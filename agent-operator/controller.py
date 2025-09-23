#!/usr/bin/env python3
"""
Agent Controller for OpenShift Agent Discovery.

This controller watches for resources with ai.openshift.io/agent.* labels
and creates corresponding Agent custom resources.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import httpx
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Agent label prefix
AGENT_LABEL_PREFIX = "ai.openshift.io/agent."
AGENT_CLASS_LABEL = f"{AGENT_LABEL_PREFIX}class"
AGENT_NAME_LABEL = f"{AGENT_LABEL_PREFIX}name"
AGENT_VERSION_LABEL = f"{AGENT_LABEL_PREFIX}version"

# Agent annotations
AGENT_DESCRIPTION_ANNOTATION = "ai.openshift.io/agent.description"
AGENT_SKILLS_ANNOTATION = "ai.openshift.io/agent.skills"
AGENT_ENDPOINT_ANNOTATION = "ai.openshift.io/agent.endpoint"

# CRD details
AGENT_CRD_GROUP = "ai.openshift.io"
AGENT_CRD_VERSION = "v1"
AGENT_CRD_PLURAL = "agents"


class AgentController:
    """Controller that manages Agent CRs based on labeled resources."""

    def __init__(self):
        """Initialize the controller."""
        # Load Kubernetes config
        try:
            # Try in-cluster config first
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            # Fall back to local config
            config.load_kube_config()
            logger.info("Loaded local Kubernetes config")

        # Initialize Kubernetes clients
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_objects = client.CustomObjectsApi()

        # HTTP client for endpoint verification
        self.http_client = httpx.AsyncClient(verify=False, timeout=5)

        # Track managed agents to avoid duplicates
        self.managed_agents: Dict[str, str] = {}  # namespace/name -> resource_type/name

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.http_client.aclose()

    def extract_agent_info(self, resource: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract agent information from a Kubernetes resource."""
        metadata = resource.get("metadata", {})
        labels = metadata.get("labels") or {}
        annotations = metadata.get("annotations") or {}

        # Check if this resource has agent labels
        agent_class = labels.get(AGENT_CLASS_LABEL)
        if not agent_class:
            return None

        agent_name = labels.get(AGENT_NAME_LABEL)
        if not agent_name:
            logger.warning(f"Resource {metadata.get('name')} has agent class but no agent name")
            return None

        # Extract agent information
        agent_info = {
            "class": agent_class,
            "name": agent_name,
            "version": labels.get(AGENT_VERSION_LABEL, "unknown"),
            "description": annotations.get(AGENT_DESCRIPTION_ANNOTATION, ""),
            "endpoint": annotations.get(AGENT_ENDPOINT_ANNOTATION, "/.well-known/agent.json"),
            "sourceRef": {
                "apiVersion": resource.get("apiVersion", ""),
                "kind": resource.get("kind", ""),
                "name": metadata.get("name", ""),
                "namespace": metadata.get("namespace", "")
            }
        }

        # Parse skills if present
        skills_str = annotations.get(AGENT_SKILLS_ANNOTATION, "")
        if skills_str:
            agent_info["skills"] = [skill.strip() for skill in skills_str.split(",")]

        return agent_info

    def get_agent_url(self, resource: Dict[str, Any], agent_info: Dict[str, Any]) -> Optional[str]:
        """Get the agent URL from a resource."""
        kind = resource.get("kind", "")
        metadata = resource.get("metadata", {})

        if kind == "Route":
            # OpenShift Route
            spec = resource.get("spec", {})
            host = spec.get("host")
            if host:
                tls = spec.get("tls")
                scheme = "https" if tls else "http"
                return f"{scheme}://{host}"
        elif kind == "Service":
            # Kubernetes Service - try to find associated route or ingress
            namespace = metadata.get("namespace", "")
            service_name = metadata.get("name", "")

            # Look for OpenShift route pointing to this service
            try:
                routes = self.custom_objects.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=namespace,
                    plural="routes"
                )

                for route in routes.get("items", []):
                    route_spec = route.get("spec", {})
                    to = route_spec.get("to", {})
                    if to.get("name") == service_name:
                        host = route_spec.get("host")
                        if host:
                            tls = route_spec.get("tls")
                            scheme = "https" if tls else "http"
                            return f"{scheme}://{host}"
            except ApiException as e:
                logger.warning(f"Could not query routes: {e}")

        return None

    async def verify_agent_endpoint(self, url: str, endpoint: str) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Verify that an agent endpoint is accessible and fetch agent card."""
        if not url:
            return False, None

        agent_url = f"{url.rstrip('/')}{endpoint}"
        try:
            response = await self.http_client.get(agent_url)
            if response.status_code == 200:
                try:
                    agent_card = response.json()
                    return True, agent_card
                except:
                    return True, None
            return False, None
        except Exception as e:
            logger.debug(f"Agent endpoint {agent_url} not accessible: {e}")
            return False, None

    def create_agent_cr(self, agent_info: Dict[str, Any], url: Optional[str] = None, agent_card: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create an Agent custom resource from agent info."""
        namespace = agent_info["sourceRef"]["namespace"]
        agent_name = agent_info["name"]

        # Generate CR name (lowercase, no special chars)
        cr_name = f"{agent_name.lower().replace('_', '-')}"

        agent_cr = {
            "apiVersion": f"{AGENT_CRD_GROUP}/{AGENT_CRD_VERSION}",
            "kind": "Agent",
            "metadata": {
                "name": cr_name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "agent-controller",
                    f"{AGENT_LABEL_PREFIX}class": agent_info["class"]
                }
            },
            "spec": {
                "class": agent_info["class"],
                "name": agent_info["name"],
                "endpoint": agent_info["endpoint"],
                "sourceRef": agent_info["sourceRef"]
            },
            "status": {
                "phase": "Discovered",
                "conditions": []
            }
        }

        # Add URL to status if available
        if url:
            agent_cr["status"]["url"] = url

        # Add agent card to status if available
        if agent_card:
            agent_cr["status"]["agentCard"] = agent_card

        return agent_cr

    async def update_agent_status(self, namespace: str, cr_name: str, url: Optional[str] = None, endpoint: str = "/.well-known/agent.json"):
        """Update the status of an Agent CR."""
        try:
            # Get current CR
            agent = self.custom_objects.get_namespaced_custom_object(
                group=AGENT_CRD_GROUP,
                version=AGENT_CRD_VERSION,
                namespace=namespace,
                plural=AGENT_CRD_PLURAL,
                name=cr_name
            )

            # Update status
            now = datetime.now(timezone.utc).isoformat()
            status = agent.get("status", {})

            if url:
                status["url"] = url
                # Verify endpoint and fetch agent card
                accessible, agent_card = await self.verify_agent_endpoint(url, endpoint)
                if accessible:
                    status["phase"] = "Ready"
                    status["lastSeen"] = now
                    if agent_card:
                        status["agentCard"] = agent_card
                    condition = {
                        "type": "Ready",
                        "status": "True",
                        "reason": "EndpointAccessible",
                        "message": "Agent endpoint is accessible",
                        "lastTransitionTime": now
                    }
                else:
                    status["phase"] = "Failed"
                    condition = {
                        "type": "Ready",
                        "status": "False",
                        "reason": "EndpointNotAccessible",
                        "message": "Agent endpoint is not accessible",
                        "lastTransitionTime": now
                    }
            else:
                status["phase"] = "Failed"
                condition = {
                    "type": "Ready",
                    "status": "False",
                    "reason": "NoURL",
                    "message": "No accessible URL found for agent",
                    "lastTransitionTime": now
                }

            # Update conditions
            conditions = status.get("conditions", [])
            # Remove existing Ready condition
            conditions = [c for c in conditions if c.get("type") != "Ready"]
            conditions.append(condition)
            status["conditions"] = conditions

            # Update the CR
            agent["status"] = status
            self.custom_objects.patch_namespaced_custom_object(
                group=AGENT_CRD_GROUP,
                version=AGENT_CRD_VERSION,
                namespace=namespace,
                plural=AGENT_CRD_PLURAL,
                name=cr_name,
                body=agent
            )

            logger.info(f"Updated Agent CR {namespace}/{cr_name} status: {status['phase']}")

        except ApiException as e:
            logger.error(f"Failed to update Agent CR status: {e}")

    async def handle_resource_event(self, event_type: str, resource: Dict[str, Any]):
        """Handle a resource event."""
        metadata = resource.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "")
        kind = resource.get("kind", "")

        logger.debug(f"Handling {event_type} event for {kind} {namespace}/{name}")

        agent_info = self.extract_agent_info(resource)
        if not agent_info:
            return

        agent_key = f"{namespace}/{agent_info['name']}"

        if event_type in ["ADDED", "MODIFIED"]:
            # Create or update Agent CR
            try:
                # Get agent URL
                url = self.get_agent_url(resource, agent_info)

                # Generate CR name
                cr_name = f"{agent_info['name'].lower().replace('_', '-')}"

                # Check if Agent CR already exists
                try:
                    existing_agent = self.custom_objects.get_namespaced_custom_object(
                        group=AGENT_CRD_GROUP,
                        version=AGENT_CRD_VERSION,
                        namespace=namespace,
                        plural=AGENT_CRD_PLURAL,
                        name=cr_name
                    )

                    # Only update if this is a Route (priority resource) or if existing has no URL
                    existing_url = existing_agent.get("status", {}).get("url")
                    if kind == "Route" or not existing_url:
                        logger.info(f"Updating existing Agent CR {namespace}/{cr_name} from {kind}")

                        # Update the sourceRef to point to this resource if it's better
                        if kind == "Route" or not existing_agent.get("spec", {}).get("sourceRef", {}).get("kind"):
                            patch_data = {
                                "spec": {
                                    "sourceRef": agent_info["sourceRef"]
                                }
                            }
                            self.custom_objects.patch_namespaced_custom_object(
                                group=AGENT_CRD_GROUP,
                                version=AGENT_CRD_VERSION,
                                namespace=namespace,
                                plural=AGENT_CRD_PLURAL,
                                name=cr_name,
                                body=patch_data
                            )

                        await self.update_agent_status(namespace, cr_name, url, agent_info["endpoint"])

                except ApiException as e:
                    if e.status == 404:
                        # Create new Agent CR
                        agent_cr = self.create_agent_cr(agent_info, url)

                        self.custom_objects.create_namespaced_custom_object(
                            group=AGENT_CRD_GROUP,
                            version=AGENT_CRD_VERSION,
                            namespace=namespace,
                            plural=AGENT_CRD_PLURAL,
                            body=agent_cr
                        )

                        logger.info(f"Created Agent CR {namespace}/{cr_name} from {kind}")

                        # Update status
                        await self.update_agent_status(namespace, cr_name, url, agent_info["endpoint"])

                        # Track this agent
                        self.managed_agents[agent_key] = f"{kind}/{name}"
                    else:
                        logger.error(f"Error checking for existing Agent CR: {e}")

            except Exception as e:
                logger.error(f"Failed to handle resource event: {e}")

        elif event_type == "DELETED":
            # Remove Agent CR if we created it
            if agent_key in self.managed_agents:
                try:
                    cr_name = f"{agent_info['name'].lower().replace('_', '-')}"
                    self.custom_objects.delete_namespaced_custom_object(
                        group=AGENT_CRD_GROUP,
                        version=AGENT_CRD_VERSION,
                        namespace=namespace,
                        plural=AGENT_CRD_PLURAL,
                        name=cr_name
                    )
                    logger.info(f"Deleted Agent CR {namespace}/{cr_name}")
                    del self.managed_agents[agent_key]

                except ApiException as e:
                    if e.status != 404:  # Ignore not found errors
                        logger.error(f"Failed to delete Agent CR: {e}")

    async def sync_existing_resources(self):
        """Sync existing resources with agent labels."""
        logger.info("Syncing existing resources...")

        # Sync routes
        try:
            routes = self.custom_objects.list_cluster_custom_object(
                group="route.openshift.io",
                version="v1",
                plural="routes"
            )

            for route in routes.get("items", []):
                # Routes from custom_objects already have apiVersion and kind
                await self.handle_resource_event("ADDED", route)

        except ApiException as e:
            logger.warning(f"Could not sync routes: {e}")

        # Sync services
        try:
            services = self.core_v1.list_service_for_all_namespaces()
            for service in services.items:
                service_dict = service.to_dict()
                service_dict["apiVersion"] = "v1"
                service_dict["kind"] = "Service"
                await self.handle_resource_event("ADDED", service_dict)
        except ApiException as e:
            logger.warning(f"Could not sync services: {e}")

        # Sync deployments
        try:
            deployments = self.apps_v1.list_deployment_for_all_namespaces()
            for deployment in deployments.items:
                deployment_dict = deployment.to_dict()
                deployment_dict["apiVersion"] = "apps/v1"
                deployment_dict["kind"] = "Deployment"
                await self.handle_resource_event("ADDED", deployment_dict)
        except ApiException as e:
            logger.warning(f"Could not sync deployments: {e}")

        logger.info("Finished syncing existing resources")

    async def watch_resources(self):
        """Watch for resource changes."""
        logger.info("Starting to watch for agent resources...")

        # Watch different resource types
        resource_watchers = [
            ("routes", "route.openshift.io", "v1", "routes"),
            ("services", "v1", None, "services"),
            ("deployments", "apps", "v1", "deployments"),
        ]

        tasks = []
        for name, group, version, plural in resource_watchers:
            if group == "v1":
                # Core API
                if plural == "services":
                    list_func = self.core_v1.list_service_for_all_namespaces
                else:
                    continue
            elif group == "apps":
                # Apps API
                if plural == "deployments":
                    list_func = self.apps_v1.list_deployment_for_all_namespaces
                else:
                    continue
            else:
                # Custom resources (like OpenShift routes)
                def make_list_func(g, v, p):
                    return lambda: self.custom_objects.list_cluster_custom_object(
                        group=g, version=v, plural=p
                    )
                list_func = make_list_func(group, version, plural)

            task = asyncio.create_task(self._watch_resource_type(name, list_func))
            tasks.append(task)

        # Wait for all watchers
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _watch_resource_type(self, resource_name: str, list_func):
        """Watch a specific resource type."""
        while True:
            try:
                logger.info(f"Starting watch for {resource_name}")

                # Create watch stream
                w = watch.Watch()

                # Watch for changes
                for event in w.stream(list_func):
                    event_type = event['type']
                    resource = event['object']

                    # Convert Kubernetes object to dict and add apiVersion/kind
                    if hasattr(resource, 'to_dict'):
                        resource_dict = resource.to_dict()
                        # Add apiVersion and kind based on resource type
                        if resource_name == "services":
                            resource_dict["apiVersion"] = "v1"
                            resource_dict["kind"] = "Service"
                        elif resource_name == "deployments":
                            resource_dict["apiVersion"] = "apps/v1"
                            resource_dict["kind"] = "Deployment"
                        elif resource_name == "routes":
                            resource_dict["apiVersion"] = "route.openshift.io/v1"
                            resource_dict["kind"] = "Route"
                        resource = resource_dict

                    # Handle the event
                    await self.handle_resource_event(event_type, resource)

            except Exception as e:
                logger.error(f"Error watching {resource_name}: {e}")
                logger.info(f"Restarting watch for {resource_name} in 10 seconds...")
                await asyncio.sleep(10)


async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Controller")
    parser.add_argument("--sync-only", action="store_true",
                       help="Run sync once and exit (default: run continuous watch)")
    args = parser.parse_args()

    if args.sync_only:
        logger.info("Starting Agent Controller in sync-only mode...")
        async with AgentController() as controller:
            await controller.sync_existing_resources()
        logger.info("Sync completed successfully")
    else:
        logger.info("Starting Agent Controller in watch mode...")
        async with AgentController() as controller:
            # Sync existing resources first
            await controller.sync_existing_resources()

            # Start watching for changes
            await controller.watch_resources()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Controller stopped by user")
    except Exception as e:
        logger.error(f"Controller failed: {e}")
        sys.exit(1)
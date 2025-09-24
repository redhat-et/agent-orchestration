#!/usr/bin/env python3
"""
Simple MCP Server for A2A Agent Discovery using fastmcp.

This provides basic tools to discover A2A-compliant agents in OpenShift.
"""

import subprocess
import json
import httpx
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
from uuid import uuid4
from fastmcp import FastMCP

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
)
from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    EXTENDED_AGENT_CARD_PATH,
)


# Create the MCP server
mcp = FastMCP("Agent Discovery")


def check_oc_login() -> bool:
    """Check if user is logged into OpenShift."""
    try:
        result = subprocess.run(
            ["oc", "whoami"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_namespace_scope(
    namespace: Optional[str] = None, all_namespaces: bool = False
) -> tuple[str, str]:
    """Determine namespace scope for OpenShift commands."""
    if all_namespaces:
        return "--all-namespaces", "all namespaces"
    elif namespace:
        return f"-n {namespace}", f"namespace: {namespace}"
    else:
        # Get current project
        try:
            result = subprocess.run(
                ["oc", "project", "-q"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                current_project = result.stdout.strip()
                return f"-n {current_project}", f"current project: {current_project}"
            else:
                raise Exception(
                    "No current project set. Use namespace parameter or all_namespaces=true"
                )
        except subprocess.TimeoutExpired:
            raise Exception("Timeout checking current OpenShift project")


def discover_agents_native(namespace_flag: str) -> List[Dict[str, Any]]:
    """Discover agents using native oc get agents command."""
    try:
        # Run oc command to get Agent CRs
        cmd = f"oc get agents {namespace_flag} -o json"
        result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise Exception(f"OpenShift command failed: {result.stderr}")

        agents_data = json.loads(result.stdout)
        return agents_data.get("items", [])

    except subprocess.TimeoutExpired:
        raise Exception("Timeout discovering agents")
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse OpenShift response: {e}")


@mcp.tool()
def discover_agents(
    namespace: Optional[str] = None,
    all_namespaces: bool = False,
    verify_endpoints: bool = False,
) -> str:
    """Discover agents in OpenShift cluster or namespace using native oc get agents."""

    # Check OpenShift login
    if not check_oc_login():
        raise Exception("Not logged into OpenShift. Please run 'oc login' first.")

    # Get namespace scope
    namespace_flag, scope_msg = get_namespace_scope(namespace, all_namespaces)

    # Discover agents using native command
    agent_crs = discover_agents_native(namespace_flag)

    if not agent_crs:
        return f'No agents found in {scope_msg}.\n\nTo make agents discoverable, ensure they have these labels:\n  ai.openshift.io/agent.class: "a2a"\n  ai.openshift.io/agent.name: "your-agent-name"'

    # Process discovered Agent CRs
    agents = []
    for agent_cr in agent_crs:
        metadata = agent_cr.get("metadata", {})
        spec = agent_cr.get("spec", {})
        status = agent_cr.get("status", {})

        agent_name = spec.get("name", "unknown")
        namespace = metadata.get("namespace", "")
        agent_class = spec.get("class", "unknown")
        endpoint = spec.get("endpoint", "/.well-known/agent.json")
        url = status.get("url", "")
        phase = status.get("phase", "Unknown")

        # Get agent card data if available
        agent_card = status.get("agentCard", {})
        description = agent_card.get("description", "")
        version = agent_card.get("version", "")

        agent_card_url = f"{url}{endpoint}" if url else ""

        agent_info = {
            "agent_name": agent_name,
            "namespace": namespace,
            "class": agent_class,
            "version": version,
            "phase": phase,
            "url": url,
            "agent_card_url": agent_card_url,
            "description": description,
        }

        if verify_endpoints and agent_card_url:
            try:
                with httpx.Client(verify=False, timeout=5) as client:
                    response = client.get(agent_card_url)
                    agent_info["endpoint_accessible"] = response.status_code == 200
            except:
                agent_info["endpoint_accessible"] = False
        elif verify_endpoints:
            agent_info["endpoint_accessible"] = False

        agents.append(agent_info)

    result_text = f"Found {len(agents)} agent(s) in {scope_msg}:\n\n"
    result_text += json.dumps(agents, indent=2)

    return result_text


@mcp.tool()
def get_agent_card(agent_url: str, endpoint: str = "/.well-known/agent.json") -> str:
    """Retrieve the agent card for a specific A2A agent."""

    # Construct full agent card URL
    agent_card_url = urljoin(agent_url, endpoint)

    try:
        with httpx.Client(verify=False, timeout=5) as client:
            response = client.get(agent_card_url)

            if response.status_code != 200:
                raise Exception(
                    f"Failed to retrieve agent card from {agent_card_url} (status: {response.status_code})"
                )

            agent_card = response.json()

        result_text = f"Agent card from {agent_card_url}:\n\n"
        result_text += json.dumps(agent_card, indent=2)

        return result_text

    except httpx.RequestError as e:
        raise Exception(f"Network error retrieving agent card: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in agent card: {e}")


@mcp.tool()
def list_agents(namespace: Optional[str] = None, all_namespaces: bool = False) -> str:
    """Get a summary list of all discovered agents."""

    # Get agent data using discover_agents
    try:
        agents_json = discover_agents(namespace, all_namespaces, False)

        # Check if it's an error message
        if "No agents found" in agents_json or "Error:" in agents_json:
            return agents_json

        # Parse the JSON from the discover result
        lines = agents_json.split("\n")
        json_start = next(
            i for i, line in enumerate(lines) if line.strip().startswith("[")
        )
        json_content = "\n".join(lines[json_start:])
        agents = json.loads(json_content)

        # Create summary table
        summary = "Agent Summary:\n\n"
        summary += f"{'AGENT NAME':<20} {'CLASS':<10} {'VERSION':<10} {'PHASE':<8} {'NAMESPACE':<15} {'URL':<40}\n"
        summary += f"{'-'*20} {'-'*10} {'-'*10} {'-'*8} {'-'*15} {'-'*40}\n"

        for agent in agents:
            summary += f"{agent['agent_name']:<20} {agent['class']:<10} {agent['version']:<10} {agent['phase']:<8} {agent['namespace']:<15} {agent['url']:<40}\n"

        summary += f"\nTotal: {len(agents)} agent(s)"

        return summary

    except Exception as e:
        raise Exception(f"Error creating agent summary: {e}")


@mcp.tool()
async def send_message_to_agent(
    agent_url: str, message: str, auth_token: Optional[str] = None
) -> str:
    """Send a message to an A2A agent and get the response."""

    async with httpx.AsyncClient(verify=False, timeout=30) as httpx_client:
        # Initialize A2ACardResolver
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=agent_url,
        )

        # Fetch agent card
        final_agent_card_to_use: AgentCard | None = None

        try:
            # Try to get the public agent card first
            public_card = await resolver.get_agent_card()
            final_agent_card_to_use = public_card

            # If auth token provided and extended card is supported, try to get it
            if auth_token and public_card.supports_authenticated_extended_card:
                try:
                    auth_headers_dict = {"Authorization": f"Bearer {auth_token}"}
                    extended_card = await resolver.get_agent_card(
                        relative_card_path=EXTENDED_AGENT_CARD_PATH,
                        http_kwargs={"headers": auth_headers_dict},
                    )
                    final_agent_card_to_use = extended_card
                except Exception:
                    # Fall back to public card if extended card fails
                    pass

        except Exception as e:
            raise Exception(f"Failed to fetch agent card from {agent_url}: {e}")

        # Initialize client and send message
        client = A2AClient(
            httpx_client=httpx_client, agent_card=final_agent_card_to_use
        )

        send_message_payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": uuid4().hex,
            },
        }

        request = SendMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )

        try:
            response = await client.send_message(request)
            return f"Response from {agent_url}:\n\n{response.model_dump_json(indent=2, exclude_none=True)}"
        except Exception as e:
            raise Exception(f"Failed to send message to agent: {e}")


@mcp.tool()
async def send_streaming_message_to_agent(
    agent_url: str, message: str, auth_token: Optional[str] = None
) -> str:
    """Send a streaming message to an A2A agent and get the streaming response."""

    async with httpx.AsyncClient(verify=False, timeout=30) as httpx_client:
        # Initialize A2ACardResolver
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=agent_url,
        )

        # Fetch agent card
        final_agent_card_to_use: AgentCard | None = None

        try:
            # Try to get the public agent card first
            public_card = await resolver.get_agent_card()
            final_agent_card_to_use = public_card

            # If auth token provided and extended card is supported, try to get it
            if auth_token and public_card.supports_authenticated_extended_card:
                try:
                    auth_headers_dict = {"Authorization": f"Bearer {auth_token}"}
                    extended_card = await resolver.get_agent_card(
                        relative_card_path=EXTENDED_AGENT_CARD_PATH,
                        http_kwargs={"headers": auth_headers_dict},
                    )
                    final_agent_card_to_use = extended_card
                except Exception:
                    # Fall back to public card if extended card fails
                    pass

        except Exception as e:
            raise Exception(f"Failed to fetch agent card from {agent_url}: {e}")

        # Initialize client and send streaming message
        client = A2AClient(
            httpx_client=httpx_client, agent_card=final_agent_card_to_use
        )

        send_message_payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": uuid4().hex,
            },
        }

        streaming_request = SendStreamingMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )

        try:
            stream_response = client.send_message_streaming(streaming_request)

            result_chunks = []
            async for chunk in stream_response:
                result_chunks.append(chunk.model_dump(mode="json", exclude_none=True))

            return f"Streaming response from {agent_url}:\n\n" + "\n\n".join(
                [json.dumps(chunk, indent=2) for chunk in result_chunks]
            )

        except Exception as e:
            raise Exception(f"Failed to send streaming message to agent: {e}")


if __name__ == "__main__":
    mcp.run()

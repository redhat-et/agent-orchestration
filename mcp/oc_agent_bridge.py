#!/usr/bin/env python3
"""
MCP Server for A2A Agent Discovery and Verification.

Provides tools to discover, verify, and communicate with A2A-compliant agents in OpenShift.
Supports cryptographic signature verification for agent cards.
"""

import base64
import copy
import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from uuid import uuid4

import httpx
from authlib.jose.rfc7515.jws import JsonWebSignature
from authlib.jose.rfc7517.jwk import JsonWebKey
from fastmcp import FastMCP

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
)
from a2a.utils.constants import EXTENDED_AGENT_CARD_PATH

# Initialize MCP server and logger
mcp = FastMCP("Agent Discovery")
logger = logging.getLogger(__name__)

# Constants
DEFAULT_AGENT_ENDPOINT = "/.well-known/agent.json"
HTTPX_TIMEOUT = 5
AGENT_LABEL_KEYS = ("a2a.agent.name", "ai.openshift.io/agent.name", "app")
ALLOWED_SIGNATURE_ALGORITHMS = ["RS256", "ES256"]


# Configuration and data classes

class SecurityConfig:
    """Centralized security configuration."""

    ALLOWED_ALGORITHMS = ALLOWED_SIGNATURE_ALGORITHMS
    MAX_SIGNATURE_AGE_SECONDS = int(os.getenv("A2A_MAX_SIGNATURE_AGE_SECONDS", str(365 * 24 * 60 * 60)))

    @staticmethod
    def require_verified_card() -> bool:
        """Check if card verification is required."""
        return os.getenv("A2A_REQUIRE_VERIFIED_CARD", "false").lower() in ("1", "true", "yes")

    @staticmethod
    def httpx_verify() -> bool:
        """Return whether to verify TLS based on env (default True)."""
        return not (os.getenv("A2A_INSECURE_SKIP_TLS_VERIFY", "false").lower() in ("1", "true", "yes"))


@dataclass
class AgentInfo:
    """Data class for agent information."""
    agent_name: str
    namespace: str
    agent_class: str
    version: str
    phase: str
    url: str
    agent_card_url: str
    description: str
    endpoint_accessible: Optional[bool] = None
    signature_verified: Optional[bool] = None
    signature_verification: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

# Signature verification helpers

def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode_to_json(b64: str) -> Dict[str, Any]:
    """Decode base64url-encoded JSON."""
    pad_len = (-len(b64)) % 4
    padded = b64 + ("=" * pad_len)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _candidate_payload_b64s(agent_card: Dict[str, Any]) -> List[str]:
    """Return possible payload encodings (Base64url) for verification.

    Order: RFC8785/JCS (if available) then deterministic minified JSON.
    """
    uniques: List[str] = []
    # Remove signatures before serialization
    card_copy: Dict[str, Any] = copy.deepcopy(agent_card)
    card_copy.pop("signatures", None)

    # Try RFC8785/JCS canonicalization if library is present
    try:
        import rfc8785  # type: ignore

        jcs_str = rfc8785.dump(card_copy)
        if isinstance(jcs_str, bytes):
            jcs_bytes = jcs_str
        else:
            jcs_bytes = jcs_str.encode("utf-8")
        b64 = _base64url_encode(jcs_bytes)
        uniques.append(b64)
    except Exception:
        pass

    # Fallback deterministic JSON
    payload_str = json.dumps(card_copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    b64 = _base64url_encode(payload_str.encode("utf-8"))
    if b64 not in uniques:
        uniques.append(b64)

    return uniques


class SignatureVerifier:
    """Handles AgentCard signature verification."""

    def __init__(self, jwks: Optional[Dict[str, Any]] = None):
        """Initialize verifier with optional JWKS."""
        self.jwks = jwks or self._load_trusted_jwks()
        self.jws = JsonWebSignature()

    @staticmethod
    def _load_trusted_jwks() -> Optional[Dict[str, Any]]:
        """Load trusted JWKS from environment (JSON string, file path, or URL)."""
        # Try JSON string
        if jwks_json := os.getenv("A2A_TRUSTED_JWKS_JSON"):
            try:
                return json.loads(jwks_json)
            except json.JSONDecodeError as e:
                raise Exception(f"A2A_TRUSTED_JWKS_JSON is not valid JSON: {e}")

        # Try file path
        if (jwks_path := os.getenv("A2A_TRUSTED_JWKS_PATH")) and os.path.exists(jwks_path):
            with open(jwks_path, encoding="utf-8") as f:
                return json.load(f)

        # Try URL
        if jwks_url := os.getenv("A2A_TRUSTED_JWKS_URL"):
            with httpx.Client(verify=SecurityConfig.httpx_verify(), timeout=HTTPX_TIMEOUT) as client:
                return client.get(jwks_url).raise_for_status().json()

        return None

    @staticmethod
    def _validate_timestamps(protected_json: Dict[str, Any]) -> None:
        """Validate exp, nbf, and iat claims."""
        current_time = int(time.time())

        # Check expiration time (exp)
        exp = protected_json.get("exp")
        if exp is not None:
            if not isinstance(exp, (int, float)) or exp < current_time:
                raise Exception(f"Signature has expired (exp: {exp}, current: {current_time})")

        # Check not before time (nbf)
        nbf = protected_json.get("nbf")
        if nbf is not None:
            if not isinstance(nbf, (int, float)) or nbf > current_time:
                raise Exception(f"Signature not yet valid (nbf: {nbf}, current: {current_time})")

        # Check issued at time (iat) - warn if too old
        iat = protected_json.get("iat")
        if iat is not None:
            if not isinstance(iat, (int, float)):
                raise Exception(f"Invalid iat timestamp: {iat}")
            age_seconds = current_time - iat
            if age_seconds > SecurityConfig.MAX_SIGNATURE_AGE_SECONDS:
                logger.warning(f"Signature is very old (iat: {iat}, age: {age_seconds}s)")

    def _create_key_resolver(self, key_set: Any):
        """Create a key resolver function for signature verification."""
        def key_resolver(header: Dict[str, Any], _payload: Any):
            kid = header.get("kid")
            key = key_set.find_by_kid(kid)

            # Security: validate key usage if present
            if key and hasattr(key, 'use') and key.use and key.use != 'sig':
                raise Exception(f"Key {kid} has invalid use: {key.use} (expected 'sig')")

            # Security: validate key type matches algorithm
            if key and hasattr(key, 'kty'):
                alg = header.get('alg', '')
                if alg.startswith('RS') or alg.startswith('PS'):
                    if key.kty != 'RSA':
                        raise Exception(f"Algorithm {alg} requires RSA key, got {key.kty}")
                elif alg.startswith('ES'):
                    if key.kty != 'EC':
                        raise Exception(f"Algorithm {alg} requires EC key, got {key.kty}")

            return key
        return key_resolver

    def verify(self, agent_card: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """Verify AgentCard.signatures using JWS JSON Serialization per RFC 7515.

        - Uses only the trusted JWKS provided.
        - Does NOT use embedded jwk or jku headers from the agent card.
        - Requires ALL signatures to verify against trusted keys (not just ANY).
        Returns (all_valid, details_per_signature).
        """
        details: List[Dict[str, Any]] = []
        signatures = agent_card.get("signatures") or []
        if not signatures:
            return False, details

        payload_b64_candidates = _candidate_payload_b64s(agent_card)

        if self.jwks is None:
            logger.warning("No trusted JWKS configured - signature verification will be skipped")
            return False, [{"valid": False, "error": "No trusted JWKS available"}]

        key_set = JsonWebKey.import_key_set(self.jwks)
        key_resolver = self._create_key_resolver(key_set)

        all_valid = True
        for sig in signatures:
            protected_b64 = sig.get("protected")
            signature = sig.get("signature")
            unprotected = sig.get("header")
            info: Dict[str, Any] = {"valid": False}

            try:
                protected_json = _base64url_decode_to_json(protected_b64) if protected_b64 else {}
                info["kid"] = protected_json.get("kid") or (unprotected or {}).get("kid")
                info["alg"] = protected_json.get("alg")

                # Security: validate algorithm is in allowlist
                if info["alg"] not in SecurityConfig.ALLOWED_ALGORITHMS:
                    raise Exception(f"Algorithm {info['alg']} not in allowlist: {SecurityConfig.ALLOWED_ALGORITHMS}")

                # Security: reject signatures with critical headers (crit)
                crit = protected_json.get("crit") or (unprotected or {}).get("crit")
                if crit:
                    raise Exception(f"Signature contains unsupported critical headers: {crit}")

                # Validate timestamps
                self._validate_timestamps(protected_json)

                # Verify signature
                verified = False
                for payload_b64 in payload_b64_candidates:
                    flattened = {
                        "payload": payload_b64,
                        "protected": protected_b64,
                        "signature": signature,
                    }
                    if unprotected is not None:
                        flattened["header"] = unprotected
                    try:
                        self.jws.deserialize_json(flattened, key_resolver)
                        verified = True
                        break
                    except Exception as verify_err:
                        logger.debug(f"Signature verification failed for payload candidate: {verify_err}")
                        continue

                if verified:
                    info["valid"] = True
                    logger.info(f"Signature verified successfully: kid={info.get('kid')}, alg={info.get('alg')}")
                else:
                    all_valid = False
                    logger.warning(f"Signature verification failed: kid={info.get('kid')}, alg={info.get('alg')}")
            except Exception as e:
                info["error"] = str(e)
                all_valid = False
                logger.error(f"Error verifying signature: {e}")

            details.append(info)

        return all_valid, details

    def verify_if_required(self, agent_card: AgentCard) -> None:
        """If A2A_REQUIRE_VERIFIED_CARD=true, verify signatures or raise Exception."""
        if SecurityConfig.require_verified_card():
            if self.jwks is None:
                raise Exception("A2A_REQUIRE_VERIFIED_CARD is true but no JWKS configured")
            card_dict = agent_card.model_dump(mode='json', exclude_none=True)
            ok, _ = self.verify(card_dict)
            if not ok:
                raise Exception("AgentCard signatures did not verify")


class OpenShiftClient:
    """Wrapper for OpenShift CLI operations."""

    @staticmethod
    def check_login() -> bool:
        """Check if user is logged into OpenShift."""
        try:
            result = subprocess.run(
                ["oc", "whoami"], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    def get_current_namespace() -> str:
        """Get current OpenShift namespace."""
        result = subprocess.run(
            ["oc", "project", "-q"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise Exception("No current project set. Use namespace parameter or all_namespaces=true")
        return result.stdout.strip()

    @staticmethod
    def get_namespace_scope(namespace: Optional[str] = None, all_namespaces: bool = False) -> Tuple[str, str]:
        """Determine namespace scope for OpenShift commands."""
        if all_namespaces:
            return "--all-namespaces", "all namespaces"
        elif namespace:
            return f"-n {namespace}", f"namespace: {namespace}"
        else:
            try:
                current_project = OpenShiftClient.get_current_namespace()
                return f"-n {current_project}", f"current project: {current_project}"
            except subprocess.TimeoutExpired:
                raise Exception("Timeout checking current OpenShift project")

    @staticmethod
    def get_agents(namespace_flag: str) -> List[Dict[str, Any]]:
        """Fetch Agent CRs."""
        try:
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

    @staticmethod
    def get_routes(namespace_flag: str, label_selector: str = "a2a.agent=true") -> List[Dict[str, Any]]:
        """Discover A2A routes using OpenShift CLI (label-based)."""
        try:
            cmd = f"oc get routes {namespace_flag} -l {label_selector} -o json"
            result = subprocess.run(
                cmd.split(), capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                raise Exception(f"OpenShift command failed: {result.stderr}")

            routes_data = json.loads(result.stdout)
            return routes_data.get("items", [])

        except subprocess.TimeoutExpired:
            raise Exception("Timeout discovering routes")
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse OpenShift response: {e}")

    @staticmethod
    def get_route(name: str, namespace: str) -> Optional[Dict[str, Any]]:
        """Get a specific Route by name."""
        try:
            result = subprocess.run(
                ["oc", "get", "route", name, "-n", namespace, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            return json.loads(result.stdout)
        except Exception:
            return None

    @staticmethod
    def _build_url_from_route(route_spec: Dict[str, Any]) -> Optional[str]:
        """Build URL from route spec (host + TLS)."""
        if not (host := route_spec.get("host")):
            return None
        scheme = "https" if route_spec.get("tls") else "http"
        return f"{scheme}://{host}"

    @staticmethod
    def resolve_url_from_source_ref(ns: str, source_ref: Dict[str, Any]) -> Optional[str]:
        """Resolve Agent URL from spec.sourceRef (Route or Service)."""
        kind = (source_ref.get("kind") or "").strip()
        name = (source_ref.get("name") or "").strip()
        if not (kind and name):
            return None

        try:
            if kind == "Route":
                if route := OpenShiftClient.get_route(name, ns):
                    return OpenShiftClient._build_url_from_route(route.get("spec", {}))

            elif kind == "Service":
                routes = OpenShiftClient.get_routes(f"-n {ns}", label_selector="")
                for route in routes:
                    spec = route.get("spec", {})
                    if spec.get("to", {}).get("name") == name:
                        return OpenShiftClient._build_url_from_route(spec)
        except Exception:
            pass

        return None


class RouteIndexBuilder:
    """Builds an index of routes for agent URL resolution."""

    @staticmethod
    def build_route_index(routes: List[Dict[str, Any]]) -> Dict[Tuple[str, str], str]:
        """Build index of (namespace, name) -> URL from routes."""
        index: Dict[Tuple[str, str], str] = {}

        for route in routes:
            metadata = route.get("metadata", {})
            spec = route.get("spec", {})

            ns = metadata.get("namespace", "")
            host = spec.get("host", "")
            if not (ns and host):
                continue

            url = f"https://{host}"
            labels = metadata.get("labels", {})

            # Index by label values (priority order)
            for key in AGENT_LABEL_KEYS:
                if name := labels.get(key):
                    index[(ns, name)] = url

            # Fallback: index by route name
            if route_name := metadata.get("name"):
                index.setdefault((ns, route_name), url)

        return index


async def _get_agent_card_with_auth(
    resolver: A2ACardResolver,
    auth_token: Optional[str]
) -> AgentCard:
    """Fetch agent card, trying extended card if auth provided."""
    public_card = await resolver.get_agent_card()

    if auth_token and public_card.supports_authenticated_extended_card:
        try:
            headers = {"Authorization": f"Bearer {auth_token}"}
            return await resolver.get_agent_card(
                relative_card_path=EXTENDED_AGENT_CARD_PATH,
                http_kwargs={"headers": headers}
            )
        except Exception:
            pass  # Fall back to public card

    return public_card


async def _fetch_and_verify_card(agent_url: str, auth_token: Optional[str] = None) -> AgentCard:
    """Fetch and verify agent card with optional authentication."""
    async with httpx.AsyncClient(verify=SecurityConfig.httpx_verify(), timeout=30) as client:
        resolver = A2ACardResolver(httpx_client=client, base_url=agent_url)

        try:
            agent_card = await _get_agent_card_with_auth(resolver, auth_token)
        except Exception as e:
            raise Exception(f"Failed to fetch agent card from {agent_url}: {e}")

        # Verify signatures if required
        SignatureVerifier().verify_if_required(agent_card)

        return agent_card


def _verify_endpoint_and_signature(
    agent_info: AgentInfo,
    agent_card_url: str,
    verify_endpoints: bool,
    verify_signatures: bool,
    verifier: Optional[SignatureVerifier]
) -> None:
    """Verify endpoint accessibility and signatures, updating agent_info in place."""
    if not (verify_endpoints or verify_signatures) or not agent_card_url:
        if verify_endpoints:
            agent_info.endpoint_accessible = False
        return

    try:
        with httpx.Client(verify=SecurityConfig.httpx_verify(), timeout=HTTPX_TIMEOUT) as client:
            response = client.get(agent_card_url)
            agent_info.endpoint_accessible = (response.status_code == 200)

            if not (verify_signatures and response.status_code == 200 and verifier):
                return

            card_json = response.json()

            if verifier.jwks is None:
                agent_info.signature_verified = None
                agent_info.signature_verification = {"status": "skipped", "reason": "No trusted JWKS configured"}
                if SecurityConfig.require_verified_card():
                    raise Exception("A2A_REQUIRE_VERIFIED_CARD is true but no JWKS configured")
            else:
                ok, details = verifier.verify(card_json)
                agent_info.signature_verified = ok
                agent_info.signature_verification = {"details": details}
                if not ok and SecurityConfig.require_verified_card():
                    raise Exception(f"AgentCard signatures did not verify: {details}")

    except Exception as e:
        if verify_signatures:
            agent_info.signature_verified = False
            agent_info.signature_verification = {"error": str(e)}
        agent_info.endpoint_accessible = False
        if SecurityConfig.require_verified_card():
            raise Exception(f"Failed to verify agent {agent_info.agent_name}: {e}")


def _discover_agents_impl(
    namespace: Optional[str] = None,
    all_namespaces: bool = False,
    verify_endpoints: bool = False,
    verify_signatures: bool = False,
) -> Tuple[List[Dict[str, Any]], str]:
    """Core agent discovery implementation.

    Returns: (agents_list, scope_message)
    """
    # Check OpenShift login
    if not OpenShiftClient.check_login():
        raise Exception("Not logged into OpenShift. Please run 'oc login' first.")

    # Get namespace scope
    namespace_flag, scope_msg = OpenShiftClient.get_namespace_scope(namespace, all_namespaces)

    agents: List[Dict[str, Any]] = []
    agent_crs = OpenShiftClient.get_agents(namespace_flag)
    if not agent_crs:
        return [], scope_msg

    # Build a fallback index of Routes (labelled a2a.agent=true), in case Agent.status.url is missing
    route_index: Dict[Tuple[str, str], str] = {}
    try:
        fallback_routes = OpenShiftClient.get_routes(namespace_flag)
        route_index = RouteIndexBuilder.build_route_index(fallback_routes)
    except Exception:
        # If route discovery fails, continue without fallback
        pass

    # Initialize verifier if needed
    verifier = SignatureVerifier() if verify_signatures else None

    for agent_cr in agent_crs:
        metadata = agent_cr.get("metadata", {})
        spec = agent_cr.get("spec", {})
        status = agent_cr.get("status", {})

        agent_name = spec.get("name", "unknown")
        ns = metadata.get("namespace", "")
        agent_class = spec.get("class", "unknown")
        endpoint = spec.get("endpoint", DEFAULT_AGENT_ENDPOINT)
        url = status.get("url", "")

        # Fallback: if the Agent status does not include a URL yet, try to infer from the Route
        if not url:
            # 1) Prefer spec.sourceRef when present (deterministic lookup)
            source_ref = spec.get("sourceRef") or {}
            inferred = OpenShiftClient.resolve_url_from_source_ref(ns, source_ref)
            # 2) Fall back to agent/CR name based route index
            if not inferred:
                cr_name = metadata.get("name", "")
                inferred = route_index.get((ns, agent_name)) or route_index.get((ns, cr_name))
            if inferred:
                url = inferred
        phase = status.get("phase", "Unknown")

        agent_card = status.get("agentCard", {})
        description = agent_card.get("description", "")
        version = agent_card.get("version", "")

        agent_card_url = f"{url}{endpoint}" if url else ""

        agent_info = AgentInfo(
            agent_name=agent_name,
            namespace=ns,
            agent_class=agent_class,
            version=version,
            phase=phase,
            url=url,
            agent_card_url=agent_card_url,
            description=description,
        )

        _verify_endpoint_and_signature(agent_info, agent_card_url, verify_endpoints, verify_signatures, verifier)
        agents.append(agent_info.to_dict())

    return agents, scope_msg


@mcp.tool()
def discover_agents(
    namespace: Optional[str] = None,
    all_namespaces: bool = False,
    verify_endpoints: bool = False,
    verify_signatures: bool = False,
) -> str:
    """Discover agents in OpenShift using native Agent CRs only.

    - verify_endpoints: attempt to fetch card URLs to check accessibility
    - verify_signatures: if true, verify card signatures when a JWKS is available
    """
    agents, scope_msg = _discover_agents_impl(namespace, all_namespaces, verify_endpoints, verify_signatures)

    if not agents:
        return f"No agents found in {scope_msg}.\n\nTo make agents discoverable, ensure they have these labels:\n  ai.openshift.io/agent.class: \"a2a\"\n  ai.openshift.io/agent.name: \"your-agent-name\""

    return f"Found {len(agents)} agent(s) in {scope_msg}:\n\n" + json.dumps(agents, indent=2)


@mcp.tool()
def get_agent_card(agent_url: str, endpoint: str = DEFAULT_AGENT_ENDPOINT, verify_signatures: bool = False) -> str:
    """Retrieve the agent card for a specific A2A agent.

    If verify_signatures is true, verifies signatures using trusted JWKS env.
    """

    # Construct full agent card URL
    agent_card_url = urljoin(agent_url, endpoint)

    try:
        with httpx.Client(verify=SecurityConfig.httpx_verify(), timeout=HTTPX_TIMEOUT) as client:
            response = client.get(agent_card_url)

            if response.status_code != 200:
                raise Exception(
                    f"Failed to retrieve agent card from {agent_card_url} (status: {response.status_code})"
                )

            agent_card = response.json()

        result_text = f"Agent card from {agent_card_url}:\n\n"
        result_text += json.dumps(agent_card, indent=2)

        if verify_signatures:
            try:
                verifier = SignatureVerifier()
                if verifier.jwks is None:
                    result_text += "\n\nSignature verification: skipped (no JWKS configured)"
                else:
                    ok, details = verifier.verify(agent_card)
                    result_text += "\n\nSignature verification: " + ("valid" if ok else "invalid")
                    result_text += "\n" + json.dumps(details, indent=2)
            except Exception as e:
                result_text += f"\n\nSignature verification error: {e}"

        return result_text

    except httpx.RequestError as e:
        raise Exception(f"Network error retrieving agent card: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in agent card: {e}")


@mcp.tool()
def list_agents(namespace: Optional[str] = None, all_namespaces: bool = False) -> str:
    """Get a summary list of all discovered agents (native backend)."""
    agents, scope_msg = _discover_agents_impl(namespace, all_namespaces, verify_endpoints=False, verify_signatures=False)

    if not agents:
        return f"No agents found in {scope_msg}."

    # Create summary table
    summary = "Agent Summary:\n\n"
    summary += f"{'AGENT NAME':<20} {'CLASS':<10} {'VERSION':<10} {'PHASE':<8} {'NAMESPACE':<15} {'URL':<40}\n"
    summary += f"{'-'*20} {'-'*10} {'-'*10} {'-'*8} {'-'*15} {'-'*40}\n"

    for agent in agents:
        summary += f"{agent.get('agent_name',''):<20} {agent.get('agent_class',''):<10} {agent.get('version',''):<10} {agent.get('phase',''):<8} {agent.get('namespace',''):<15} {agent.get('url',''):<40}\n"

    summary += f"\nTotal: {len(agents)} agent(s)"

    return summary


@mcp.tool()
async def send_message_to_agent(
    agent_url: str, message: str, auth_token: Optional[str] = None
) -> str:
    """Send a message to an A2A agent and get the response."""
    agent_card = await _fetch_and_verify_card(agent_url, auth_token)

    async with httpx.AsyncClient(verify=SecurityConfig.httpx_verify(), timeout=30) as client:
        a2a_client = A2AClient(httpx_client=client, agent_card=agent_card)

        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(
                message={
                    "role": "user",
                    "parts": [{"kind": "text", "text": message}],
                    "messageId": uuid4().hex,
                }
            )
        )

        response = await a2a_client.send_message(request)
        return f"Response from {agent_url}:\n\n{response.model_dump_json(indent=2, exclude_none=True)}"


@mcp.tool()
async def send_streaming_message_to_agent(
    agent_url: str, message: str, auth_token: Optional[str] = None
) -> str:
    """Send a streaming message to an A2A agent and get the streaming response."""
    agent_card = await _fetch_and_verify_card(agent_url, auth_token)

    async with httpx.AsyncClient(verify=SecurityConfig.httpx_verify(), timeout=30) as client:
        a2a_client = A2AClient(httpx_client=client, agent_card=agent_card)

        request = SendStreamingMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(
                message={
                    "role": "user",
                    "parts": [{"kind": "text", "text": message}],
                    "messageId": uuid4().hex,
                }
            )
        )

        result_chunks = [
            chunk.model_dump(mode="json", exclude_none=True)
            async for chunk in a2a_client.send_message_streaming(request)
        ]

        return f"Streaming response from {agent_url}:\n\n" + "\n\n".join(
            json.dumps(chunk, indent=2) for chunk in result_chunks
        )


@mcp.tool()
def verify_agent_card_signature(agent_url: str, endpoint: str = DEFAULT_AGENT_ENDPOINT) -> str:
    """Fetch an AgentCard and verify its signatures using trusted JWKS env.

    Configure trust via env: A2A_TRUSTED_JWKS_JSON, A2A_TRUSTED_JWKS_PATH, or A2A_TRUSTED_JWKS_URL.
    """
    agent_card_url = urljoin(agent_url, endpoint)
    try:
        with httpx.Client(verify=SecurityConfig.httpx_verify(), timeout=HTTPX_TIMEOUT) as client:
            response = client.get(agent_card_url)
            if response.status_code != 200:
                raise Exception(
                    f"Failed to retrieve agent card from {agent_card_url} (status: {response.status_code})"
                )
            agent_card = response.json()


        verifier = SignatureVerifier()
        if verifier.jwks is None:
            return "Signature verification skipped: no JWKS configured"

        ok, details = verifier.verify(agent_card)
        return ("Signatures valid\n\n" if ok else "Signatures invalid\n\n") + json.dumps(details, indent=2)

    except httpx.RequestError as e:
        raise Exception(f"Network error retrieving agent card: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in agent card: {e}")


if __name__ == "__main__":
    mcp.run()

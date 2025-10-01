#!/usr/bin/env python3
"""
This is a mock agent, meant to return static responses to queries.

Its purpose is to help debug multi-agent architectures by acting as
a constant in the system.
"""
from __future__ import annotations
import argparse
import logging
import os
import json
import yaml
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

# Import A2A SDK components from their specific modules
from a2a.types import AgentCard, AgentSkill, AgentCapabilities, AgentCardSignature
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import new_agent_text_message

# JWS signing
from authlib.jose.rfc7515.jws import JsonWebSignature
from authlib.jose.rfc7517.jwk import JsonWebKey

# Set up logging
logger = logging.getLogger(__name__)

# Global store for published JWKS (if enabled)
PUBLISHED_JWKS: Optional[Dict[str, Any]] = None


class StatusKB:
    def __init__(self, text: str):
        # Store lines with simple normalization
        self.text: str = text

    @classmethod
    def from_file(cls, path: Path) -> "StatusKB":
        return cls(path.read_text(encoding="utf-8"))


class MockAgent:
    def __init__(self, kb: StatusKB):
        self.kb = kb

    async def answer(self, question: str) -> str:
        _ = question
        return f"{self.kb.text}"


class MockAgentExecutor(AgentExecutor):
    """Bridges A2A protocol <-> MockAgent business logic.

    The SDK passes a RequestContext and an EventQueue. We extract the user's
    text question from the context, query the KB, then enqueue a single
    agent Message as a response.
    """

    def __init__(self, agent: MockAgent):
        self.agent = agent

    # The SDK calls this for message/send and message/stream
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        user_text = context.get_user_input()
        result = await self.agent.answer(user_text)
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception(
            f"cancel not supported, args: {context} event_queue: {event_queue}"
        )


class SigningError(Exception):
    """Raised when agent card signing fails."""
    pass


def _load_signing_key() -> JsonWebKey:
    """Load or generate a signing key based on environment configuration."""
    jwk_json = os.getenv("A2A_SIGNING_JWK_JSON")
    jwk_path = os.getenv("A2A_SIGNING_JWK_PATH")
    fail_if_no_key = os.getenv("A2A_FAIL_IF_NO_SIGNING_KEY", "false").lower() in ("1", "true", "yes")

    if jwk_json:
        try:
            return JsonWebKey.import_key(json.loads(jwk_json), options={"use": "sig"})
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            raise SigningError(f"Invalid JWK JSON in A2A_SIGNING_JWK_JSON: {e}") from e

    elif jwk_path and os.path.exists(jwk_path):
        try:
            with open(jwk_path, "r", encoding="utf-8") as f:
                raw = f.read()
            try:
                jwk_dict = json.loads(raw)
                return JsonWebKey.import_key(jwk_dict, options={"use": "sig"})
            except (json.JSONDecodeError, ValueError, KeyError):
                # Fall back to treating file as PEM
                return JsonWebKey.import_key(raw, options={"use": "sig"})
        except (OSError, IOError) as e:
            raise SigningError(f"Failed to read signing key from {jwk_path}: {e}") from e
    else:
        if fail_if_no_key:
            raise SigningError("A2A_FAIL_IF_NO_SIGNING_KEY=true but no signing key provided via A2A_SIGNING_JWK_JSON or A2A_SIGNING_JWK_PATH")
        logger.info("Generating new RSA key for signing")
        return JsonWebKey.generate_key("RSA", 2048, options={"kid": "mock-agent-key", "use": "sig", "alg": "RS256"}, is_private=True)


def _sign_agent_card(card: AgentCard, base_url: str) -> Tuple[AgentCard, Optional[Dict[str, Any]]]:
    """Sign an agent card and optionally prepare JWKS for publishing."""
    logger.info("Signing agent card")

    # Remove signatures before serialization
    payload = card.model_dump(mode="json", exclude_none=True)
    payload.pop("signatures", None)
    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    # Load or generate signing key
    key = _load_signing_key()

    kid = os.getenv("A2A_SIGNING_KID") or key.as_dict(is_private=False).get("kid") or "mock-agent-key"
    alg = os.getenv("A2A_SIGNING_ALG") or "RS256"

    logger.info(f"Signing with kid: {kid}, alg: {alg}")

    # Determine JWKS URL for jku header if available
    configured_jwks_url = os.getenv("A2A_JWKS_URL")
    # If not configured, but we plan to publish locally, point to local well-known
    if not configured_jwks_url and os.getenv("A2A_PUBLISH_JWKS", "false").lower() in ("1", "true", "yes"):
        configured_jwks_url = f"{base_url}/.well-known/jwks.json"

    protected_hdr = {"alg": alg, "kid": kid}
    if configured_jwks_url:
        protected_hdr["jku"] = configured_jwks_url

    jws = JsonWebSignature()
    jws_flat = jws.serialize_json({"protected": protected_hdr}, payload_str, key)

    card.signatures = [
        AgentCardSignature(
            protected=jws_flat["protected"],
            signature=jws_flat["signature"],
        )
    ]

    # Optionally prepare JWKS to publish alongside the agent
    jwks_data = None
    if os.getenv("A2A_PUBLISH_JWKS", "false").lower() in ("1", "true", "yes"):
        jwks_data = {"keys": [key.as_dict(is_private=False)]}
        logger.info("Prepared JWKS for publishing")

    return card, jwks_data


def load_agent_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load agent configuration from YAML file or environment variable."""
    def _try_load(path):
        try:
            if path and Path(path).is_file():
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to read config from {path}: {e}")

    # Try config_path (if file), then CONFIG_FILE env var (if file)
    result = _try_load(str(config_path) if config_path else None) or _try_load(os.getenv("CONFIG_FILE"))
    if result:
        return result

    # Return default config if no file specified or file doesn't exist
    return {
        "agent": {
            "name": "mock-agent",
            "description": "A mock agent, used for testing agentic systems.",
            "version": "0.1.0",
            "capabilities": {},
            "default_input_modes": ["text/plain"],
            "default_output_modes": ["text/plain"],
            "skills": [
                {
                    "id": "status-query",
                    "name": "Query status log",
                    "description": "Find status lines relevant to a user question.",
                    "input_modes": ["text/plain"],
                    "output_modes": ["text/plain"],
                    "tags": ["query", "status"],
                }
            ],
        },
        "knowledge_base": {"file": "./data/default", "type": "text"},
    }


def build_agent_card(base_url: str, config: Dict[str, Any]) -> AgentCard:
    """Build agent card from configuration and optionally sign it."""
    agent_config = config["agent"]

    # Build skills from config
    skills = []
    for skill_config in agent_config.get("skills", []):
        skills.append(
            AgentSkill(
                id=skill_config["id"],
                name=skill_config["name"],
                description=skill_config["description"],
                input_modes=skill_config["input_modes"],
                output_modes=skill_config["output_modes"],
                tags=skill_config.get("tags", []),
            )
        )

    card = AgentCard(
        name=agent_config["name"],
        description=agent_config["description"],
        version=agent_config["version"],
        url=base_url,
        capabilities=AgentCapabilities(),
        default_input_modes=agent_config["default_input_modes"],
        default_output_modes=agent_config["default_output_modes"],
        skills=skills,
    )

    # Optionally sign the AgentCard using env-provided JWK or generated RSA key
    if os.getenv("A2A_SIGN_CARD", "false").lower() in ("1", "true", "yes"):
        try:
            card, jwks_data = _sign_agent_card(card, base_url)
            if jwks_data:
                global PUBLISHED_JWKS
                PUBLISHED_JWKS = jwks_data
        except SigningError as e:
            logger.error(f"Failed to sign agent card: {e}")
            raise

    return card


def get_base_url(host: str, port: int) -> str:
    """Determine the base URL for the agent card."""
    # Input validation
    if not host or not isinstance(host, str):
        raise ValueError("host must be a non-empty string")
    if not isinstance(port, int) or port <= 0 or port > 65535:
        raise ValueError("port must be a valid integer between 1 and 65535")

    # Check for explicit BASE_URL environment variable first
    if base_url := os.getenv("BASE_URL"):
        if not base_url.strip():
            raise ValueError("BASE_URL environment variable is empty")
        return base_url.strip()

    # Check for OpenShift route hostname (set by operator/deployment)
    if route_host := os.getenv("OPENSHIFT_ROUTE_HOST"):
        if not route_host.strip():
            raise ValueError("OPENSHIFT_ROUTE_HOST environment variable is empty")
        return f"https://{route_host.strip()}"

    # Fallback to host:port for local development
    return f"http://{host}:{port}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config",
        type=Path,
        help="Path to agent config YAML file (overrides CONFIG_FILE env var)",
    )
    ap.add_argument(
        "--kb",
        type=Path,
        help="Path to status text file (overrides KB_FILE env var and config)",
    )
    ap.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "10000")))
    ap.add_argument(
        "--base-url", help="Override base URL (auto-detected if not provided)"
    )
    args = ap.parse_args()

    # Load agent configuration
    config_path = args.config
    config = load_agent_config(config_path)

    # Determine KB file path - command line > env var > config file > default
    if args.kb:
        kb_path = args.kb
    elif os.getenv("KB_FILE"):
        kb_path = Path(os.getenv("KB_FILE"))
    else:
        kb_path = Path(config["knowledge_base"]["file"])

    kb = StatusKB.from_file(kb_path)
    agent = MockAgent(kb)
    executor = MockAgentExecutor(agent)

    # Determine base URL
    base_url = args.base_url or get_base_url(args.host, args.port)

    # Wire A2A server
    task_store = InMemoryTaskStore()
    http_handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)
    card = build_agent_card(base_url, config)
    app = A2AFastAPIApplication(agent_card=card, http_handler=http_handler)

    print(f"Serving A2A Mock Agent on {args.host}:{args.port}")
    print("Agent card at /.well-known/agent.json")

    import uvicorn

    fastapi_app = app.build()
    # If publishing JWKS is enabled, add a well-known JWKS endpoint
    if os.getenv("A2A_PUBLISH_JWKS", "false").lower() in ("1", "true", "yes"):
        from fastapi import Response

        def get_jwks():
            global PUBLISHED_JWKS
            # If a JWKS is provided via env/path, serve that; otherwise serve generated one
            jwks_json_env = os.getenv("A2A_JWKS_JSON")
            jwks_path = os.getenv("A2A_JWKS_PATH")
            body: Optional[str] = None
            if jwks_json_env:
                body = jwks_json_env
            elif jwks_path and os.path.exists(jwks_path):
                body = Path(jwks_path).read_text(encoding="utf-8")
            elif PUBLISHED_JWKS is not None:
                body = json.dumps(PUBLISHED_JWKS)
            else:
                body = json.dumps({"keys": []})
            return Response(content=body, media_type="application/json")

        fastapi_app.add_api_route("/.well-known/jwks.json", get_jwks, methods=["GET"])

    uvicorn.run(fastapi_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

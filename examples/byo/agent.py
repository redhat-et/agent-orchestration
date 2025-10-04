#!/usr/bin/env python3
"""
BYO (Bring Your Own) Mock Agent

A mock agent that returns canned responses based on configuration.
Useful for testing agentic systems without requiring live data sources.
"""
from __future__ import annotations
import argparse
import json
import os
import yaml
from pathlib import Path
from typing import Dict, Any

# Import A2A SDK components
from a2a.types import AgentCard, AgentSkill, AgentCapabilities
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import new_agent_text_message


class MockAgent:
    def __init__(self, response_data: str):
        # Store the mock response as a formatted string (JSON or text)
        self.response_data: str = response_data

    async def answer(self, question: str) -> str:
        return self.response_data


class MockAgentExecutor(AgentExecutor):
    """Bridges A2A protocol <-> MockAgent business logic."""

    def __init__(self, agent: MockAgent):
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        user_text = context.get_user_input()
        result = await self.agent.answer(user_text)
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception(
            f"cancel not supported, args: {context} event_queue: {event_queue}"
        )


def load_agent_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load agent configuration from YAML file."""
    if config_path and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

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
        "mock_response": "Default mock response: The agent is operational.",
    }


def build_agent_card(base_url: str, config: Dict[str, Any]) -> AgentCard:
    """Build agent card from configuration."""
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

    return AgentCard(
        name=agent_config["name"],
        description=agent_config["description"],
        version=agent_config["version"],
        url=base_url,
        capabilities=AgentCapabilities(),
        default_input_modes=agent_config["default_input_modes"],
        default_output_modes=agent_config["default_output_modes"],
        skills=skills,
    )


def get_base_url(host: str, port: int) -> str:
    """Determine the base URL for the agent card."""
    # Check for explicit BASE_URL environment variable first
    if base_url := os.getenv("BASE_URL"):
        return base_url

    # Check for OpenShift route hostname (set by operator/deployment)
    if route_host := os.getenv("OPENSHIFT_ROUTE_HOST"):
        return f"https://{route_host}"

    # Fallback to host:port for local development
    return f"http://{host}:{port}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config",
        type=Path,
        help="Path to agent config YAML file (overrides CONFIG_FILE env var)",
    )
    ap.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    ap.add_argument(
        "--base-url", help="Override base URL (auto-detected if not provided)"
    )
    args = ap.parse_args()

    # Load agent configuration from --config arg or CONFIG_FILE env var
    config_path = args.config or (Path(os.getenv("CONFIG_FILE")) if os.getenv("CONFIG_FILE") else None)
    config = load_agent_config(config_path)

    # Get mock response from config
    # If it's a dict/list (JSON data), format it as JSON string
    # If it's already a string, use it as-is
    mock_response = config.get("mock_response", "No response data configured.")
    if isinstance(mock_response, (dict, list)):
        response_data = json.dumps(mock_response, indent=2)
    else:
        response_data = str(mock_response)

    agent = MockAgent(response_data)
    executor = MockAgentExecutor(agent)

    # Determine base URL
    base_url = args.base_url or get_base_url(args.host, args.port)

    # Wire A2A server
    task_store = InMemoryTaskStore()
    http_handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)
    card = build_agent_card(base_url, config)
    app = A2AFastAPIApplication(agent_card=card, http_handler=http_handler)

    # Add health endpoint for kagent readiness probe
    fastapi_app = app.build()

    @fastapi_app.get("/health")
    async def health():
        return {"status": "healthy"}

    print(f"Serving A2A Mock Agent on {args.host}:{args.port}")
    print("Agent card at /.well-known/agent.json")
    print("Health check at /health")

    import uvicorn

    uvicorn.run(fastapi_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

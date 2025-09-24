#!/usr/bin/env python3
"""
This is a mock agent, meant to return static responses to queries. 

Its purpose is to help debug multi-agent architectures by acting as
a constant in the system.
"""
from __future__ import annotations
import argparse
import os
import re
import yaml
from pathlib import Path
from typing import Iterable, List, Tuple, Dict, Any, Optional

# Import A2A SDK components from their specific modules
from a2a.types import AgentCard, AgentSkill, AgentCapabilities
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import new_agent_text_message


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
        raise Exception(f"cancel not supported, args: {context} event_queue: {event_queue}")


def load_agent_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load agent configuration from YAML file."""
    if config_path and config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    # Return default config if no file specified or file doesn't exist
    return {
        'agent': {
            'name': 'mock-agent',
            'description': 'A mock agent, used for testing agentic systems.',
            'version': '0.1.0',
            'capabilities': {},
            'default_input_modes': ['text/plain'],
            'default_output_modes': ['text/plain'],
            'skills': [{
                'id': 'status-query',
                'name': 'Query status log',
                'description': 'Find status lines relevant to a user question.',
                'input_modes': ['text/plain'],
                'output_modes': ['text/plain'],
                'tags': ['query', 'status']
            }]
        },
        'knowledge_base': {
            'file': './data/default',
            'type': 'text'
        }
    }


def build_agent_card(base_url: str, config: Dict[str, Any]) -> AgentCard:
    """Build agent card from configuration."""
    agent_config = config['agent']

    # Build skills from config
    skills = []
    for skill_config in agent_config.get('skills', []):
        skills.append(AgentSkill(
            id=skill_config['id'],
            name=skill_config['name'],
            description=skill_config['description'],
            input_modes=skill_config['input_modes'],
            output_modes=skill_config['output_modes'],
            tags=skill_config.get('tags', [])
        ))

    return AgentCard(
        name=agent_config['name'],
        description=agent_config['description'],
        version=agent_config['version'],
        url=base_url,
        capabilities=AgentCapabilities(),  # use default empty capabilities
        default_input_modes=agent_config['default_input_modes'],
        default_output_modes=agent_config['default_output_modes'],
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
    ap.add_argument("--config", type=Path, help="Path to agent config YAML file (overrides CONFIG_FILE env var)")
    ap.add_argument("--kb", type=Path, help="Path to status text file (overrides KB_FILE env var and config)")
    ap.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "10000")))
    ap.add_argument("--base-url", help="Override base URL (auto-detected if not provided)")
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
        kb_path = Path(config['knowledge_base']['file'])

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
    uvicorn.run(fastapi_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

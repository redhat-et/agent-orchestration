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
from pathlib import Path
from typing import Iterable, List, Tuple

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


def build_agent_card(base_url: str) -> AgentCard:
    return AgentCard(
        name="status-update-bot",
        description="Answers questions from a KnowledgeBase consisting of team/contributor status updates.",
        version="0.1.0",
        url=base_url,
        capabilities=AgentCapabilities(),  # use default empty capabilities
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="status-query",
                name="Query status log",
                description="Find status lines relevant to a user question.",
                input_modes=["text/plain"],
                output_modes=["text/plain"],
                tags=["query", "status"],
            )
        ],
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
    ap.add_argument("--kb", type=Path, help="Path to status text file (overrides KB_FILE env var)")
    ap.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "10000")))
    ap.add_argument("--base-url", help="Override base URL (auto-detected if not provided)")
    args = ap.parse_args()

    # Use KB_FILE env var if --kb not provided
    kb_path = args.kb or Path(os.getenv("KB_FILE", "./data/cdn-xy-zz-0009-debug-agent.txt"))
    kb = StatusKB.from_file(kb_path)
    agent = MockAgent(kb)
    executor = MockAgentExecutor(agent)

    # Determine base URL
    base_url = args.base_url or get_base_url(args.host, args.port)

    # Wire A2A server
    task_store = InMemoryTaskStore()
    http_handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)
    card = build_agent_card(base_url)
    app = A2AFastAPIApplication(agent_card=card, http_handler=http_handler)

    print(f"Serving A2A Status Bot on {args.host}:{args.port}")
    print("Agent card at /.well-known/agent.json")

    import uvicorn
    fastapi_app = app.build()
    uvicorn.run(fastapi_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

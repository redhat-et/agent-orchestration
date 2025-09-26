# Agent Runtime for OpenShift AI: Design Overview

## Purpose

Provide a first-class runtime for packaging, deploying, discovering, and invoking AI agents on Kubernetes/OpenShift. Standardize the agent container contract and expose a stable bridge for IDEs and services.

## Audience & Scope
- Kubernetes/OpenShift users exploring how agents become first-class resources.
- MLOps Engineers interested in uniformly deploying and managing agent lifcycle.

## Problem
- Agents are ad-hoc processes with undefined contracts.
- Teams lack a registry for "what agents exist, who owns them, and how to call them."
- Ops needs consistent health, metrics, security, and upgrades.

## Goals
- Declarative deploy of agents via CRDs.
- Uniform agent contract: card, health, metrics.
- Discovery by capability/skill and owner.
- Invocation through a stable MCP bridge (interact with agents via IDE).
- Secure by default and observable.

## Non-Goals
- Define one "true" agent framework.
- Prescribe a single agent execution engine or SDK; we validate the contract, not the runtime.

## Architecture at a Glance
### Agent Operator (`agent-operator/`)
- Defines the `Agent` CustomResource and a prototype controller that lazily discovers agents labelled with `ai.openshift.io/agent.*`.
- On `oc get agents`, the controller resolves live endpoints, hydrates status with the agent card, and returns up-to-date metadata without persisting state.
- Future work: hardened reconciliation loop, packaging for OLM, RBAC tightening.

### Mock Agents (`mock_agent/`)
- Lightweight FastAPI services that implement the runtime contract and ship representative payloads from `mock_agent/data/`.
- Deployment scripts (`deploy.sh`, `teardown.sh`) exercise the contract end-to-end against OpenShift routes.
- Use these samples as conformance references when authoring your own containers.

### MCP Bridge (`mcp/oc_agent_bridge.py`)
- FastMCP server that lists agents via the Operator and relays A2A protocol messages.
- Validates the card endpoint (`/.well-known/agent.json`) and optionally probes health to surface actionable metadata to developers.
- Acts as the join point between OpenShift discovery and external agent clients.

## Agent Runtime Contract
Every compliant agent image must expose three HTTP endpoints:
- `/.well-known/agent.json` — versioned agent card describing capabilities and skills.
- `/healthz` — readiness/liveness probe returning HTTP 200 when the agent is ready.
- `/metrics` — Prometheus-format metrics for platform observability.

### Agent Card Shape
Cards follow the [A2A](https://github.com/ai-actions/a2a) AgentCard schema. 

The Operator relies on `ai.openshift.io/agent.class` and `ai.openshift.io/agent.name` labels to locate agent pods and annotate returned Agent resources with the card contents.

## Control Flow
1. Developer deploys an agent image with the required labels and contract endpoints.
2. The Agent Operator serves `oc get agents`, fetching each agent's card and exposing phase, version, and endpoint data in the CR status.
3. The MCP bridge consumes the CR data, enriches results, and exposes discovery/messaging tools to clients (e.g. IDEs).
4. Users interact with agents through the A2A protocol; responses are backed by the live agent container.

## Roadmap Threads
- **Security & Trust**: TLS termination, signed cards, and attestation of Agent images.
- **Operator Hardening**: Stateful reconciliation, drift detection, and multi-tenant safety.
- **Conformance Tooling**: Automated contract checks and reusable base images for agent authors.
- **Documentation**: Expand `docs/presentations/` slides into task-focused guides. 

## Related Reading
- Quick starts and repository map: `../README.md`.
- Operator implementation details: `agent-operator/README.md` and `agent-operator/controller.py`.
- MCP bridge implementation: `mcp/oc_agent_bridge.py` (see inline docstrings for tool usage).

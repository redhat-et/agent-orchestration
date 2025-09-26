# First Class Agents in OpenShift (Proof of Concept)

## Status
- **Proof of concept only.** The repo demonstrates a potential agent contract and operator flow; it is **not** production ready.
- **Mock agents.** All agents in `mock_agent/` are synthetic services to illustrate the deployment and discovery contract we intend to enforce.
- **Security/integration gaps.** Auth, RBAC, hardened reconcilers, and polished docs are still in flight.
- The core features here overlap with [Kagenti](https://github.com/kagenti/kagenti), we are investigating implementing the features demonstrated here via integration between Kagenti and OpenShift. See: Issue redhat-et/agent-orchestration#12

## What This Repo Demonstrates
- Turning agent workloads into **first-class Kubernetes resources** via an `Agent` CRD and controller.
- Defining a **uniform runtime contract** (`/.well-known/agent.json`, `/healthz`, `/metrics`) that any compliant agent image must satisfy.
- Bridging OpenShift agents into developer tooling through an **MCP server** that discovers agents and relays A2A protocol messages.

## Quick Start Pathways
### 1. OpenShift Cluster Experiment
1. Install the Agent CRD and demo operator: `cd agent-operator && oc apply -f agent-crd.yaml` (plus the controller manifest once hardened).
2. Deploy a mock agent: `cd mock_agent && ./deploy.sh <AGENT_NAME>` (names map to files in `mock_agent/data/`).
3. Verify discovery via `oc get agents` and interact through the MCP bridge.
4. Optionally, clean up with `mock_agent/teardown.sh`.

### 1. MCP Integration
1. Install Python 3.13+ and [uv](https://github.com/astral-sh/uv) or `pip`.
2. Run `uv sync` (or `pip install -e .`) to pull dependencies.
3. Start the MCP bridge: `cd mcp && python oc_agent_bridge.py`.
4. Use the bridge with your IDE or CLI (e.g. `claude mcp add`) to list and message the mock agents.

> ⚠️ Treat all cluster steps as disposable demos. Hardened manifests, RBAC, and signing workflows are still future work.

## Current Capabilities
- Discover mock agents labeled with `ai.openshift.io/agent.*` and surface their cards.
- Enforce the draft endpoint contract through deployment scripts and sample responses.
- Relay user messages to mock agents via the A2A protocol using the MCP bridge.

## Major Gaps Before Dev Preview
- Security & trust foundations (TLS, signed cards, RBAC).
- Operator hardening (stateful reconciliation, OLM packaging).
- Conformance tooling and reusable agent base images.

## Learn More
- Architecture and positioning slides: `docs/presentations/demo/`.
- Design overview and goals: `docs/README.md`.

## Contributing & Feedback
This is an exploratory project, file issues or PRs to discuss the contract, operator shape, or feature expectations.

# First Class Agents in OpenShift (Proof of Concept)

This proof-of-concept demonstrates how to make AI agents first-class citizens in OpenShift through:
- **Agent CRD**: Kubernetes-native resources for deploying and managing agents
- **A2A Protocol**: Standardized agent-to-agent communication protocol
- **MCP Bridge**: Integration with developer tools via Model Context Protocol
- **Signature Verification**: Cryptographic verification of agent identity and integrity

> ⚠️ **Not production ready.** This is an exploratory project demonstrating potential patterns for agent deployment, discovery, and trust.

## What This Demonstrates
- **First-class Kubernetes resources** via an `Agent` CRD and controller
- **Uniform runtime contract** (`/.well-known/agent.json`, `/healthz`, `/metrics`) that compliant agents must satisfy
- **MCP server** that discovers agents and relays A2A protocol messages to IDEs and developer tools
- **Agent card signatures** using JWS for verifying agent authenticity

> 💡 The core features overlap with [Kagenti](https://github.com/kagenti/kagenti). We are exploring integration options. See Issue redhat-et/agent-orchestration#12

## Quick Start

Choose your path:
1. **[Signature Verification Demo](#signature-verification-quickstart)** - Test agent card signing and verification locally or on a cluster
2. **[Basic OpenShift Deployment](#openshift-cluster-quickstart)** - Deploy agents to OpenShift and discover them via MCP
3. **[MCP Integration Only](#mcp-integration)** - Connect your IDE to discover and message agents

### Prerequisites
- Python 3.13+ and [uv](https://github.com/astral-sh/uv) (or `pip`)
- OpenShift cluster access (for cluster demos)
- MCP-compatible IDE or CLI (for agent messaging)

---

### OpenShift Cluster Quickstart

Deploy agents to OpenShift and discover them via the MCP bridge.

```bash
# 0) Install dependencies (first time only)
uv sync  # or: pip install -e .

# 1) Install the Agent CRD
cd agent-operator
oc apply -f agent-crd.yaml

# 2) Deploy a mock agent (choose from: security-monitoring-agent, database-performance-monitor, etc.)
cd ../mock_agent
./deploy.sh security-monitoring-agent

# 3) Verify the agent was created
oc get agents

# 4) Start the MCP bridge to interact with deployed agents
cd ../mcp
python oc_agent_bridge.py

# In your MCP client/IDE, use these tools:
# - list_agents() to see all deployed agents
# - send_message_to_agent(agent_url="https://<agent-host>", message="your query")
```

**Available mock agents** (in `mock_agent/data/`):
- `security-monitoring-agent`
- `database-performance-monitor`
- `application-performance-monitor`
- `kubernetes-cluster-monitor`
- `cicd-pipeline-monitor`
- `message-queue-monitor`

**Optional:** Enable signature verification by adding `--jwks-url` when deploying (see [Signature Verification Quickstart](#signature-verification-quickstart)).

**Cleanup:**
```bash
cd mock_agent
./teardown.sh <AGENT_NAME>
```

---
### Signature Verification Quickstart

Try agent card signing and cryptographic verification on a cluster.

**Cluster demo (with central JWKS):**

```bash
# 1) Deploy a central JWKS service to your OpenShift project
cd mock_agent
./setup_central_jwks.sh

# 2) Deploy a signed agent that references the central JWKS
./deploy.sh security-monitoring-agent --jwks-url https://<jwks-host>/.well-known/jwks.json

# 3) Run the MCP bridge and verify against the central JWKS
cd ../mcp
export A2A_TRUSTED_JWKS_URL=https://<jwks-host>/.well-known/jwks.json
python oc_agent_bridge.py

# In your MCP client/IDE, call the tool:
# verify_agent_card_signature(agent_url="https://<agent-route-host>")
```
---

### MCP Integration

Connect your IDE or CLI to discover and message agents.

```bash
# 1) Install dependencies
uv sync  # or: pip install -e .

# 2) Start the MCP bridge
cd mcp
python oc_agent_bridge.py

# 3) Add to your IDE (e.g., Claude Desktop)
# Add to your MCP settings or use: claude mcp add
```

**Available MCP tools:**
- `discover_agents()` - Find all agents in your OpenShift cluster
- `list_agents()` - Get a summary table of agents
- `get_agent_card(agent_url)` - Retrieve an agent's card
- `send_message_to_agent(agent_url, message)` - Send a message to an agent
- `verify_agent_card_signature(agent_url)` - Verify agent card signatures

---

## Configuration Reference

### Environment Variables

#### Agent-Side Configuration

**Signing Control**

| Variable | Description | Default |
|----------|-------------|---------|
| `A2A_SIGN_CARD` | Enable agent card signing | `false` |
| `A2A_FAIL_IF_NO_SIGNING_KEY` | Fail if no signing key provided | `false` |

**Signing Key Configuration** (priority: JSON → Path → Auto-generate)

| Variable | Description | Default |
|----------|-------------|---------|
| `A2A_SIGNING_JWK_JSON` | Inline private JWK JSON | - |
| `A2A_SIGNING_JWK_PATH` | Path to private JWK or PEM file | Auto-generated RSA-2048 |
| `A2A_SIGNING_KID` | Override key ID in JWS header | From key |
| `A2A_SIGNING_ALG` | JWS algorithm | `RS256` |

**JWKS Publishing** (for signature verification by others)

| Variable | Description | Default |
|----------|-------------|---------|
| `A2A_JWKS_URL` | Public JWKS URL to advertise (in `jku` header) | - |
| `A2A_PUBLISH_JWKS` | Serve `/.well-known/jwks.json` endpoint locally | `false` |
| `A2A_JWKS_JSON` | Inline JWKS JSON for local publishing | - |
| `A2A_JWKS_PATH` | Path to JWKS file for local publishing | Uses signing key |

**Agent Runtime**

| Variable | Description | Default |
|----------|-------------|---------|
| `BASE_URL` | Manual base URL override | Derived from host:port |
| `OPENSHIFT_ROUTE_HOST` | Cluster route hostname (set by `deploy.sh`) | - |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `10000` |

---

#### MCP Bridge Configuration

**Trusted JWKS Configuration** (priority: JSON → Path → URL)

| Variable | Description | Default |
|----------|-------------|---------|
| `A2A_TRUSTED_JWKS_JSON` | Inline trusted JWKS JSON | - |
| `A2A_TRUSTED_JWKS_PATH` | Path to trusted JWKS file | - |
| `A2A_TRUSTED_JWKS_URL` | URL to fetch trusted JWKS | - |

**Verification Policy**

| Variable | Description | Default |
|----------|-------------|---------|
| `A2A_REQUIRE_VERIFIED_CARD` | Reject agents with invalid/missing signatures | `false` |

**Security Settings** (testing only - do not use in production)

| Variable | Description | Default |
|----------|-------------|---------|
| `A2A_INSECURE_SKIP_TLS_VERIFY` | Skip TLS certificate verification | `false` |
| `A2A_INSECURE_ALLOW_HTTP_JKU` | Allow HTTP URLs in `jku` header | `false` |

---

## Architecture & Design

### Key Concepts

**Agent CRD**: Kubernetes Custom Resource Definition that makes agents first-class cluster resources with spec, status, and lifecycle management.

**A2A Protocol**: Agent-to-Agent communication protocol with standardized message format, streaming support, and task management.

**Agent Card**: JSON document at `/.well-known/agent.json` describing agent capabilities, skills, and API surface. Optionally signed with JWS.

**MCP Bridge**: Model Context Protocol server that translates between MCP tools and A2A protocol, enabling IDE integration.

### Limitations & Future Work

**Current gaps:**
- No production-ready authentication or RBAC
- Agent controller is a demo (lacks stateful reconciliation, OLM packaging)
- No conformance testing or reusable base images
- Signature verification relies on pre-shared trust (JWKS URLs)

**Planned improvements:**
- Integration with [Kagenti](https://github.com/kagenti/kagenti) for agent orchestration
- Hardened operator with proper reconciliation loop
- Agent base images with built-in A2A support
- Enhanced trust model with certificate authorities

---

## Additional Resources

- **Architecture slides**: `docs/presentations/demo/`
- **Design overview**: `docs/README.md`
- **Related project**: [Kagenti](https://github.com/kagenti/kagenti) - Agent orchestration framework

## Contributing

This is an exploratory project. We welcome:
- Issues discussing the agent contract, operator design, or feature ideas
- PRs improving documentation, demos, or proof-of-concept implementations
- Feedback on integration patterns with existing tools

File issues or PRs at the repository to join the discussion.

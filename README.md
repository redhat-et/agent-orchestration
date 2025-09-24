# OpenShift Dynamic Agent Patterns (Proof of Concept)

## Note

A production agent discovery pattern needs at least basic security. We also have no stable best practices for deployment of agents. This is only a rough exploration of the possible implementation and use cases of combining OpenShift and A2A protocols.

## About

This project demonstrates how to build **durable, standards-aligned patterns** for agentic systems using OpenShift as the substrate. The goal is to leverage OpenShift's existing primitives to integrate all layers of the AI agent stack, including discovery, messaging, and orchestration.

### Vision: Agents as First-Class Resources

OpenShift provides the perfect substrate for **durable agent models** where agents become **self-documenting, conversational APIs** for clusters. This project implements:

- **Agent CRD**: Define agents as first-class Kubernetes resources
- **A2A Protocol Integration**: Wrap Agent-to-Agent communication practices into Kubernetes API objects
- **MCP Server**: Discovers agents, surfaces capabilities, and enables communication via A2A
- **Digital Twin Pattern**: Agents provide intelligent, self-describing interfaces to cluster resources

## Prerequisites

- OpenShift cluster access with `oc` CLI installed
- Python 3.13 or later
- uv package manager (recommended) or pip
- Agent CRD installed in your cluster (see agent-operator directory)

## Setup

1. Clone this repository and navigate to the demo directory
2. Install dependencies:
   ```bash
   uv sync
   ```
   Or with pip:
   ```bash
   pip install -e .
   ```

## Deployment

### 1. Install Agent CRD

First, install the Agent Custom Resource Definition in your OpenShift cluster:

```bash
cd agent-operator
oc apply -f agent-crd.yaml
```

### 2. Deploy Mock Agent

To deploy a mock agent to your OpenShift cluster:

1. Log into your OpenShift cluster:
   ```bash
   oc login
   ```

2. Navigate to the mock agent directory:
   ```bash
   cd mock_agent
   ```

note: AGENT_NAME should match the name of a datafile in the data directory minus the `.txt` extension.
This allows the mock agent to know which flat file to serve when sending a response.

3. Deploy the agent:
   ```bash
   ./deploy.sh {AGENT_NAME}
   ```

The deployment script will:
- Create a build configuration
- Build and deploy the container image
- Set up the service and route
- Configure A2A discovery labels
- Verify the deployment

### 3. Run the MCP Server for Agent Discovery

The MCP server provides tools for discovering and interacting with A2A agents using the Agent CRD:

```bash
cd mcp
python oc_agent_bridge.py
```

This server provides the following capabilities:
- Discover A2A agents in OpenShift clusters using native `oc get agents`
- Retrieve agent cards from discovered agents
- Send messages to agents via the A2A protocol
- Stream responses from agents

### Using with Claude Code

The MCP server can be integrated with Claude Code for interactive agent discovery and communication:

```bash
claude mcp add oc-agent-discovery python /path/to/your/project/mcp/oc_agent_bridge.py
```

This integration allows you to discover and interact with A2A agents directly from Claude Code using the MCP tools.

### 4. Verify Deployment

Check that your agent is running and accessible:

```bash
# Check agent CRs
oc get agents

# Check pod status (replace {agent-name} with your deployed agent)
oc get pods -l app={agent-name}

# View logs
oc logs -l app={agent-name} -f

# Test agent card endpoint
curl -k https://$(oc get route {agent-name} -o jsonpath='{.spec.host}')/.well-known/agent.json
```

## Agent Discovery

Agents are discovered using the Agent CRD with these labels:
- `ai.openshift.io/agent.class: "a2a"` - Marks the resource as an A2A agent
- `ai.openshift.io/agent.name: "<agent-name>"` - Agent identifier

The MCP server uses `oc get agents` to discover agents and retrieves their capabilities through agent cards served at `/.well-known/agent.json`.

## Cleanup

To remove deployed agents:

```bash
cd mock_agent
./teardown.sh {agent-name}
```

## Usage Examples

Once deployed, you can discover and interact with agents using the MCP tools:

1. **List all discovered agents**: Use `discover_agents` tool to find all Agent CRs
2. **Get agent cards**: Retrieve agent capabilities and metadata
3. **Send messages to agents**: Communicate via A2A protocol
4. **Stream responses from agents**: Receive real-time responses

## Project Structure

```
.
├── agent-operator/          # Agent CRD and controller
│   ├── agent-crd.yaml      # Agent Custom Resource Definition
│   └── controller.py       # Agent controller implementation
├── mcp/                    # MCP server for agent discovery
│   └── oc_agent_bridge.py  # fastmcp-based discovery server
├── mock_agent/             # Mock agent implementation
│   ├── agent.py           # A2A-compliant mock agent
│   ├── deploy.sh          # Deployment script
│   ├── configs/           # Agent configurations
│   └── data/              # Mock data files
└── docs/                  # Documentation and presentations
```

The system demonstrates how A2A-compliant agents can be dynamically discovered and utilized within OpenShift environments using native Kubernetes primitives.

## Big Picture Architecture

```text
+=========================================================================+
|              Kubernetes / OpenShift Cluster (agentized)                 |
+=========================================================================+
|                                                                         |
|  +---------------- Agent Resource (CRD: Agent) ----------------------+  |
|  | name: <agent-name>                                                 | |
|  |                                                                    | |
|  |  +------------+                             +-------------------+  | |
|  |  | AGENT CARD |<==== A2A / ACP messages ===>| Other Agents/     |  | |
|  |  |  (signed)  |  (routing, identity, prov.) | Services          |  | |
|  |  +-----+------+                             +-------------------+  | |
|  |        | exposes: /card  /invoke  /metrics  /health                | |
|  |        v                                                           | |
|  |  +----------------+      MCP tool negotiation      +------------+  | |
|  |  |   MCP SERVER   | <----------------------------> |  TOOLS/APIs|  | |
|  |  +--------+-------+                                +------------+  | |
|  |           |  /metrics                                              | |
|  |           v                                                        | |
|  |     Observability -----> Prometheus / Grafana                      | |
|  +---------------------------------------------------------------------+|
|                                                                         |
|   ^ Deployment Path       ^ Security/Provenance       ^ Discovery       |
|   | (OCI image -> CRD +   | (RBAC, signed cards,      | (Registry /     |
|   |  Controller reconcile)|  key trust)               |  Card Index)    |
|   +-----------------------+---------------------------+-----------------+
|      Controller syncs cards using labels or registry integration        |
+=========================================================================+
```

## Example Run

The following shows a demo of this concept, integrated with claude code.

```

oc-dynamic-agent-patterns on  main is 📦 v0.1.0 via 🐍 v3.13.7 on ☁️  usize
❯ claude
╭─────────────────────────────────────────────────────────────╮
│ ✻ Welcome to Claude Code!                                   │
│                                                             │
│   /help for help, /status for your current setup            │
│                                                             │
│   cwd: /Users/mofoster/Workspace/oc-dynamic-agent-patterns  │
╰─────────────────────────────────────────────────────────────╯

 Tips for getting started:

  Run /init to create a CLAUDE.md file with instructions for Claude
  Use Claude to help with file analysis, editing, bash commands and git
  Be as specific as you would with another engineer for the best results

> Could you please list the agents running in my openshift cluster?

⏺ I'll discover the A2A agents running in your OpenShift cluster.

⏺ oc-agent-discovery - discover_agents (MCP)(all_namespaces: true, verify_endpoints: true)
  ⎿  Found 3 A2A agent(s) in all namespaces:

     [
     … +28 lines (ctrl+o to expand)

⏺ Found 3 A2A agents running in your OpenShift cluster:

  1. cdn-xy-zz-0009-debug-agent (namespace: mofoster-dynamic-a2a-card)
    - URL: https://cdn-xy-zz-0009-debug-agent-mofoster-dynamic-a2a-card.apps.com
    - Status: Endpoint accessible ✓
  2. cdn-xy-zz-0012-debug-agent (namespace: mofoster-dynamic-a2a-card)
    - URL: https://cdn-xy-zz-0012-debug-agent-mofoster-dynamic-a2a-card.apps.com
    - Status: Endpoint accessible ✓
  3. lb-xy-zz-0003-debug-agent (namespace: mofoster-dynamic-a2a-card)
    - URL: https://lb-xy-zz-0003-debug-agent-mofoster-dynamic-a2a-card.apps.com
    - Status: Endpoint accessible ✓

  All agents are running in the mofoster-dynamic-a2a-card namespace and their endpoints are accessible.

> Excellent, could you contact one of the debug agents and run its debug service?

⏺ I'll contact one of the debug agents and run its debug service. Let me start with the first one (cdn-xy-zz-0009-debug-agent).

⏺ oc-agent-discovery - send_message_to_agent (MCP)(agent_url: "https://cdn-xy-zz-0009-debug-agent-mofoster-dynamic-a2a-card.apps.com", message: "Please run your debug service")
  ⎿  Response from https://cdn-xy-zz-0009-debug-agent-mofoster-dynamic-a2a-card.apps.com:

     {
     … +20 lines (ctrl+o to expand)

⏺ The debug agent successfully ran its debug service and returned detailed diagnostic information for device cdn.xy.zz.0009. Here's the summary:

  Status: WARN (Score: 0.84)Issue: Degraded network performance with elevated latency and error rates

  Key Metrics:
  - CPU: 18%, Memory: 62%, Disk: 41%
  - P95 Latency: 320ms
  - Packet Loss: 3.1%
  - HTTP 5xx Rate: 1.8%

  Critical Findings:
  1. Network Issue (High Severity): BGP neighbor flapping correlated with interface errors on eth1
  2. Application Issue (Medium Severity): Increased HTTP 5xx rate affecting API endpoints

  Recommended Actions:
  - High Priority: Check physical link and SFP on eth1, collect BGP neighbor counters
  - Medium Priority: Schedule bgpd restart if flapping persists, capture packets on eth1

  The agent detected network instability that's impacting both routing protocols and application performance.

> Did the agent mention cite any specific log lines or metrics?

⏺ Yes, the agent cited specific log lines and metrics as evidence for its findings:

  Log Lines Cited:
  1. 2025-09-16T14:02:10Z WARN bgpd: neighbor 10.0.0.1 went DOWN (flap detected)
  2. 2025-09-16T14:02:11Z ERROR net_if: eth1 carrier lost, rx_errors=129
  3. 2025-09-16T14:05:00Z INFO httpd: 502 response to /api/query from 192.0.2.5

  Metrics Cited:
  - packet_loss_pct: 3.1%
  - http_5xx_rate_pct: 1.8%

  Evidence References:
  - Finding F001 (BGP flapping): Referenced log_snippets[0], log_snippets[1], and metrics.packet_loss_pct
  - Finding F002 (HTTP errors): Referenced metrics.http_5xx_rate_pct and log_snippets[2]

  The agent also provided query IDs for the raw data: mq-20250916-140500 (metrics) and lq-20250916-140500 (logs).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
> 
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ? for shortcuts

```

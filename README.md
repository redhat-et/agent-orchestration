# Dynamic Agent Discovery in OpenShift Clusters

## About

Dynamic agent discovery creates interesting new possibilities for cluster management.

For example, deployments can include agentic utilities like debuggers that synthesize
data from metrics and logs in order to surface problems with devices or deployments
and offer succinct summaries and suggested next steps.

Making such agents dynamically discoverable creates a powerful new capability for
cluster managers, and empowers organizations to quickly surface new capabilities
without the need for internal evangelizing.

## Shadow Agents

In order to demonstrate the power of dynamic agent discovery in OpenShift we
have implemented a "shadow" pattern, where devices in a content delivery network
are deployed alongside a lightweight agent capable of debugging them or providing
health checks.

The agents may be discovered via an MCP server that facilitates discovery
and then execution of agent capabilities via the A2A protocol.

## Example Run

The following shows a demo of this concept, integrated with claude code.

```

oc-dynamic-agent-patterns on  main is 📦 v0.1.0 via 🐍 v3.13.7 on ☁️  mofoster@redhat.com
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
    - URL: https://cdn-xy-zz-0009-debug-agent-mofoster-dynamic-a2a-card.apps.maas2.octo-emerging.redhataicoe.com
    - Status: Endpoint accessible ✓
  2. cdn-xy-zz-0012-debug-agent (namespace: mofoster-dynamic-a2a-card)
    - URL: https://cdn-xy-zz-0012-debug-agent-mofoster-dynamic-a2a-card.apps.maas2.octo-emerging.redhataicoe.com
    - Status: Endpoint accessible ✓
  3. lb-xy-zz-0003-debug-agent (namespace: mofoster-dynamic-a2a-card)
    - URL: https://lb-xy-zz-0003-debug-agent-mofoster-dynamic-a2a-card.apps.maas2.octo-emerging.redhataicoe.com
    - Status: Endpoint accessible ✓

  All agents are running in the mofoster-dynamic-a2a-card namespace and their endpoints are accessible.

> Excellent, could you contact one of the debug agents and run its debug service?

⏺ I'll contact one of the debug agents and run its debug service. Let me start with the first one (cdn-xy-zz-0009-debug-agent).

⏺ oc-agent-discovery - send_message_to_agent (MCP)(agent_url: "https://cdn-xy-zz-0009-debug-agent-mofoster-dynamic-a2a-card.apps.maas2.octo-emerging.redhataicoe.com", message: "Please run your debug service")
  ⎿  Response from https://cdn-xy-zz-0009-debug-agent-mofoster-dynamic-a2a-card.apps.maas2.octo-emerging.redhataicoe.com:

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

## Prerequisites

- OpenShift cluster access with `oc` CLI installed
- Python 3.13 or later
- uv package manager (recommended) or pip

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

### 1. Deploy Mock Agent

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

### 2. Run the MCP Server for Agent Discovery

The MCP server provides tools for discovering and interacting with A2A agents:

```bash
python oc_agent_discovery.py
```

This server provides the following capabilities:
- Discover A2A agents in OpenShift clusters
- Retrieve agent cards from discovered agents
- Send messages to agents via the A2A protocol
- Stream responses from agents

### Using with Claude Code

The MCP server can be integrated with Claude Code for interactive agent discovery and communication:

```bash
claude mcp add oc-agent-discovery /Users/mofoster/Workspace/cloud-native-agents/demos/dynamic_discovery_with_agent_cards/.venv/bin/python /Users/mofoster/Workspace/cloud-native-agents/demos/dynamic_discovery_with_agent_cards/oc_agent_discovery.py
```

This integration allows you to discover and interact with A2A agents directly from Claude Code using the MCP tools.

### 3. Verify Deployment

Check that your agent is running and accessible:

```bash
# Check pod status
oc get pods -l app=device-status

# View logs
oc logs -l app=device-status -f

# Test agent card endpoint
curl -k https://$(oc get route device-status -o jsonpath='{.spec.host}')/.well-known/agent.json
```

## Discovery Labels

Agents are automatically tagged with discovery labels:
- `a2a.agent=true` - Marks the resource as an A2A agent
- `a2a.agent.name=<agent-name>` - Agent identifier
- `a2a.agent.version=0.1.0` - Agent version

## Cleanup

To remove deployed agents:

```bash
cd mock_agent
./teardown.sh device-status
```

## Usage Examples

Once deployed, you can discover and interact with agents using the MCP tools:

1. List all discovered agents
2. Get agent cards for specific agents
3. Send messages to agents
4. Stream responses from agents

The system demonstrates how A2A-compliant agents can be dynamically discovered and utilized within OpenShift environments.

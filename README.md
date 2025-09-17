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

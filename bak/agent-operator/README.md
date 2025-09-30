# Agent Operator

A Kubernetes operator for discovering and managing AI agents in OpenShift clusters.

## Overview

The Agent Operator provides native `oc get agents` functionality by implementing a lazy controller that discovers agents based on Kubernetes resource labels.

## Components

- **`agent-crd.yaml`**: Custom Resource Definition for Agent resources
- **`lazy-controller.py`**: Lazy controller that discovers agents on-demand
- **`deployment.yaml`**: Kubernetes deployment for the operator
- **`rbac.yaml`**: Role-based access control configuration

## How It Works

1. **Label-based Discovery**: Finds resources with `ai.openshift.io/agent.*` labels
2. **On-demand Generation**: Creates Agent resources dynamically when `oc get agents` is called
3. **Agent Card Integration**: Fetches agent cards from `/.well-known/agent.json` endpoints
4. **Real-time Data**: No persistent storage, always returns current state

## Required Labels

Resources must have these labels to be discovered as agents:

```yaml
labels:
  ai.openshift.io/agent.class: "a2a"              # Required: agent type
  ai.openshift.io/agent.name: "your-agent-name"   # Required: human-readable name
```

Optional annotations:
```yaml
annotations:
  ai.openshift.io/agent.endpoint: "/.well-known/agent.json"  # Agent card endpoint
```

## Installation

1. Install the CRD:
   ```bash
   oc apply -f agent-crd.yaml
   ```

2. Deploy the operator:
   ```bash
   oc apply -f deployment.yaml
   oc apply -f rbac.yaml
   ```

## Usage

Once installed, use standard Kubernetes commands:

```bash
# List all agents
oc get agents

# List agents in specific namespace
oc get agents -n my-namespace

# Get agent details
oc describe agent my-agent

# JSON output
oc get agents -o json
```

## Testing

Test the controller locally:

```bash
python lazy-controller.py
```
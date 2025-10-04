# BYO (Bring Your Own) Agent Pattern

This example demonstrates the **BYO (Bring Your Own) agent pattern** for deploying custom agents with kagent on OpenShift.

## Overview

The BYO pattern allows you to:
- Build your own agent container image with custom logic
- Define agent behavior via YAML configuration
- Deploy agents using kagent's Agent CRD
- Expose agents via the A2A protocol

## What's in this Example

This is a **mock agent** that returns canned responses based on configuration. It's useful for testing agentic systems without requiring live data sources.

```
examples/byo/
├── agent.py                              # Generic A2A-compliant agent runtime
├── Dockerfile                            # Container image definition
├── configs/                              # Agent configurations
│   └── message-queue-monitor.yaml       # Example: embedded response data + agent card
├── deploy.yaml                           # kagent Agent CRD manifest
├── build-and-deploy.sh                  # Build & deploy script
└── README.md                             # This file
```

## How It Works

1. **Configuration** (`configs/message-queue-monitor.yaml`) defines:
   - Agent metadata (name, description, version)
   - Skills and capabilities (A2A protocol)
   - Mock response data (embedded YAML/JSON)

2. **Runtime** (`agent.py`) loads the config and:
   - Serves the agent card at `/.well-known/agent.json`
   - Returns the mock response for any query
   - Implements A2A protocol via the SDK
   - Provides `/health` endpoint for kagent readiness probes

3. **Deployment** (kagent Agent CRD):
   - References your container image
   - Passes config file path via `CONFIG_FILE` env var
   - kagent manages the pod lifecycle

## Quick Start

### 1. Build the Image

```bash
./build-and-deploy.sh
```

This creates: `image-registry.openshift-image-registry.svc:5000/oc-dynamic-agents/mock-agents:latest`

### 2. Deploy the Agent

```bash
kubectl apply -f deploy.yaml
```

### 3. Verify Deployment

```bash
# Check agent status
kubectl get agents -n oc-dynamic-agents

# Expected output:
# NAME                    TYPE   READY   ACCEPTED
# message-queue-monitor   BYO    True    True

# View details
kubectl describe agent message-queue-monitor -n oc-dynamic-agents
```

### 4. Test the Agent

```bash
# Port-forward kagent controller
kubectl port-forward -n kagent svc/kagent-controller 8083:8083 &

# Get agent card
curl http://localhost:8083/api/a2a/oc-dynamic-agents/message-queue-monitor/.well-known/agent.json

# Send a message
curl -X POST http://localhost:8083/api/a2a/oc-dynamic-agents/message-queue-monitor/api/message/send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "content": [{
        "type": "text",
        "text": "What is the queue status?"
      }]
    }
  }'
```

## Configuration Format

```yaml
# Agent metadata and A2A card definition
agent:
  name: "Agent Display Name"
  description: "What this agent does"
  version: "1.0.0"
  skills:
    - id: "skill-id"
      name: "Skill Name"
      description: "What this skill does"
      tags: ["tag1", "tag2"]

# Mock response (YAML format, auto-converted to JSON)
mock_response:
  status: "OK"
  data: {...}
```

## Creating Your Own BYO Agent

### Option 1: Modify this Example

1. Update `configs/message-queue-monitor.yaml`:
   - Change agent metadata
   - Update skills
   - Replace `mock_response` with your data

2. Rebuild and deploy:
```bash
./build-and-deploy.sh
kubectl apply -f deploy.yaml
```

### Option 2: Build Custom Logic

Replace `agent.py` with your own implementation:

```python
class YourAgent:
    async def answer(self, question: str) -> str:
        # Your custom logic here
        result = await your_processing(question)
        return result
```

The only requirements are:
- Implement A2A protocol (use the SDK)
- Serve `/.well-known/agent.json`
- Provide `/health` endpoint
- Listen on port 8080

## Deployment Details

### Agent CRD Spec

```yaml
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: your-agent
  namespace: oc-dynamic-agents
spec:
  description: "Your agent description"
  type: BYO
  byo:
    deployment:
      image: your-registry/your-image:tag
      imagePullPolicy: Always
      env:
        - name: CONFIG_FILE
          value: "/app/configs/your-config.yaml"
```

### Environment Variables

- `CONFIG_FILE` - Path to agent configuration YAML
- `PORT` - Port to listen on (default: 8080)
- `HOST` - Host to bind to (default: 0.0.0.0)
- `BASE_URL` - Override base URL for agent card

### Image Registry

**OpenShift Internal Registry:**
```bash
image-registry.openshift-image-registry.svc:5000/oc-dynamic-agents/mock-agents:latest
```

**External Registry (e.g., ghcr.io):**
```bash
# Build and push
docker build -t ghcr.io/yourorg/your-agent:latest .
docker push ghcr.io/yourorg/your-agent:latest

# Update deploy.yaml
spec:
  byo:
    deployment:
      image: ghcr.io/yourorg/your-agent:latest
```

## Comparison with Other Patterns

| Feature | BYO (this example) | Declarative |
|---------|-------------------|-------------|
| **Use case** | Custom code, existing agents | Quick LLM-based agents |
| **Code** | You write it | kagent generates it |
| **Image** | You build it | kagent provides base |
| **Flexibility** | Full control | Limited to system message |
| **Complexity** | Higher | Lower |

## Troubleshooting

### Agent not Ready

```bash
# Check pod logs
kubectl logs -l kagent=message-queue-monitor -n oc-dynamic-agents

# Check pod status
kubectl get pods -n oc-dynamic-agents -l kagent=message-queue-monitor

# Common issues:
# - Port mismatch (must be 8080)
# - Missing /health endpoint
# - Image not pulled (check imagePullPolicy: Always)
```

### Image not updating

```bash
# Force image pull
kubectl delete pods -n oc-dynamic-agents -l kagent=message-queue-monitor

# Or set imagePullPolicy: Always in deploy.yaml
```

## Next Steps

- See `../declarative/` for LLM-based declarative agents
- See `../../kagent/python/samples/` for ADK, LangGraph, CrewAI examples
- Read the [ROADMAP.md](../../ROADMAP.md) for OpenShift AI integration plans

## References

- **A2A Protocol:** https://github.com/google/A2A
- **kagent:** https://github.com/kagent-dev/kagent
- **A2A SDK:** https://pypi.org/project/a2a-sdk/

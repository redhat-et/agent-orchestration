# KServe + kagent Integration Demo

This demo shows how to integrate kagent with OpenShift AI (RHOAI) using KServe to serve LLM models.

## Architecture

```
Qwen2.5-0.5B Model (Ollama on KServe)
    ↓
kagent ModelConfig (qwen-kserve)
    ↓
kagent Declarative Agent (demo-kserve-agent)
    ↓
A2A Protocol (Agent-to-Agent communication)
```

## Components

### 1. KServe InferenceService (`qwen-tiny-model.yaml`)
- **Model**: Qwen2.5-0.5B (494M parameters)
- **Runtime**: Ollama (ARM64-compatible)
- **Namespace**: `models`
- **Service**: `qwen-tiny.models.svc.cluster.local:8080`

### 2. Kagent ModelConfig (`kagent-modelconfig.yaml`)
- **Name**: `qwen-kserve`
- **Provider**: OpenAI (Ollama has OpenAI-compatible API)
- **Endpoint**: `http://qwen-tiny.models.svc.cluster.local:8080/v1`

### 3. Kagent Declarative Agent (`demo-agent.yaml`)
- **Name**: `demo-kserve-agent`
- **Type**: Declarative
- **Model**: Uses `qwen-kserve` ModelConfig

## Deployment

```bash
# 1. Deploy KServe InferenceService
oc apply -f qwen-tiny-model.yaml
oc apply -f qwen-service.yaml

# 2. Wait for model to download and start
oc get pods -n models -w

# 3. Test model directly
oc run test-curl --image=curlimages/curl:latest --rm -i --restart=Never -- \
  curl -s http://qwen-tiny.models.svc.cluster.local:8080/api/generate \
  -d '{"model":"qwen2.5:0.5b","prompt":"Hello!","stream":false}'

# 4. Create ModelConfig
oc apply -f kagent-modelconfig.yaml

# 5. Deploy Agent
oc apply -f ../declarative/demo-agent.yaml

# 6. Verify Agent
oc get agents -n kagent
```

## Testing

### Direct Model Test
```bash
curl http://qwen-tiny.models.svc.cluster.local:8080/api/generate \
  -d '{
    "model": "qwen2.5:0.5b",
    "prompt": "Why is the sky blue?",
    "stream": false
  }'
```

### Agent Test (via A2A Protocol)
The agent uses JSON-RPC 2.0 protocol. Proper invocation requires the correct method specification.

```bash
# Get agent card
curl http://kagent-controller.kagent.svc.cluster.local:8083/api/a2a/kagent/demo-kserve-agent/.well-known/agent.json

# List all agents
curl http://kagent-controller.kagent.svc.cluster.local:8083/api/agents
```

## Resource Requirements

- **Qwen Model Pod**: 500m CPU, 1Gi Memory
- **Agent Pod**: Default declarative agent resources

## Benefits of This Integration

1. **Self-contained**: No external API dependencies
2. **Cost-effective**: Free, local LLM inference
3. **Enterprise-ready**: Uses RHOAI/KServe standard patterns
4. **Scalable**: KServe handles auto-scaling
5. **Flexible**: Easy to swap models or add more agents

## Next Steps

- Add tool calling to the agent
- Deploy additional models with different capabilities
- Create multi-agent workflows
- Add persistent memory
- Integrate with BYO (Bring Your Own) agents

## Resources

- Kagent Documentation: https://kagent.dev
- KServe Documentation: https://kserve.github.io/website/
- Ollama Models: https://ollama.com/library

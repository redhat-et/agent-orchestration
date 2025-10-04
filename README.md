# kagent + OpenShift AI Integration PoC

**Demonstrating how kagent can be integrated into OpenShift AI to provide first-class agent runtime capabilities.**

## Objective

This proof-of-concept demonstrates the integration path between [kagent](https://github.com/kagent-dev/kagent) (a Kubernetes-native agent framework) and Red Hat OpenShift AI. The goal is to provide:

- **First-class agent resources** in Kubernetes via the Agent CRD
- **Declarative agent deployment** using kagent's framework
- **Multi-framework support** (ADK, LangGraph, CrewAI, custom BYO)
- **A2A protocol compliance** for agent-to-agent communication
- **KServe integration** for model serving

## Status

⚠️ **This is a proof-of-concept, not production-ready.**

- ✅ kagent deployed on OpenShift
- ✅ BYO (Bring Your Own) agent pattern working
- ✅ Declarative agent pattern examples
- ✅ OpenShift AI installation
- ✅ KServe model integration
- ⬜ MCP Agent Bridge 
- ⬜ Agent discovery integration
- ⬜ Dashboard integration

## Quick Start

### 1. Install kagent

```bash
cd deploy
./install-kagent.sh  # Requires $OPENAI_API_KEY env var
```

### 2. Deploy Example Agents

**BYO (Bring Your Own) Pattern:**
```bash
cd examples/byo
./build-and-deploy.sh    # Build image
kubectl apply -f deploy.yaml  # Deploy agent
```

**Declarative Pattern:**
```bash
cd examples/declarative
./deploy-all.sh  # Deploy all monitoring agents
```

### 3. Verify Deployment

```bash
# Check agents
kubectl get agents -n oc-dynamic-agents

# Test agent via A2A protocol
kubectl port-forward -n kagent svc/kagent-controller 8083:8083
curl http://localhost:8083/api/a2a/oc-dynamic-agents/message-queue-monitor/.well-known/agent.json
```

## Repository Structure

```
agent-orchestration/
├── README.md                     # This file
├── ROADMAP.md                    # Integration roadmap & architecture
├── docs/                         # Design docs & presentations
├── deploy/                       # Deployment scripts
│   ├── install-kagent.sh        # Install kagent on cluster
│   └── ns.yaml                  # Namespace setup
├── examples/                     # Agent pattern examples
│   ├── byo/                     # Bring Your Own agent pattern
│   │   ├── agent.py             # A2A-compliant mock agent
│   │   ├── Dockerfile           # Container image
│   │   ├── configs/             # Agent configurations
│   │   ├── deploy.yaml          # kagent Agent CRD
│   │   └── build-and-deploy.sh # Build & deploy script
│   └── declarative/             # Declarative (LLM-based) pattern
│       └── [monitoring agents]
├── kagent/                       # Reference: kagent source (READ ONLY)
└── integration/                  # Future: OpenShift AI integration code
```

## Agent Patterns

### BYO (Bring Your Own)
Deploy custom agent code with full control over logic and behavior.

**Use cases:**
- Existing agent implementations
- Custom frameworks
- Complex business logic
- Integration with external systems

**Example:** `examples/byo/` - Mock agent returning canned responses

**Deploy:**
```bash
cd examples/byo
./build-and-deploy.sh
kubectl apply -f deploy.yaml
```

### Declarative
Deploy LLM-based agents via configuration (no code required).

**Use cases:**
- Quick prototyping
- LLM-powered agents
- Simple query/response patterns

**Example:** `examples/declarative/` - Monitoring agents

**Deploy:**
```bash
cd examples/declarative
./deploy-all.sh
```

## Architecture

See [ROADMAP.md](ROADMAP.md) for detailed architecture diagrams and integration strategy.

### Upstream (kagent)
- Agent, ModelConfig, ToolServer CRDs
- Controller & reconciliation logic
- A2A protocol support
- CLI & basic UI

### Downstream (OpenShift AI - Future)
- Dashboard integration
- KServe auto-discovery
- Multi-tenancy alignment
- Enterprise features

## Integration with OpenShift AI

### Phase 1: PoC (Current)
- ✅ Deploy kagent on OpenShift
- ✅ Example BYO agent
- ✅ Example declarative agents
- ⬜ Install OpenShift AI
- ⬜ Deploy KServe model
- ⬜ Connect agent to KServe

### Phase 2: Integration (Future)
- KServe → ModelConfig auto-sync
- RHOAI dashboard agent management
- Multi-tenant agent deployments
- Observability integration

### Phase 3: Production (Future)
- Red Hat supported distribution
- Enterprise RBAC & compliance
- Customer deployments

## Next Steps

See [ROADMAP.md](ROADMAP.md) for:
- Detailed architecture vision
- OpenShift AI installation guide
- KServe integration plans
- Dashboard extension points
- Timeline & milestones

## Key Concepts

### Agent CRD
Kubernetes custom resource for deploying agents:

```yaml
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: my-agent
spec:
  type: BYO | Declarative
  # ... configuration
```

### A2A Protocol
Agent-to-agent communication protocol providing:
- Agent cards (`/.well-known/agent.json`)
- Message exchange
- Skill discovery
- Task coordination

### ModelConfig
Configuration for LLM providers:

```yaml
apiVersion: kagent.dev/v1alpha2
kind: ModelConfig
metadata:
  name: my-model
spec:
  provider: openAI | anthropic | kserve | ollama
  model: gpt-4
  # ... configuration
```

## Resources

- **kagent:** https://github.com/kagent-dev/kagent
- **OpenShift AI:** https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/
- **A2A Protocol:** https://github.com/google/A2A
- **KServe:** https://kserve.github.io/website/

## Contributing

This is an exploratory project demonstrating integration patterns. Contributions should focus on:

### Upstream (kagent)
- KServe provider implementation
- Multi-tenancy enhancements
- OpenShift compatibility testing

### Downstream (this repo)
- Integration patterns & documentation
- Example agents & use cases
- Deployment automation

File issues or PRs to discuss integration approaches, patterns, or requirements.

## License

See [LICENSE](LICENSE) for details.

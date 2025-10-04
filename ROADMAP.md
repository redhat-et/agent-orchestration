# OpenShift AI + kagent Integration PoC Roadmap

## Objective
Demonstrate how kagent can be integrated into OpenShift AI to provide first-class agent runtime capabilities.

## Architecture Vision

```
┌─────────────────────────────────────────────────────────────────┐
│ OpenShift AI Dashboard (Downstream/Future)                      │
│ ├── Agent Management UI                                         │
│ ├── Model ↔ Agent Binding Interface                            │
│ ├── Metrics & Observability Integration                        │
│ └── Calls kagent APIs (agents.kagent.dev)                       │
└─────────────────────────────────────────────────────────────────┘
                           ↓ Kubernetes API
┌─────────────────────────────────────────────────────────────────┐
│ kagent Framework (Upstream)                                     │
│ ├── Agent CRD (agents.kagent.dev/v1alpha2)                     │
│ │   ├── BYO (bring your own container)                         │
│ │   └── Declarative (LLM-based via system message)             │
│ ├── ModelConfig CRD                                             │
│ │   └── Providers: OpenAI, Anthropic, KServe, Ollama...        │
│ ├── ToolServer CRD (MCP integration)                            │
│ ├── Controller (reconciliation logic)                           │
│ ├── A2A Protocol Support                                        │
│ └── Basic React UI                                              │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ OpenShift AI Components                                         │
│ ├── KServe (Model Serving)                                     │
│ │   └── InferenceService → Granite, vLLM, etc.                 │
│ ├── Data Science Pipelines (Kubeflow)                          │
│ ├── Jupyter Notebooks                                           │
│ └── Model Registry                                              │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ Integration Layer (Downstream Adapters - Future)               │
│ ├── KServe → ModelConfig Auto-Discovery                        │
│ ├── DataScienceProject → Agent Namespace Mapping               │
│ └── RHOAI Metrics → kagent Observability                       │
└─────────────────────────────────────────────────────────────────┘
```

## Upstream vs Downstream Strategy

### Upstream (kagent community)
- **Core Agent APIs** - Agent, ModelConfig, ToolServer CRDs
- **Controller Logic** - Reconciliation, lifecycle management
- **A2A Protocol Support** - Standard agent communication
- **CLI Tool** - `kagent` command-line interface
- **Basic UI** - React-based agent management
- **Framework Adapters** - ADK, LangGraph, CrewAI support

**Contribution Strategy:**
- Add KServe provider support
- Enhance multi-tenancy features
- Improve observability hooks
- OpenShift compatibility testing

### Downstream (OpenShift AI)
- **Dashboard Integration** - Agent management in RHOAI UI
- **KServe Integration** - Auto-discovery of models → ModelConfigs
- **Multi-tenancy Alignment** - DataScienceProject integration
- **Documentation** - OpenShift-specific deployment guides
- **Samples** - RHOAI-specific agent examples
- **Support & Certification** - Red Hat support model

## Phase 1: Proof of Concept (Current)

### Goals
1. ✅ Deploy kagent on OpenShift cluster
2. ✅ Demonstrate BYO agent pattern (mock agents)
3. ✅ Demonstrate Declarative agent pattern (LLM-based)
4. ⬜ Install OpenShift AI on same cluster
5. ⬜ Deploy KServe model
6. ⬜ Connect agent to KServe model
7. ⬜ Document integration points

### Deliverables
- Working kagent deployment on OpenShift
- Example BYO agent (mock-agents)
- Example Declarative agents (monitoring agents)
- Documentation showing integration path
- List of gaps/requirements for production

## Phase 2: Integration (Future)

### OpenShift AI Installation
```bash
# Install RHOAI operator
oc create -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: redhat-ods-operator
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: rhods-operator
  namespace: redhat-ods-operator
spec:
  channel: stable
  name: rhods-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF

# Wait for operator installation
oc wait --for=condition=Ready pod -l name=rhods-operator -n redhat-ods-operator --timeout=300s

# Create DataScienceCluster
oc create -f - <<EOF
apiVersion: datasciencecluster.opendatahub.io/v1
kind: DataScienceCluster
metadata:
  name: default-dsc
spec:
  components:
    dashboard:
      managementState: Managed
    workbenches:
      managementState: Managed
    modelmeshserving:
      managementState: Managed
    kserve:
      managementState: Managed
EOF
```

### KServe Model Deployment
```yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: granite-model
  namespace: models
spec:
  predictor:
    model:
      modelFormat:
        name: pytorch
      runtime: vllm
      storageUri: s3://models/granite-3.1-8b-instruct
```

### ModelConfig Integration
```yaml
apiVersion: kagent.dev/v1alpha2
kind: ModelConfig
metadata:
  name: granite-kserve
  namespace: kagent
spec:
  provider: kserve  # New provider type
  model: granite-3.1-8b-instruct
  endpoint: http://granite-model-predictor.models.svc.cluster.local/v1
  # KServe implements OpenAI-compatible API
```

### Agent Using KServe Model
```yaml
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: data-analyst-agent
  namespace: data-science-team
spec:
  type: Declarative
  description: "Analyzes datasets and generates insights"
  declarative:
    modelConfig: granite-kserve  # Points to KServe model
    systemMessage: |
      You are a data analyst agent...
```

## Phase 3: Dashboard Integration (Future)

### RHOAI Dashboard Extension
- Add "Agents" section to RHOAI dashboard
- Agent CRUD operations
- Model selection dropdown (from KServe InferenceServices)
- Agent metrics/logs viewer
- A2A protocol testing interface

### Implementation Options
1. **PatternFly React Extension**
   - Extend RHOAI dashboard codebase
   - Call kagent API server

2. **Proxy Integration**
   - RHOAI dashboard → kagent UI (iframe/proxy)
   - Less custom code, faster to implement

## Key Questions to Resolve

### 1. Governance
- **Q:** Will agent runtime be Red Hat-owned or community project?
- **A (Proposed):** Core APIs upstream (kagent), UI/integration downstream (RHOAI)

### 2. Model Integration
- **Q:** How do agents discover/use models in KServe?
- **A (Proposed):**
  - Phase 1: Manual ModelConfig creation
  - Phase 2: Auto-sync InferenceService → ModelConfig
  - Phase 3: Dashboard UI for model selection

### 3. Multi-tenancy
- **Q:** How do agent namespaces align with RHOAI projects?
- **A (Proposed):**
  - Use standard k8s namespaces
  - Agents deploy in DataScienceProject namespaces
  - RBAC inherits from RHOAI project permissions

### 4. Dashboard
- **Q:** Native RHOAI UI or point to kagent UI?
- **A (Proposed):**
  - Phase 1: Link to kagent UI
  - Phase 2: Embed kagent UI in RHOAI dashboard
  - Phase 3: Native RHOAI agent management UI

### 5. CRD Naming
- **Q:** Use `agents.kagent.dev` or create `agents.openshift.io`?
- **A (Proposed):** Keep `agents.kagent.dev` (upstream), add OpenShift annotations
- **Precedent:** Knative uses `serving.knative.dev`, not `serving.openshift.io`

## Success Metrics

### Phase 1 (PoC)
- ✅ kagent deployed on OpenShift
- ✅ BYO agent example working
- ✅ Declarative agent example working
- ⬜ RHOAI installed alongside kagent
- ⬜ KServe model serving agent requests
- ⬜ Documentation complete

### Phase 2 (Integration)
- Auto-discovery of KServe models
- Multi-tenant agent deployments
- RHOAI dashboard showing agents
- Agent metrics in RHOAI observability

### Phase 3 (Production)
- Red Hat supported kagent distribution
- Full RHOAI dashboard integration
- Enterprise features (RBAC, audit, compliance)
- Customer deployments

## Repository Structure (Proposed Cleanup)

```
agent-orchestration/
├── README.md                           # High-level PoC overview
├── ROADMAP.md                          # This file
├── docs/                               # Architecture documentation
│   ├── integration-guide.md           # How to integrate with RHOAI
│   ├── kserve-modelconfig.md          # KServe provider guide
│   └── presentations/                 # Demo slides
├── deploy/                            # Deployment scripts
│   ├── install-kagent.sh              # Install kagent
│   ├── install-rhoai.sh               # Install OpenShift AI
│   └── ns.yaml                        # Namespace setup
├── examples/                          # Agent examples
│   ├── byo-agents/                    # BYO pattern (mock agents)
│   │   ├── mock_agent/                # Generic mock agent
│   │   └── README.md
│   └── declarative-agents/            # Declarative pattern
│       ├── monitoring-agents/         # LLM-based monitoring
│       └── README.md
├── kagent/                            # kagent source (git submodule or reference)
└── integration/                       # RHOAI integration code (future)
    ├── kserve-sync/                   # Auto-sync InferenceService → ModelConfig
    └── dashboard-extension/           # RHOAI UI extension
```

## Next Steps (Immediate)

1. **Clean up repository**
   - Remove deprecated code (`bak/`, old agent-operator)
   - Reorganize examples
   - Update main README

2. **Install OpenShift AI**
   - Deploy RHOAI operator
   - Create DataScienceCluster
   - Verify dashboard access

3. **Deploy KServe Model**
   - Choose sample model (Granite, Llama, etc.)
   - Create InferenceService
   - Test model serving

4. **Create Integration Example**
   - Manual ModelConfig → KServe
   - Deploy agent using KServe model
   - Document the flow

5. **Document Integration Points**
   - API endpoints needed
   - Dashboard extension points
   - RBAC requirements
   - Metrics/logging integration

## Timeline (Estimated)

- **Week 1-2:** Repository cleanup + RHOAI installation
- **Week 3-4:** KServe integration + agent examples
- **Week 5-6:** Documentation + demo preparation
- **Week 7+:** Community engagement + upstream contributions

## Resources

- **kagent:** https://github.com/kagent-dev/kagent
- **OpenShift AI:** https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/
- **KServe:** https://kserve.github.io/website/
- **A2A Protocol:** https://github.com/google/A2A
- **MCP:** https://modelcontextprotocol.io/

## Contributing

### Upstream (kagent)
- Submit PRs for KServe provider support
- Propose multi-tenancy enhancements
- Test OpenShift compatibility
- Share OpenShift-specific documentation

### Downstream (This Repo)
- Document integration patterns
- Build example agents
- Create deployment automation
- Share best practices

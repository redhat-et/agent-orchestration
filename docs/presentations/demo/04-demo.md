# 🖥 Demo

### OpenShift CLI
```bash
oc get agents
oc get agent-card <agent-name>
```

  - oc get agents → list available agents
  - oc get agent-card → fetch capabilities & endpoints

### Agent Card
  - Identity + metadata
  - Capability contract
  - Bootstrap for runtime communication

### MCP Server
  - Consumes agent cards
  - Enables discovery + tool negotiation
  - Ready to integrate with dev tools (e.g. Claude Code)

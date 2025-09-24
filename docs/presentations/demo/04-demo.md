



# 🖥 Demo

### OpenShift CLI
```bash
oc get agents
oc describe agent <agent-name>
```

  - oc get agents → list available agents
  - oc describe agent → fetch capabilities & endpoints

### Agent Card
  - Identity (supports signatures) + metadata
  - Capability contract
  - Bootstrap for runtime communication 

### MCP Server
  - Consumes agent cards
  - Enables discovery + tool negotiation
  - Ready to integrate with dev tools (e.g. Claude Code)

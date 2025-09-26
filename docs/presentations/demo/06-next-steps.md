
# ⏭️ Next Steps

## Still Needs
 - Standardized deployment spec.
 - Identity verification with Agent Card signatures.
 - RBAC
 - Baseline /metrics endpoint.
---

# Big Picture 

```text
+=========================================================================+
|              Kubernetes / OpenShift Cluster (agentized)                 |
+=========================================================================+
|                                                                         |
|  +---------------- Agent Resource (CRD: Agent) ----------------------+  |
|  | name: <agent-name>                                                 | |
|  |                                                                    | |
|  |  +------------+                             +-------------------+  | |
|  |  | AGENT CARD |<====    A2A messages    ===>| Other Agents/     |  | |
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

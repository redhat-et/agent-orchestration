# ☸️ Why OpenShift?

- Already provides **CRDs, controllers, APIs**  
- Perfect substrate for **durable agent models**  
- We can model agents as **first-class resources**

---

**Proof of Concept**  
- Define an `Agent` CRD  
- Wrap A2A practices into Kubernetes API objects  
- Create an **MCP server** that:  
  - Discovers agents  
  - Surfaces capabilities  
  - Communicates via A2A





# AI Agent Stack + Maturity

The concept of an "AI Agent" can be modeled into the following conceptual layers, with accompanying projects for each.

| Layer | Responsibility | Examples | Maturity |
|-------|----------------|----------|----------|
| 6. Input / Interaction | Capture intent, structure inputs | Slack Bot, Webhook, Chat | **Consolidating** |
| 5. Discovery & Registry | Publish & resolve agent/tool capabilities | A2A cards, NANDA index | **Experimental** |
| 4. Orchestration & Planning | DAGs, schedulers, planners | LangGraph, CrewAI, AutoGen | **Fragmented** |
| 3. Messaging | Agent-to-agent communication | A2A, A̶C̶P̶ | **Consolidating** |
| 2. Tool Interface | Tool negotiation & contracts | MCP, Direct Calling, UTCP | **Consolidating** |
| 1. Execution Plane | Run models & tools | vLLM, Ollama, APIs | **Consolidating** |

---

**Cross-cutting services:**  
Storage • Observability • Deployment • Security • Governance

**Conclusion**
 - Orchestration and Planning, where agent frameworks live, is the most contested part of the stack. 
 - This creates an opportunity: by hooking in just above and just below the most unstable layer we can build a durable conceptual boundary.  
 - In practice this would mean:
    - building a simple interface for search and discovery – durable across implementation details 
    - using agent card metadata (a common feature across messaging protocols) as a basis for modeling agents as components in systems.

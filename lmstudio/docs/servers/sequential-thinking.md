# sequential-thinking

**MCP server:** `sequential-thinking`  
**Package:** `@modelcontextprotocol/server-sequential-thinking`

Structured multi-step reasoning scaffold — break a problem into ordered thoughts before acting.

---

## When to use

| Scenario | Flow |
|---|---|
| Complex task needs planning | sequential-thinking → plan steps |
| Before large refactor | thoughts → coding-tools execution |
| Local model rushes to tools | Force explicit reasoning chain |

---

## Typical flow

```
sequential-thinking: thought 1 → thought 2 → ... → conclusion
     ↓
coding-tools: execute plan step by step
     ↓
think-delegate: if a step fails or needs expert input
```

**Complements:** think-delegate (expert depth) · coding-tools (execution)

# context7

**MCP server:** `context7`  
**Package:** `@upstash/context7-mcp`

Up-to-date library and framework documentation lookup.

---

## Flow

```mermaid
sequenceDiagram
  participant Model
  participant C7 as context7
  participant Docs as Library docs index

  Model->>C7: resolve library + query
  C7->>Docs: fetch relevant snippets
  Docs-->>C7: documentation excerpts
  C7-->>Model: formatted docs
  Model->>Model: coding-tools to implement
```

---

## When to use

| Scenario | vs other tools |
|---|---|
| “How do I use FastMCP decorators?” | context7 — structured lib docs |
| Arbitrary webpage | web-tools `fetch_url` |
| Reasoning over recent changes | think-delegate `latest_knowledge` |

**Typical flow:** context7 → read official pattern → **coding-tools** `write_file` / `edit_file`

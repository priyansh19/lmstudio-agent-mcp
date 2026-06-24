# web-tools (OpenClaw)

**MCP server:** `web-tools`  
**Source:** `../lmstudio/servers/web_tools.py`

Same two tools as LM Studio: `fetch_url`, `web_search`.

Full reference: [../../lmstudio/docs/servers/web-tools.md](../../lmstudio/docs/servers/web-tools.md)

---

## When to use on WhatsApp

| User intent | Tool |
|---|---|
| “Search the web for X” | `web-tools__web_search` |
| “Read this URL” | `web-tools__fetch_url` |
| Needs synthesis + reasoning | Prefer `think-delegate__latest_knowledge` |

---

## Example

```json
{"query": "OpenClaw MCP toolFilter", "max_results": 3}
```

```json
{"url": "https://docs.example.com/page", "max_chars": 4000}
```

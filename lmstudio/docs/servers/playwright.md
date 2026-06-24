# playwright

**MCP server:** `playwright`  
**Package:** `@playwright/mcp`

Full browser automation — navigate, snapshot DOM, click, type, screenshot.

---

## When to use

| Scenario | vs fetch_url |
|---|---|
| JavaScript-rendered SPA | playwright renders JS |
| Login flows, multi-step UI | interactive click/type |
| Static HTML page | web-tools `fetch_url` is enough |

---

## Typical flow

```
navigate(url) → snapshot() → click(selector) → type(...) → snapshot()
```

**Cost:** Heavy — use sparingly; resource-intensive in local setups.

---

## Combine with

- **web-tools** for simple fetches first; escalate to playwright if page is empty/broken in fetch.
- **coding-tools** to save extracted data or screenshots to files.

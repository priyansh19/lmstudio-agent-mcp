# codebase-memory

**MCP server:** `codebase-memory`  
**Binary:** `codebase-memory-mcp`

Code-aware memory — indexes and retrieves project structure and context over time.

---

## Purpose

Long-term **codebase-level** recall: where modules live, patterns used, indexed repository structure. Different from **memory** (user facts in `.agent-memory.json`).

---

## When to use

| Scenario | Tool usage |
|---|---|
| “Where is auth handled in this repo?” | Search codebase memory |
| After indexing repo | Better retrieval of file/module relationships |
| Large project orientation | Before grep/read_file exploration |

---

## Flow

```
index_repository (CLI) → codebase-memory indexes repo
     ↓
Model queries via MCP search tools → relevant code context returned
```

Use alongside **coding-tools** `grep` / `find_files` for precise file operations.

# git (read-only MCP)

**MCP server:** `git`  
**Package:** `mcp-server-git`

Read-only git operations — no commits (use **coding-tools** `git_commit` for writes).

---

## Typical tools

| Operation | Use |
|---|---|
| Log / history | See recent commits without shell |
| Diff | Compare changes read-only |
| Status | Working tree state |
| Show / branch list | Inspect refs and file history |

---

## When to use

| coding-tools git_* | git MCP |
|---|---|
| You need commit/write | Read-only audit |
| Already in agent flow | Dedicated git introspection |
| `git_commit`, `git_diff` | Deeper history browsing |

**Flow:** `git` MCP for exploration → **coding-tools** for making changes and committing.

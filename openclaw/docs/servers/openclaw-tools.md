# openclaw-tools

**MCP server:** `openclaw-tools`  
**Source:** `openclaw/servers/openclaw_tools.py`  
**OpenClaw only** — use this instead of `coding-tools__read_file` on WhatsApp

All tools accept empty `{}` or use sensible defaults.

---

## Why this exists

Gemma calls `coding-tools__read_file` with `{}` → OpenClaw JSON validation fails **before** MCP runs. This server duplicates read/list/grep with **default parameters**.

**Do not use `coding-tools__read_file` on OpenClaw.** Use `openclaw-tools__read_file`.

---

## Tools (15)

### Zero-arg discovery

| Tool | Description |
|---|---|
| `list_allowed_roots` | Sandbox + repo root paths |
| `list_repo` | Top-level `lmstudio-agent-mcp/` |
| `list_lmstudio` | Contents of `lmstudio/` |
| `list_openclaw` | Contents of `openclaw/` |

### Doc reads (zero-arg)

| Tool | File |
|---|---|
| `read_readme` | `lmstudio/README.md` |
| `read_openclaw_readme` | `openclaw/README.md` |
| `read_setup_guide` | `lmstudio/SETUP.md` |
| `read_catalog` | `lmstudio/CATALOG.md` |

### Optional-arg reads

| Tool | Default |
|---|---|
| `read_doc` | `filename=README.md` |
| `read_repo_file` | `relative_path=lmstudio/README.md` |

### Sandbox I/O (Gemma-safe — use instead of coding-tools)

| Tool | Default |
|---|---|
| `read_file` | `path=lmstudio-agent-mcp/lmstudio/README.md` |
| `list_directory` | `path=lmstudio-agent-mcp` |
| `grep` | `pattern=openclaw`, `path=lmstudio-agent-mcp` |
| `find_files` | `pattern=*.md`, `path=lmstudio-agent-mcp` |
| `grep_repo` | `pattern=think-delegate` |

Paths are relative to sandbox root (`~/Desktop`).

---

## Flow

```
User → Gemma → openclaw-tools__read_readme {}
         → lmstudio/README.md content
         → reply
```

For subpaths:

```
openclaw-tools__read_file {"path": "lmstudio-agent-mcp/lmstudio/servers/coding_tools.py"}
```

Or `{}` for default README.

---

## OpenClaw profile

`coding-tools` on OpenClaw is limited to 3 tools (all args optional): `list_allowed_roots`, `list_directory`, `find_files`. No `read_file` or `grep` on coding-tools.

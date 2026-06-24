# Tool-calling rules (OpenClaw agent)

## Filesystem access

MCP tools can read your **entire home directory** (`~`), not just Desktop or lmstudio-agent-mcp.

Config: `openclaw/config/filesystem.json` → re-apply with `setup_openclaw_mcp.py`

Paths are **relative to home**:

```
Desktop/Learning-01/session-1-claude-loops
Documents/myfile.txt
Downloads
lmstudio-agent-mcp/lmstudio/README.md
```

OpenClaw itself also has **sandbox off** — native tools (`read`, `write`, `exec`, `apply_patch`) can access the full Mac when the gateway process has permission.

---

## Use openclaw-tools for reads (Gemma-safe)

| Need | Tool |
|---|---|
| List home | `openclaw-tools__list_home` |
| List Desktop | `openclaw-tools__list_desktop` |
| List any folder | `openclaw-tools__list_directory` path=`Desktop/Learning-01` |
| Read a file | `openclaw-tools__read_file` path=`Desktop/Learning-01/.../README.md` |
| Browse Desktop with {} | `openclaw-tools__read_file` (default path=Desktop) |
| Search | `openclaw-tools__grep` or `find_files` |
| LM Studio repo docs | `openclaw-tools__read_readme` |

**Do not use `coding-tools__read_file`** — Gemma sends `{}` and validation fails.

---

## Example: explore a Cursor project on Desktop

```
openclaw-tools__list_desktop
openclaw-tools__list_directory  path=Desktop/Learning-01
openclaw-tools__read_file       path=Desktop/Learning-01/session-1-claude-loops/README.md
```

---

## Priority

1. openclaw-tools — filesystem reads/lists
2. think-delegate — hard reasoning
3. web-tools — web fetch/search
4. OpenClaw native tools — read/write/exec (full Mac, sandbox off)
5. memory — preferences

---

## Add more roots (external drives)

Edit `openclaw/config/filesystem.json`:

```json
{
  "allowedRoots": ["__HOME__", "/Volumes/MyDrive"]
}
```

Then: `cd lmstudio && uv run python ../openclaw/scripts/setup_openclaw_mcp.py`

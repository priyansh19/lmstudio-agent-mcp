# procedural — Phase 4 Skill.md procedural memory

**MCP server:** `procedural`  
**Source:** `servers/procedural_tools.py` + `agent/procedural_memory.py`  
**Config:** `config/procedural.json`  
**Default skill:** `skills/Skill.md`

---

## Architecture role

Procedural memory defines **how the agent should act** — loaded into the system prompt on every turn (not RAG). Matches the diagram’s `Skill.md` / procedural memory box.

Search order:

1. `lmstudio/skills/Skill.md` (repo default)
2. Paths in `config/procedural.json` → `skills_dirs`
3. `<workspace>/skills/Skill.md` when `include_workspace_skills` is true

---

## Tools

| Tool | Purpose |
|---|---|
| `list_skills` | Discover Skill.md files |
| `read_procedural_memory` | Preview merged procedural block |
| `procedural_status` | Config + file count |

---

## Agent integration

`local_agent.py` merges procedural memory into the system prompt via `load_procedural_context()`.

Disable: `--no-procedural` or `PROCEDURAL_ENABLED=0`.

Per-project skills: add `skills/Skill.md` under your workspace root.

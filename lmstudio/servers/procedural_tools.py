"""
procedural_tools.py — MCP server for Phase 4 Skill.md procedural memory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP

from agent.procedural_memory import (
    discover_skill_files,
    load_config,
    load_procedural_context,
)

mcp = FastMCP("procedural")


@mcp.tool()
def list_skills(workspace: str = "") -> str:
    """List Skill.md / procedural memory files discovered on disk."""
    files = discover_skill_files(workspace)
    if not files:
        return "No skill files found. Add skills/Skill.md under lmstudio/ or workspace."
    lines = ["Procedural skill files:"]
    for p in files:
        lines.append(f"- {p}")
    return "\n".join(lines)


@mcp.tool()
def read_procedural_memory(workspace: str = "") -> str:
    """Return the procedural memory block injected into the agent system prompt."""
    block = load_procedural_context(workspace)
    return block or "(procedural memory disabled or no Skill.md files found)"


@mcp.tool()
def procedural_status() -> str:
    """Show procedural memory configuration."""
    cfg = load_config()
    files = discover_skill_files()
    return "\n".join([
        "procedural MCP — Phase 4 Skill.md loader",
        f"  enabled: {cfg.get('enabled', True)}",
        f"  skill_filenames: {cfg.get('skill_filenames', [])}",
        f"  skills_dirs: {cfg.get('skills_dirs', [])}",
        f"  include_workspace_skills: {cfg.get('include_workspace_skills', True)}",
        f"  discovered files: {len(files)}",
        "",
        "Tools: list_skills, read_procedural_memory",
    ])


if __name__ == "__main__":
    mcp.run(transport="stdio")

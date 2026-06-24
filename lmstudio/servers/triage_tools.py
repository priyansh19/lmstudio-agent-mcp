"""
triage_tools.py — MCP server for Phase 1 scoring + auto-triage.

Tools:
  score_prompt   — local model scores confidence 0-10
  triage_request — score + auto-delegate to Claude if below threshold
  triage_status  — show config
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow imports from lmstudio project root
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP

from agent.triage_core import load_config, score_prompt, triage_prompt

mcp = FastMCP("triage")


@mcp.tool()
def score_prompt_tool(user_prompt: str, context: str = "") -> str:
    """Score how confidently the local model can handle this request (0-10).

    Uses the loaded LM Studio model as the scoring agent.
    Does NOT delegate — scoring only.
    """
    if not user_prompt.strip():
        return "Error: user_prompt cannot be empty."
    score, reason = score_prompt(user_prompt, context)
    cfg = load_config()
    threshold = float(cfg.get("threshold", 7.0))
    route = "local" if score >= threshold else "claude"
    return json.dumps(
        {
            "score": score,
            "reason": reason,
            "threshold": threshold,
            "route": route,
        },
        indent=2,
    )


@mcp.tool()
def triage_request(
    user_prompt: str,
    context: str = "",
    auto_delegate: bool = True,
) -> str:
    """Score the prompt and route: local model or Claude expert.

    If score < threshold (default 7) and auto_delegate=true, calls think-delegate
    (Claude CLI) and returns the expert response.

    Matches Architecture_Daigram: Scoring Agent → Triaging → MCP Claude.
    """
    if not user_prompt.strip():
        return "Error: user_prompt cannot be empty."
    result = triage_prompt(user_prompt, context, auto_delegate=auto_delegate)
    return result.summary()


@mcp.tool()
def triage_status() -> str:
    """Show triage configuration (threshold, enabled, LM Studio URL)."""
    cfg = load_config()
    lines = [
        "triage MCP — Phase 1 scoring + auto-route",
        f"  enabled: {cfg.get('enabled', True)}",
        f"  threshold: {cfg.get('threshold', 7.0)} (score >= → local, < → Claude)",
        f"  ultra_threshold: {cfg.get('ultra_threshold', 4.0)} (score < → opus)",
        f"  lmstudio_url: {cfg.get('lmstudio_url')}",
        f"  bridge_triage: {cfg.get('bridge_triage', True)}",
        f"  config: {_ROOT / 'config' / 'triage.json'}",
        "",
        "Tools: score_prompt_tool, triage_request",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")

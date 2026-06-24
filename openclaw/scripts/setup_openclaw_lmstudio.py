#!/usr/bin/env python3
"""
setup_openclaw_lmstudio.py — Point OpenClaw at the stable LM Studio bridge (once).

Run from lmstudio/:
    cd lmstudio && uv run python ../openclaw/scripts/setup_openclaw_lmstudio.py --with-mcp
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

OPENCLAW = Path(__file__).resolve().parent.parent
LMSTUDIO = OPENCLAW.parent / "lmstudio"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
LMSTUDIO_MCP = Path.home() / ".lmstudio" / "mcp.json"
BRIDGE_PORT = 8765
BRIDGE_URL = f"http://127.0.0.1:{BRIDGE_PORT}/v1"

LOCAL_AGENT_PROVIDER = {
    "baseUrl": BRIDGE_URL,
    "apiKey": "local",
    "api": "openai-completions",
    "models": [
        {
            "id": "local/current",
            "name": "LM Studio (auto — whatever is loaded)",
            "reasoning": False,
            "input": ["text"],
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            "contextWindow": 131072,
            "maxTokens": 8192,
        }
    ],
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Configure OpenClaw → LM Studio bridge")
    ap.add_argument("--with-mcp", action="store_true",
                    help="Copy MCP servers from ~/.lmstudio/mcp.json into OpenClaw.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-anthropic-fallback", action="store_true",
                    help="Keep Claude models as fallbacks (default: local only).")
    args = ap.parse_args()

    if not OPENCLAW_CONFIG.exists():
        sys.exit(f"OpenClaw config not found at {OPENCLAW_CONFIG}. Run: openclaw onboard")

    cfg = _load_json(OPENCLAW_CONFIG)

    cfg.setdefault("models", {})
    cfg["models"]["mode"] = "merge"
    cfg["models"].setdefault("providers", {})
    cfg["models"]["providers"]["local-agent"] = LOCAL_AGENT_PROVIDER

    cfg.setdefault("agents", {}).setdefault("defaults", {})
    cfg["agents"]["defaults"].setdefault("model", {})
    cfg["agents"]["defaults"]["model"]["primary"] = "local-agent/local/current"

    if not args.keep_anthropic_fallback:
        cfg["agents"]["defaults"]["model"]["fallbacks"] = []

    if args.with_mcp and LMSTUDIO_MCP.exists():
        lm_mcp = _load_json(LMSTUDIO_MCP).get("mcpServers", {})
        cfg.setdefault("mcp", {}).setdefault("servers", {})
        for name, spec in lm_mcp.items():
            cfg["mcp"]["servers"][name] = spec

    if args.dry_run:
        print(json.dumps({
            "primary_model": cfg["agents"]["defaults"]["model"]["primary"],
            "bridge_url": BRIDGE_URL,
            "mcp_servers": sorted(cfg.get("mcp", {}).get("servers", {})),
        }, indent=2))
        return

    backup = OPENCLAW_CONFIG.with_suffix(f".json.bak.{int(time.time())}")
    shutil.copy2(OPENCLAW_CONFIG, backup)
    OPENCLAW_CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    print(f"Backed up -> {backup}")
    print(f"Wrote   -> {OPENCLAW_CONFIG}")
    print("Primary model: local-agent/local/current")
    print(f"Bridge URL:    {BRIDGE_URL}")
    print("\nNext:")
    print("  1) Start bridge:  cd lmstudio && uv run python agent/lmstudio_bridge.py")
    print("  2) LM Studio:     lms server start  (+ load any model you want)")
    print("  3) Restart OpenClaw gateway if running: openclaw gateway restart")
    print("  4) Verify:          curl http://127.0.0.1:8765/health")


if __name__ == "__main__":
    main()

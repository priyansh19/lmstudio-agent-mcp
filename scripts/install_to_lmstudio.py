#!/usr/bin/env python3
"""
install_to_lmstudio.py — Plug-and-play installer.

Merges this repo's MCP server definitions into LM Studio's own mcp.json
(~/.lmstudio/mcp.json), so every server shows up in the LM Studio app ready to
toggle on. Existing config is backed up first; your other servers are kept.

Usage:
    python scripts/install_to_lmstudio.py                 # zero-config servers only
    python scripts/install_to_lmstudio.py --include-keys  # also add key/OAuth templates
    python scripts/install_to_lmstudio.py --dry-run       # show what would change
    python scripts/install_to_lmstudio.py --only github filesystem docker-tools
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAIN_CONFIG = REPO / "config" / "mcp.json"
KEYS_CONFIG = REPO / "config" / "optional-with-keys.json"
LMSTUDIO_CONFIG = Path.home() / ".lmstudio" / "mcp.json"
# Servers removed from our catalog — pruned from LM Studio on full install.
REMOVED_SERVERS = frozenset({"filesystem", "fetch"})


def _strip_notes(obj):
    """Recursively drop keys that start with '_' (our annotations)."""
    if isinstance(obj, dict):
        return {k: _strip_notes(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_notes(v) for v in obj]
    return obj


def _codebase_memory_bin() -> str:
    import shutil
    candidates = [
        Path.home() / ".local/bin" / "codebase-memory-mcp",
        shutil.which("codebase-memory-mcp"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return str(Path(c).resolve())
    return str(Path.home() / ".local/bin" / "codebase-memory-mcp")


def _resolve_paths(servers: dict, repo: str, sandbox: str) -> None:
    """Replace portable placeholders so the config works on any machine:
        __REPO__     -> this repo's absolute path
        __SANDBOX__  -> the workspace root the agent may edit
        __HOME__     -> the user's home directory
    """
    home = str(Path.home())

    def sub(s: str) -> str:
        return (s.replace("__REPO__", repo)
                 .replace("__SANDBOX__", sandbox)
                 .replace("__HOME__", home)
                 .replace("__CODEBASE_MEMORY_BIN__", _codebase_memory_bin()))

    for spec in servers.values():
        if isinstance(spec.get("command"), str):
            spec["command"] = sub(spec["command"])
        spec["args"] = [sub(a) if isinstance(a, str) else a for a in spec.get("args", [])]
        env = spec.get("env", {})
        for key, val in list(env.items()):
            if isinstance(val, str):
                env[key] = sub(val)


def _inject_env(servers: dict) -> None:
    """For any env value still containing REPLACE_ME, substitute from the real
    environment if a variable of the same name is set. Lets you do:
        GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxx python install_to_lmstudio.py ...
    without writing secrets into the repo's JSON files."""
    import os
    for spec in servers.values():
        env = spec.get("env", {})
        for key, val in list(env.items()):
            if isinstance(val, str) and "REPLACE_ME" in val and os.environ.get(key):
                env[key] = os.environ[key]


def _load_servers(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return _strip_notes(data).get("mcpServers", {})


def main() -> None:
    ap = argparse.ArgumentParser(description="Install MCP servers into LM Studio")
    ap.add_argument("--include-keys", action="store_true",
                    help="Also merge key/OAuth template servers (you must fill placeholders).")
    ap.add_argument("--only", nargs="*", default=None,
                    help="Only install these named servers.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the resulting config without writing it.")
    ap.add_argument("--sandbox", default=None,
                    help="Workspace root the agent may edit (default: $SANDBOX_ROOT or ~/Desktop).")
    args = ap.parse_args()

    import os
    sandbox = args.sandbox or os.environ.get("SANDBOX_ROOT") or str(Path.home() / "Desktop")
    sandbox = str(Path(sandbox).expanduser())

    incoming = _load_servers(MAIN_CONFIG)
    if args.include_keys:
        incoming.update(_load_servers(KEYS_CONFIG))
    _resolve_paths(incoming, str(REPO), sandbox)
    _inject_env(incoming)

    # Drop key/OAuth servers whose placeholders were not filled.
    incoming = {
        k: v for k, v in incoming.items()
        if not any(
            isinstance(val, str) and "REPLACE_ME" in val
            for val in v.get("env", {}).values()
        )
    }

    if args.only:
        incoming = {k: v for k, v in incoming.items() if k in set(args.only)}
        missing = set(args.only) - set(incoming)
        if missing:
            print(f"Warning: not found in configs: {', '.join(sorted(missing))}", file=sys.stderr)

    if not incoming:
        sys.exit("Nothing to install. Check --only names or config files.")

    existing = {}
    if LMSTUDIO_CONFIG.exists():
        try:
            existing = json.loads(LMSTUDIO_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("Existing ~/.lmstudio/mcp.json is not valid JSON; starting fresh.",
                  file=sys.stderr)
            existing = {}
    existing.setdefault("mcpServers", {})

    added, updated, removed = [], [], []
    for name, spec in incoming.items():
        if name in existing["mcpServers"]:
            updated.append(name)
        else:
            added.append(name)
        existing["mcpServers"][name] = spec

    if not args.only:
        for name in REMOVED_SERVERS:
            if name in existing["mcpServers"]:
                del existing["mcpServers"][name]
                removed.append(name)

    if args.dry_run:
        print(json.dumps(existing, indent=2))
        print(f"\n[dry-run] would add: {added}", file=sys.stderr)
        print(f"[dry-run] would update: {updated}", file=sys.stderr)
        if removed:
            print(f"[dry-run] would remove: {removed}", file=sys.stderr)
        return

    LMSTUDIO_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if LMSTUDIO_CONFIG.exists():
        backup = LMSTUDIO_CONFIG.with_suffix(f".json.bak.{int(time.time())}")
        shutil.copy2(LMSTUDIO_CONFIG, backup)
        print(f"Backed up existing config -> {backup}")

    LMSTUDIO_CONFIG.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {LMSTUDIO_CONFIG}")
    print(f"Added:   {', '.join(added) or '(none)'}")
    print(f"Updated: {', '.join(updated) or '(none)'}")
    if removed:
        print(f"Removed: {', '.join(removed)}")
    print("\nOpen LM Studio -> Program -> mcp.json (or restart it) and toggle the servers on.")


if __name__ == "__main__":
    main()

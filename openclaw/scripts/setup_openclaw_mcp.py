#!/usr/bin/env python3
"""
setup_openclaw_mcp.py — Sync MCP into OpenClaw with a WhatsApp-friendly profile.

Run from lmstudio/:
    cd lmstudio && uv run python ../openclaw/scripts/setup_openclaw_mcp.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

OPENCLAW = Path(__file__).resolve().parent.parent
LMSTUDIO = OPENCLAW.parent / "lmstudio"
ROOT = LMSTUDIO.parent
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
FILESYSTEM_CONFIG = OPENCLAW / "config" / "filesystem.json"

# Gemma-safe tools only on coding-tools (all have usable defaults or no required args)
CODING_TOOLS_INCLUDE = ["list_allowed_roots", "list_directory", "find_files"]

# Full filesystem reads live on openclaw-tools (read_file/grep have defaults there)
OPENCLAW_TOOLS_INCLUDE = [
    "list_allowed_roots",
    "list_home",
    "list_desktop",
    "list_repo",
    "list_lmstudio",
    "list_openclaw",
    "read_readme",
    "read_openclaw_readme",
    "read_setup_guide",
    "read_catalog",
    "read_doc",
    "read_repo_file",
    "read_file",
    "list_directory",
    "grep",
    "find_files",
    "grep_repo",
]


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_filesystem_roots() -> list[Path]:
    """Load allowed MCP filesystem roots (default: entire home directory)."""
    home = Path.home()
    roots: list[Path] = [home]
    if FILESYSTEM_CONFIG.is_file():
        data = json.loads(FILESYSTEM_CONFIG.read_text(encoding="utf-8"))
        raw = data.get("allowedRoots") or []
        if raw:
            roots = []
            for entry in raw:
                s = str(entry).replace("__HOME__", str(home))
                roots.append(Path(s).expanduser().resolve())
    # dedupe preserve order
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _root_cli_args(roots: list[Path]) -> list[str]:
    args: list[str] = []
    for r in roots:
        args.extend(["--root", str(r)])
    return args


def _strip_root_args(args: list) -> list:
    out: list = []
    i = 0
    while i < len(args):
        if args[i] == "--root":
            i += 2
            continue
        out.append(args[i])
        i += 1
    return out


def _apply_roots_to_server(spec: dict, roots: list[Path]) -> None:
    spec["args"] = _strip_root_args(spec.get("args", [])) + _root_cli_args(roots)


def _openclaw_tools_spec(roots: list[Path]) -> dict:
    return {
        "command": "uv",
        "args": [
            "run",
            "--directory",
            str(LMSTUDIO),
            "python",
            str(OPENCLAW / "servers" / "openclaw_tools.py"),
            *_root_cli_args(roots),
        ],
        "env": {
            "OPENCLAW_REPO": str(ROOT),
        },
    }


def _fix_server_paths(servers: dict) -> None:
    """Patch stale paths after repo refactor."""
    lm = str(LMSTUDIO)
    rt = str(ROOT)
    replacements = [
        (f"{rt}/mcp_server/", f"{lm}/servers/"),
        ("mcp_server/", "servers/"),
        (f"{rt}/mcp/", f"{lm}/servers/"),
        ("mcp/coding_tools.py", "servers/coding_tools.py"),
        ("mcp/web_tools.py", "servers/web_tools.py"),
        ("mcp/think_delegate.py", "servers/think_delegate.py"),
        ("mcp/github_watch_tools.py", "servers/github_watch_tools.py"),
        (f'"{rt}"', f'"{lm}"'),
    ]

    for spec in servers.values():
        if not isinstance(spec, dict):
            continue
        cmd = spec.get("command")
        if isinstance(cmd, str):
            for old, new in replacements:
                cmd = cmd.replace(old, new)
            spec["command"] = cmd
        new_args: list = []
        for a in spec.get("args", []):
            if isinstance(a, str):
                for old, new in replacements:
                    a = a.replace(old, new)
                if a == rt:
                    a = lm
            new_args.append(a)
        spec["args"] = new_args
        env = spec.get("env", {})
        for key, val in list(env.items()):
            if not isinstance(val, str):
                continue
            if key == "OPENCLAW_REPO":
                env[key] = rt
            elif key == "MEMORY_FILE_PATH":
                env[key] = f"{lm}/.agent-memory.json"
            else:
                for old, new in replacements:
                    val = val.replace(old, new)
                env[key] = val


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=False, cwd=str(cwd) if cwd else None)


def _write_workspace_tools() -> None:
    src = OPENCLAW / "prompts" / "workspace-tools.md"
    dst = Path.home() / ".openclaw" / "workspace" / "TOOLS.md"
    if not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Wrote {dst}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Sync all servers, no tool filters")
    ap.add_argument("--no-restart", action="store_true")
    ap.add_argument("--no-workspace", action="store_true", help="Skip TOOLS.md update")
    args = ap.parse_args()

    if not LMSTUDIO.is_dir():
        sys.exit(f"LM Studio tree not found: {LMSTUDIO}")
    if not OPENCLAW_CONFIG.exists():
        sys.exit(f"OpenClaw not found: {OPENCLAW_CONFIG}")

    subprocess.run(
        [
            "uv", "run", "python",
            str(OPENCLAW / "scripts" / "setup_openclaw_lmstudio.py"),
            "--with-mcp",
        ],
        check=True,
        cwd=str(LMSTUDIO),
    )

    cfg = _load(OPENCLAW_CONFIG)
    cfg.setdefault("mcp", {}).setdefault("servers", {})
    roots = _load_filesystem_roots()
    print(f"Filesystem roots: {', '.join(str(r) for r in roots)}")

    _fix_server_paths(cfg["mcp"]["servers"])
    cfg["mcp"]["servers"]["openclaw-tools"] = _openclaw_tools_spec(roots)

    if "coding-tools" in cfg["mcp"]["servers"]:
        _apply_roots_to_server(cfg["mcp"]["servers"]["coding-tools"], roots)

    if not args.full:
        for name in ("playwright", "docker-tools"):
            if name in cfg["mcp"]["servers"]:
                cfg["mcp"]["servers"][name]["disabled"] = True

        cfg["mcp"]["servers"].setdefault("coding-tools", {})["toolFilter"] = {
            "include": CODING_TOOLS_INCLUDE,
        }
        cfg["mcp"]["servers"].setdefault("openclaw-tools", {})["toolFilter"] = {
            "include": OPENCLAW_TOOLS_INCLUDE,
        }

    backup = OPENCLAW_CONFIG.with_suffix(f".json.bak.{int(time.time())}")
    shutil.copy2(OPENCLAW_CONFIG, backup)
    OPENCLAW_CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"Patched paths + openclaw-tools -> {OPENCLAW_CONFIG}")

    if not args.no_workspace:
        _write_workspace_tools()

    if shutil.which("openclaw") and not args.full:
        _run(["openclaw", "mcp", "configure", "playwright", "--disable"])
        _run(["openclaw", "mcp", "configure", "docker-tools", "--disable"])
        _run([
            "openclaw", "mcp", "tools", "coding-tools",
            "--include", ",".join(CODING_TOOLS_INCLUDE),
        ])
        _run([
            "openclaw", "mcp", "tools", "openclaw-tools",
            "--include", ",".join(OPENCLAW_TOOLS_INCLUDE),
        ])

    if shutil.which("openclaw"):
        for name in ("openclaw-tools", "think-delegate", "triage", "coding-tools", "web-tools"):
            _run(["openclaw", "mcp", "probe", name])

    if not args.no_restart and shutil.which("openclaw"):
        _run(["openclaw", "gateway", "restart"])

    print("\nOpenClaw MCP profile ready.")
    print(f"Filesystem access: {', '.join(str(r) for r in roots)}")
    print('WhatsApp test: "Use openclaw-tools list_desktop"')
    print('Read project: openclaw-tools__read_file path=Desktop/Learning-01/session-1-claude-loops/README.md')


if __name__ == "__main__":
    main()

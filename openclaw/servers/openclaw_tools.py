"""
openclaw_tools.py — Slim MCP server for OpenClaw + small local models (Gemma).

Every tool is designed so empty {} or omitted optional args still work.
Use this server instead of coding-tools for reads on WhatsApp.

Run (from lmstudio/):
    uv run python ../openclaw/servers/openclaw_tools.py --root ~/Desktop
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("openclaw-tools")

REPO_DIRNAME = "lmstudio-agent-mcp"
DEFAULT_REPO_SUBPATH = f"{REPO_DIRNAME}/lmstudio"
ALLOWED_ROOTS: list[Path] = []


def _load_roots() -> list[Path]:
    raw = os.environ.get("WORKSPACE_ROOTS", "")
    roots: list[Path] = []
    if raw:
        for part in raw.split(os.pathsep):
            part = part.strip()
            if part:
                roots.append(Path(part).expanduser().resolve())
    if not roots:
        roots.append(Path.home() / "Desktop")
    return roots


def _repo_root() -> Path:
    """Git repo root (contains lmstudio/ and openclaw/)."""
    env = os.environ.get("OPENCLAW_REPO", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.name in ("lmstudio", "openclaw"):
            parent = p.parent
            if (parent / "lmstudio").is_dir() and (parent / "openclaw").is_dir():
                return parent
        if p.is_dir():
            return p
    for root in ALLOWED_ROOTS:
        candidate = root / REPO_DIRNAME
        if candidate.is_dir():
            return candidate.resolve()
    return (ALLOWED_ROOTS[0] / REPO_DIRNAME).resolve()


def _primary_root() -> Path:
    """First allowed root (usually ~)."""
    return ALLOWED_ROOTS[0] if ALLOWED_ROOTS else Path.home()


def _resolve_in_sandbox(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = _primary_root() / p
    p = p.resolve()
    for root in ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise PermissionError(
        f"Path {p} is outside allowed roots: {', '.join(str(r) for r in ALLOWED_ROOTS)}"
    )


def _read_text_file(target: Path, label: str) -> str:
    if not target.is_file():
        return f"Error: {label} not found at {target}"
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Error reading {label}: {exc!r}"
    lines = text.splitlines()
    numbered = [f"{i + 1:>5}|{line}" for i, line in enumerate(lines[:400])]
    suffix = f"\n... ({len(lines)} lines total, showing first 400)" if len(lines) > 400 else ""
    return "\n".join(numbered) + suffix


def _first_existing(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.is_file():
            return p
    return None


# --------------------------------------------------------------------------- #
# Discovery (zero-arg)
# --------------------------------------------------------------------------- #

@mcp.tool()
def list_allowed_roots() -> str:
    """List sandbox directories and project repo root. No arguments required."""
    root = _repo_root()
    lines = [
        f"Sandbox roots: {', '.join(str(r) for r in ALLOWED_ROOTS)}",
        f"Repo root: {root} ({'exists' if root.is_dir() else 'MISSING'})",
        f"LM Studio docs: {root / 'lmstudio'}",
        f"OpenClaw docs: {root / 'openclaw'}",
    ]
    return "\n".join(lines)


@mcp.tool()
def list_home() -> str:
    """List the user home directory (~). No arguments required."""
    return list_directory(path=".")


@mcp.tool()
def list_desktop() -> str:
    """List ~/Desktop. No arguments required."""
    return list_directory(path="Desktop")


@mcp.tool()
def list_repo() -> str:
    """List top-level lmstudio-agent-mcp entries. No arguments required."""
    root = _repo_root()
    if not root.is_dir():
        return f"Error: repo not found at {root}"
    entries = []
    for child in sorted(root.iterdir()):
        if child.name.startswith("."):
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{child.name}{suffix}")
    return "\n".join(entries) if entries else "(empty)"


@mcp.tool()
def list_lmstudio() -> str:
    """List lmstudio/ directory. No arguments required."""
    target = _repo_root() / "lmstudio"
    if not target.is_dir():
        return f"Error: {target} not found"
    entries = []
    for child in sorted(target.iterdir()):
        if child.name.startswith("."):
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{child.name}{suffix}")
    return "\n".join(entries) if entries else "(empty)"


@mcp.tool()
def list_openclaw() -> str:
    """List openclaw/ directory. No arguments required."""
    target = _repo_root() / "openclaw"
    if not target.is_dir():
        return f"Error: {target} not found"
    entries = []
    for child in sorted(target.iterdir()):
        if child.name.startswith("."):
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{child.name}{suffix}")
    return "\n".join(entries) if entries else "(empty)"


# --------------------------------------------------------------------------- #
# Doc reads (zero-arg)
# --------------------------------------------------------------------------- #

@mcp.tool()
def read_readme() -> str:
    """Read LM Studio tools reference (lmstudio/README.md). No arguments required."""
    root = _repo_root()
    found = _first_existing(
        root / "lmstudio/README.md",
        root / "README.md",
    )
    if not found:
        return f"Error: README not found under {root}"
    return _read_text_file(found, "README.md")


@mcp.tool()
def read_openclaw_readme() -> str:
    """Read OpenClaw tools reference (openclaw/README.md). No arguments required."""
    return _read_text_file(_repo_root() / "openclaw/README.md", "openclaw/README.md")


@mcp.tool()
def read_setup_guide() -> str:
    """Read lmstudio/SETUP.md if present. No arguments required."""
    return _read_text_file(_repo_root() / "lmstudio/SETUP.md", "SETUP.md")


@mcp.tool()
def read_catalog() -> str:
    """Read lmstudio/CATALOG.md if present. No arguments required."""
    return _read_text_file(_repo_root() / "lmstudio/CATALOG.md", "CATALOG.md")


@mcp.tool()
def read_doc(filename: str = "README.md") -> str:
    """Read a doc file from lmstudio/ or openclaw/. Default: README.md."""
    root = _repo_root()
    for base in (root / "lmstudio", root / "openclaw", root):
        target = base / filename
        if target.is_file():
            return _read_text_file(target, filename)
    return f"Error: {filename} not found under lmstudio/, openclaw/, or repo root"


@mcp.tool()
def read_repo_file(relative_path: str = "lmstudio/README.md") -> str:
    """Read any file under repo root by relative path. Default: lmstudio/README.md."""
    root = _repo_root()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return f"Error: path escapes repo root: {relative_path}"
    if not target.is_file():
        return f"Error: not a file: {target}"
    return _read_text_file(target, relative_path)


# --------------------------------------------------------------------------- #
# Sandbox I/O (Gemma-safe defaults — use instead of coding-tools__read_file)
# --------------------------------------------------------------------------- #

@mcp.tool()
def read_file(
    path: str = "Desktop",
    offset: int = 0,
    limit: int = 0,
) -> str:
    """Read a UTF-8 file under allowed roots (default sandbox: home ~).

    Paths are relative to home, e.g.:
      Desktop/Learning-01/session-1-claude-loops/README.md
      Documents/notes.txt
      lmstudio-agent-mcp/lmstudio/README.md

    Default path 'Desktop' lists Desktop if you pass {} (returns directory listing).
    """
    target = _resolve_in_sandbox(path)
    if target.is_dir():
        entries = []
        for child in sorted(target.iterdir()):
            if child.name.startswith("."):
                continue
            suffix = "/" if child.is_dir() else ""
            entries.append(f"{child.name}{suffix}")
        return f"(directory {path})\n" + ("\n".join(entries) if entries else "(empty)")
    if not target.is_file():
        return f"Error: not a file: {target}"
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"Error reading file: {exc!r}"
    end = len(lines) if limit <= 0 else min(len(lines), offset + limit)
    out = [f"{i + 1:>6}|{lines[i]}" for i in range(offset, end)]
    return "\n".join(out) if out else "(no lines in range)"


@mcp.tool()
def list_directory(path: str = "Desktop") -> str:
    """List a directory under allowed roots. Default: Desktop."""
    target = _resolve_in_sandbox(path)
    if not target.is_dir():
        return f"Error: not a directory: {target}"
    entries = []
    for child in sorted(target.iterdir()):
        if child.name.startswith("."):
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{child.name}{suffix}")
    return "\n".join(entries) if entries else "(empty)"


@mcp.tool()
def grep(
    pattern: str = "openclaw",
    path: str = "Desktop",
    max_results: int = 50,
) -> str:
    """Regex search under a path (relative to home). Defaults: Desktop."""
    root = _resolve_in_sandbox(path)
    if not root.exists():
        return f"Error: {root} does not exist"
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"Invalid regex: {exc}"
    hits: list[str] = []
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            if name.startswith("."):
                continue
            fpath = Path(dirpath) / name
            try:
                with fpath.open("r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if regex.search(line):
                            try:
                                rel = fpath.relative_to(_primary_root())
                            except ValueError:
                                rel = fpath
                            hits.append(f"{rel}:{lineno}: {line.rstrip()}")
                            if len(hits) >= max_results:
                                return "\n".join(hits) + "\n... (truncated)"
            except OSError:
                continue
    return "\n".join(hits) if hits else "(no matches)"


@mcp.tool()
def find_files(
    pattern: str = "*.md",
    path: str = "Desktop",
    max_results: int = 100,
) -> str:
    """Glob files under a path (relative to home). Defaults: *.md on Desktop."""
    root = _resolve_in_sandbox(path)
    if not root.exists():
        return f"Error: {root} does not exist"
    matches: list[str] = []
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            if fnmatch.fnmatch(pattern, name):
                fpath = Path(dirpath) / name
                try:
                    rel = fpath.relative_to(_primary_root())
                except ValueError:
                    rel = fpath
                matches.append(str(rel))
                if len(matches) >= max_results:
                    return "\n".join(matches) + "\n... (truncated)"
    return "\n".join(matches) if matches else "(no matches)"


@mcp.tool()
def grep_repo(pattern: str = "think-delegate") -> str:
    """Search repo source (lmstudio-agent-mcp) for a regex. Default: think-delegate."""
    return grep(pattern=pattern, path=REPO_DIRNAME, max_results=50)


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClaw-friendly slim MCP tools")
    parser.add_argument("--root", action="append", default=[], help="Sandbox root (repeatable)")
    args = parser.parse_args()
    global ALLOWED_ROOTS
    ALLOWED_ROOTS = _load_roots()
    if args.root:
        ALLOWED_ROOTS = [Path(r).expanduser().resolve() for r in args.root]
    print(
        f"[openclaw-tools] roots={[str(r) for r in ALLOWED_ROOTS]} repo={_repo_root()}",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

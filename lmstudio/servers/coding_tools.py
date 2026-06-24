"""
coding_tools.py — A FastMCP server that gives a local LLM (e.g. Gemma in LM Studio)
real "agent" powers: read/write/edit files, search code, run shell commands,
execute Python/Node snippets, and use git.

Transport: stdio (the format LM Studio's mcp.json expects).

Safety model
------------
- All filesystem access is sandboxed to one or more ALLOWED ROOTS.
  By default the root is the directory you launch the server from, but you
  should pass explicit roots via the WORKSPACE_ROOTS env var (os.pathsep
  separated) or the --root CLI flag.
- A blocklist stops obviously destructive shell commands. This is a guardrail,
  NOT a real sandbox — only point this at directories you are willing to let
  the model modify.

Run directly:
    python coding_tools.py --root /path/to/project

Or let LM Studio launch it via mcp.json (see lmstudio/mcp/mcp.json).
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("local-coding-tools")

# --------------------------------------------------------------------------- #
# Sandbox configuration
# --------------------------------------------------------------------------- #

def _load_roots() -> list[Path]:
    raw = os.environ.get("WORKSPACE_ROOTS", "")
    roots: list[Path] = []
    if raw:
        for part in raw.split(os.pathsep):
            part = part.strip()
            if part:
                roots.append(Path(part).expanduser().resolve())
    if not roots:
        roots.append(Path.cwd().resolve())
    return roots


ALLOWED_ROOTS: list[Path] = _load_roots()

# Commands we refuse to run no matter what. Defense-in-depth, not a jail.
_BLOCKED_PATTERNS = [
    r"\brm\s+-rf?\s+/",          # rm -rf / ...
    r"\brm\s+-rf?\s+~",          # rm -rf ~
    r":\(\)\s*\{",               # fork bomb
    r"\bmkfs\b",
    r"\bdd\b\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bsudo\b",
    r">\s*/dev/sd",
    r"\bchmod\s+-R\s+777\s+/",
]


def _resolve_in_sandbox(path: str) -> Path:
    """Resolve `path` and ensure it lives inside an allowed root."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (ALLOWED_ROOTS[0] / p)
    p = p.resolve()
    for root in ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise PermissionError(
        f"Path {p} is outside the allowed roots: "
        f"{', '.join(str(r) for r in ALLOWED_ROOTS)}"
    )


def _is_command_blocked(command: str) -> str | None:
    for pat in _BLOCKED_PATTERNS:
        if re.search(pat, command):
            return pat
    return None


# --------------------------------------------------------------------------- #
# Filesystem tools
# --------------------------------------------------------------------------- #

@mcp.tool()
def list_allowed_roots() -> str:
    """List the directories this server is allowed to read and write."""
    return "\n".join(str(r) for r in ALLOWED_ROOTS)


@mcp.tool()
def list_directory(path: str = ".") -> str:
    """List files and folders at `path`. Directories are suffixed with '/'."""
    target = _resolve_in_sandbox(path)
    if not target.exists():
        return f"Error: {target} does not exist."
    if not target.is_dir():
        return f"Error: {target} is not a directory."
    entries = []
    for child in sorted(target.iterdir()):
        suffix = "/" if child.is_dir() else ""
        size = "" if child.is_dir() else f"  ({child.stat().st_size} bytes)"
        entries.append(f"{child.name}{suffix}{size}")
    return "\n".join(entries) if entries else "(empty directory)"


@mcp.tool()
def read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """Read a UTF-8 text file. Optionally start at line `offset` (0-indexed) and
    read at most `limit` lines (0 = read everything). Returns numbered lines."""
    target = _resolve_in_sandbox(path)
    if not target.exists():
        return f"Error: {target} does not exist."
    if not target.is_file():
        return f"Error: {target} is not a file."
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        return f"Error reading file: {exc!r}"
    end = len(lines) if limit <= 0 else min(len(lines), offset + limit)
    out = [f"{i + 1:>6}|{lines[i]}" for i in range(offset, end)]
    return "\n".join(out) if out else "(no lines in range)"


@mcp.tool()
def write_file(path: str, content: str, overwrite: bool = True) -> str:
    """Create or overwrite a text file with `content`. Set overwrite=False to
    refuse writing if the file already exists. Parent dirs are created."""
    target = _resolve_in_sandbox(path)
    if target.exists() and not overwrite:
        return f"Error: {target} already exists and overwrite=False."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return f"Error writing file: {exc!r}"
    return f"Wrote {len(content)} chars to {target}."


@mcp.tool()
def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Replace `old_string` with `new_string` in a file. By default `old_string`
    must appear exactly once; set replace_all=True to replace every occurrence."""
    target = _resolve_in_sandbox(path)
    if not target.is_file():
        return f"Error: {target} is not a file."
    text = target.read_text(encoding="utf-8", errors="replace")
    count = text.count(old_string)
    if count == 0:
        return "Error: old_string not found in file."
    if count > 1 and not replace_all:
        return f"Error: old_string appears {count} times; pass replace_all=True or add more context."
    new_text = text.replace(old_string, new_string, -1 if replace_all else 1)
    target.write_text(new_text, encoding="utf-8")
    replaced = count if replace_all else 1
    return f"Replaced {replaced} occurrence(s) in {target}."


@mcp.tool()
def create_directory(path: str) -> str:
    """Create a directory (and any missing parents)."""
    target = _resolve_in_sandbox(path)
    target.mkdir(parents=True, exist_ok=True)
    return f"Created directory {target}."


@mcp.tool()
def move_path(source: str, destination: str) -> str:
    """Move or rename a file/directory within the sandbox."""
    src = _resolve_in_sandbox(source)
    dst = _resolve_in_sandbox(destination)
    if not src.exists():
        return f"Error: {src} does not exist."
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return f"Moved {src} -> {dst}."


@mcp.tool()
def delete_path(path: str) -> str:
    """Delete a single file (not a directory). Use with care."""
    target = _resolve_in_sandbox(path)
    if not target.exists():
        return f"Error: {target} does not exist."
    if target.is_dir():
        return "Error: refusing to delete a directory. Delete files individually."
    target.unlink()
    return f"Deleted {target}."


# --------------------------------------------------------------------------- #
# Search tools
# --------------------------------------------------------------------------- #

@mcp.tool()
def find_files(pattern: str = "*", path: str = ".", max_results: int = 200) -> str:
    """Recursively find files matching a glob `pattern` (e.g. '*.py') under `path`."""
    root = _resolve_in_sandbox(path)
    matches: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip common noise
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__", ".venv", "venv"}]
        for name in filenames:
            if fnmatch.fnmatch(name, pattern):
                matches.append(str(Path(dirpath) / name))
                if len(matches) >= max_results:
                    return "\n".join(matches) + f"\n... (truncated at {max_results})"
    return "\n".join(matches) if matches else "(no matches)"


@mcp.tool()
def grep(pattern: str, path: str = ".", glob: str = "*", max_results: int = 200) -> str:
    """Search file contents for a regex `pattern`. Restrict files with `glob`.
    Returns matching lines as 'file:line: content'."""
    root = _resolve_in_sandbox(path)
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"Error: invalid regex: {exc}"
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__", ".venv", "venv"}]
        for name in filenames:
            if not fnmatch.fnmatch(name, glob):
                continue
            fpath = Path(dirpath) / name
            try:
                with fpath.open("r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if regex.search(line):
                            results.append(f"{fpath}:{lineno}: {line.rstrip()}")
                            if len(results) >= max_results:
                                return "\n".join(results) + f"\n... (truncated at {max_results})"
            except Exception:  # noqa: BLE001
                continue
    return "\n".join(results) if results else "(no matches)"


# --------------------------------------------------------------------------- #
# Execution tools
# --------------------------------------------------------------------------- #

@mcp.tool()
def run_shell(command: str, cwd: str = ".", timeout: int = 60) -> str:
    """Run a shell command inside the sandbox and return combined stdout/stderr.
    Destructive commands (rm -rf /, mkfs, sudo, ...) are blocked. Times out."""
    blocked = _is_command_blocked(command)
    if blocked:
        return f"Error: command blocked by safety policy (matched: {blocked})."
    workdir = _resolve_in_sandbox(cwd)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s."
    out = proc.stdout or ""
    err = proc.stderr or ""
    body = (out + ("\n" + err if err else "")).strip()
    return f"[exit {proc.returncode}]\n{body}" if body else f"[exit {proc.returncode}] (no output)"


@mcp.tool()
def run_python(code: str, cwd: str = ".", timeout: int = 60) -> str:
    """Execute a Python snippet with the current interpreter. Returns output."""
    workdir = _resolve_in_sandbox(cwd)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: python execution timed out after {timeout}s."
    body = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return f"[exit {proc.returncode}]\n{body}" if body else f"[exit {proc.returncode}] (no output)"


@mcp.tool()
def run_node(code: str, cwd: str = ".", timeout: int = 60) -> str:
    """Execute a JavaScript snippet with Node.js. Returns output."""
    workdir = _resolve_in_sandbox(cwd)
    try:
        proc = subprocess.run(
            ["node", "-e", code],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return "Error: node is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return f"Error: node execution timed out after {timeout}s."
    body = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return f"[exit {proc.returncode}]\n{body}" if body else f"[exit {proc.returncode}] (no output)"


# --------------------------------------------------------------------------- #
# Git tools (thin wrappers, all sandboxed)
# --------------------------------------------------------------------------- #

def _git(args: list[str], cwd: str) -> str:
    workdir = _resolve_in_sandbox(cwd)
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return "Error: git is not installed."
    body = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return body or f"[git exit {proc.returncode}]"


@mcp.tool()
def git_status(cwd: str = ".") -> str:
    """Show `git status` for the repo at cwd."""
    return _git(["status", "--short", "--branch"], cwd)


@mcp.tool()
def git_diff(cwd: str = ".", staged: bool = False) -> str:
    """Show `git diff` (working tree, or staged changes if staged=True)."""
    args = ["diff"] + (["--cached"] if staged else [])
    return _git(args, cwd)


@mcp.tool()
def git_log(cwd: str = ".", max_count: int = 10) -> str:
    """Show the most recent commits as a compact log."""
    return _git(["log", f"-{max_count}", "--oneline", "--decorate"], cwd)


@mcp.tool()
def git_commit(message: str, cwd: str = ".", add_all: bool = True) -> str:
    """Stage changes (add_all=True stages everything) and create a commit."""
    if add_all:
        _git(["add", "-A"], cwd)
    return _git(["commit", "-m", message], cwd)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Local coding-tools MCP server")
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Allowed workspace root (repeatable). Overrides WORKSPACE_ROOTS.",
    )
    args = parser.parse_args()
    if args.root:
        global ALLOWED_ROOTS
        ALLOWED_ROOTS = [Path(r).expanduser().resolve() for r in args.root]
    print(
        f"[local-coding-tools] sandbox roots: {[str(r) for r in ALLOWED_ROOTS]}",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

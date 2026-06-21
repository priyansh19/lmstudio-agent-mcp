"""
docker_tools.py — A FastMCP server that lets a local LLM operate Docker:
list/inspect containers and images, build, run, exec, view logs, manage
lifecycle, and drive docker compose.

Transport: stdio. Requires the `docker` CLI on PATH (Docker Desktop / Engine).

Run directly:
    python docker_tools.py

Safety
------
- Every tool shells out to the real `docker` CLI, so it can affect your whole
  Docker environment (not sandboxed to a directory like the file tools).
- A blocklist refuses the most destructive operations (system prune -a -f,
  volume rm with force-all, etc.). It is a guardrail, not a jail.
- Prefer reviewing tool calls in the LM Studio UI before approving them.
"""

from __future__ import annotations

import re
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("local-docker-tools")

_BLOCKED_PATTERNS = [
    r"system\s+prune\s+.*-a.*-f",   # nuke everything unattended
    r"\bvolume\s+prune\s+.*-f",     # wipe all volumes unattended
    r"\brmi?\s+.*-f.*\$\(",         # force-remove via command substitution
]


def _blocked(args: list[str]) -> str | None:
    joined = " ".join(args)
    for pat in _BLOCKED_PATTERNS:
        if re.search(pat, joined):
            return pat
    return None


def _docker(args: list[str], timeout: int = 120) -> str:
    blocked = _blocked(args)
    if blocked:
        return f"Error: docker command blocked by safety policy (matched: {blocked})."
    try:
        proc = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return "Error: docker CLI not found. Is Docker installed and on PATH?"
    except subprocess.TimeoutExpired:
        return f"Error: docker command timed out after {timeout}s."
    body = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return f"[exit {proc.returncode}]\n{body}" if body else f"[exit {proc.returncode}] (no output)"


# --------------------------------------------------------------------------- #
# Inspection
# --------------------------------------------------------------------------- #

@mcp.tool()
def docker_version() -> str:
    """Show Docker client/server version and confirm the daemon is reachable."""
    return _docker(["version"])


@mcp.tool()
def docker_ps(all_containers: bool = False) -> str:
    """List containers. Set all_containers=True to include stopped ones."""
    args = ["ps", "--format", "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}\t{{.Ports}}"]
    if all_containers:
        args.insert(1, "-a")
    return _docker(args)


@mcp.tool()
def docker_images() -> str:
    """List local Docker images."""
    return _docker(["images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"])


@mcp.tool()
def docker_inspect(target: str) -> str:
    """Inspect a container or image (JSON config, mounts, networking, etc.)."""
    return _docker(["inspect", target])


@mcp.tool()
def docker_logs(container: str, tail: int = 200) -> str:
    """Show the last `tail` lines of a container's logs."""
    return _docker(["logs", "--tail", str(tail), container])


@mcp.tool()
def docker_stats() -> str:
    """One-shot resource usage (CPU/mem) snapshot of running containers."""
    return _docker(["stats", "--no-stream", "--format",
                    "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"])


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #

@mcp.tool()
def docker_run(image: str, command: str = "", detach: bool = True,
               name: str = "", ports: str = "", env: str = "",
               volumes: str = "") -> str:
    """Run a container from `image`.
    - command: optional command to run inside the container
    - detach: run in background (default True)
    - name:   container name
    - ports:  space-separated host:container mappings, e.g. '8080:80 5432:5432'
    - env:    space-separated KEY=VALUE pairs
    - volumes: space-separated host:container mounts
    """
    args = ["run"]
    if detach:
        args.append("-d")
    if name:
        args += ["--name", name]
    for p in ports.split():
        args += ["-p", p]
    for e in env.split():
        args += ["-e", e]
    for v in volumes.split():
        args += ["-v", v]
    args.append(image)
    if command:
        args += command.split()
    return _docker(args)


@mcp.tool()
def docker_exec(container: str, command: str) -> str:
    """Run a command inside a running container (non-interactive)."""
    return _docker(["exec", container, "sh", "-c", command])


@mcp.tool()
def docker_stop(container: str) -> str:
    """Stop a running container."""
    return _docker(["stop", container])


@mcp.tool()
def docker_start(container: str) -> str:
    """Start a stopped container."""
    return _docker(["start", container])


@mcp.tool()
def docker_rm(container: str, force: bool = False) -> str:
    """Remove a container. Set force=True to remove a running one."""
    args = ["rm"]
    if force:
        args.append("-f")
    args.append(container)
    return _docker(args)


@mcp.tool()
def docker_rmi(image: str, force: bool = False) -> str:
    """Remove an image. Set force=True to force removal."""
    args = ["rmi"]
    if force:
        args.append("-f")
    args.append(image)
    return _docker(args)


# --------------------------------------------------------------------------- #
# Build & registry
# --------------------------------------------------------------------------- #

@mcp.tool()
def docker_build(path: str, tag: str, dockerfile: str = "") -> str:
    """Build an image from a build context `path`, tagging it `tag`.
    Optionally point at a specific `dockerfile`."""
    args = ["build", "-t", tag]
    if dockerfile:
        args += ["-f", dockerfile]
    args.append(path)
    return _docker(args, timeout=600)


@mcp.tool()
def docker_pull(image: str) -> str:
    """Pull an image from a registry."""
    return _docker(["pull", image], timeout=600)


# --------------------------------------------------------------------------- #
# Compose
# --------------------------------------------------------------------------- #

@mcp.tool()
def docker_compose(action: str, path: str = ".", services: str = "") -> str:
    """Run docker compose in directory `path`.
    action: one of up | down | ps | logs | build | restart | pull
    services: optional space-separated service names.
    'up' runs detached (-d)."""
    valid = {"up", "down", "ps", "logs", "build", "restart", "pull"}
    if action not in valid:
        return f"Error: action must be one of {sorted(valid)}."
    args = ["compose", "--project-directory", path, action]
    if action == "up":
        args.append("-d")
    if action == "logs":
        args += ["--tail", "200"]
    args += services.split()
    return _docker(args, timeout=600)


if __name__ == "__main__":
    mcp.run(transport="stdio")

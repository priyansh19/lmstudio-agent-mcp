"""
github_watch_tools.py — Give a local LLM "hook-like" awareness of GitHub state.

MCP is pull-based: the model calls a tool and gets a response — GitHub cannot
push into the model. This server simulates event hooks by caching the last-seen
state of the PRs / issues / repos you "watch", then reporting *what changed*
since the previous poll (CI/Actions conclusions, review decisions, merge state,
new comments, open/closed transitions, etc.).

Typical loop the agent runs:
    gh_watch("owner/repo#42")        # start tracking a PR
    gh_watch("owner/repo")           # track repo-level activity + Actions
    ... later, repeatedly ...
    gh_poll()                        # -> concise list of changes since last poll

It also exposes on-demand status tools (gh_pr_status, gh_issue_status,
gh_workflow_runs, gh_repo_activity) for one-off checks.

Auth: reads GITHUB_PERSONAL_ACCESS_TOKEN (or GITHUB_TOKEN) from the environment.
The installer injects it the same way it does for the `github` server.

Transport: stdio.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("github-watch")

API = "https://api.github.com"
STATE_FILE = Path(os.environ.get(
    "GITHUB_WATCH_STATE",
    str(Path.home() / ".lmstudio-agent" / "github_watch_state.json"),
))


def _token() -> str:
    return os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def _api(path: str, params: dict | None = None) -> Any:
    """GET an API path (relative to https://api.github.com) and return JSON."""
    token = _token()
    if not token:
        return {"_error": "No GitHub token in environment (GITHUB_PERSONAL_ACCESS_TOKEN)."}
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "lmstudio-agent-github-watch/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return {"_error": f"HTTP {exc.code} for {path}: {detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{exc!r}"}


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"watches": {}, "snapshots": {}}
    return {"watches": {}, "snapshots": {}}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _split_repo(repo: str) -> tuple[str, str]:
    owner, _, name = repo.partition("/")
    return owner, name


# --------------------------------------------------------------------------- #
# State signatures (what we diff between polls)
# --------------------------------------------------------------------------- #

def _checks_summary(repo: str, sha: str) -> dict:
    owner, name = _split_repo(repo)
    runs = _api(f"/repos/{owner}/{name}/commits/{sha}/check-runs")
    summary = {"total": 0, "success": 0, "failure": 0, "pending": 0, "names_failing": []}
    if isinstance(runs, dict) and "check_runs" in runs:
        for cr in runs["check_runs"]:
            summary["total"] += 1
            concl = cr.get("conclusion")
            if cr.get("status") != "completed":
                summary["pending"] += 1
            elif concl == "success":
                summary["success"] += 1
            elif concl in ("failure", "timed_out", "cancelled", "action_required"):
                summary["failure"] += 1
                summary["names_failing"].append(cr.get("name"))
    return summary


def _pr_signature(repo: str, number: int) -> dict:
    owner, name = _split_repo(repo)
    pr = _api(f"/repos/{owner}/{name}/pulls/{number}")
    if not isinstance(pr, dict) or "_error" in pr:
        return {"_error": pr.get("_error", "unknown") if isinstance(pr, dict) else "bad response"}
    sha = pr.get("head", {}).get("sha", "")
    reviews = _api(f"/repos/{owner}/{name}/pulls/{number}/reviews")
    latest_by_user: dict[str, str] = {}
    if isinstance(reviews, list):
        for r in reviews:
            u = (r.get("user") or {}).get("login", "?")
            latest_by_user[u] = r.get("state", "")
    return {
        "type": "pr",
        "title": pr.get("title"),
        "state": pr.get("state"),
        "draft": pr.get("draft"),
        "merged": pr.get("merged"),
        "mergeable_state": pr.get("mergeable_state"),
        "comments": pr.get("comments", 0) + pr.get("review_comments", 0),
        "commits": pr.get("commits"),
        "head_sha": sha,
        "reviews": latest_by_user,
        "checks": _checks_summary(repo, sha) if sha else {},
        "updated_at": pr.get("updated_at"),
    }


def _issue_signature(repo: str, number: int) -> dict:
    owner, name = _split_repo(repo)
    iss = _api(f"/repos/{owner}/{name}/issues/{number}")
    if not isinstance(iss, dict) or "_error" in iss:
        return {"_error": iss.get("_error", "unknown") if isinstance(iss, dict) else "bad response"}
    return {
        "type": "issue",
        "title": iss.get("title"),
        "state": iss.get("state"),
        "labels": sorted(l.get("name", "") for l in iss.get("labels", [])),
        "assignees": sorted(a.get("login", "") for a in iss.get("assignees", [])),
        "comments": iss.get("comments", 0),
        "updated_at": iss.get("updated_at"),
    }


def _repo_signature(repo: str) -> dict:
    owner, name = _split_repo(repo)
    runs = _api(f"/repos/{owner}/{name}/actions/runs", {"per_page": 5})
    latest = {}
    if isinstance(runs, dict) and runs.get("workflow_runs"):
        wr = runs["workflow_runs"][0]
        latest = {
            "id": wr.get("id"),
            "name": wr.get("name"),
            "status": wr.get("status"),
            "conclusion": wr.get("conclusion"),
            "branch": wr.get("head_branch"),
        }
    return {"type": "repo", "latest_run": latest}


def _signature(target: str) -> dict:
    if "#" in target:
        repo, _, num = target.partition("#")
        number = int(num)
        # Heuristic: PRs and issues share numbering; try PR first, fall back to issue.
        sig = _pr_signature(repo, number)
        if sig.get("_error") and "404" in str(sig.get("_error")):
            return _issue_signature(repo, number)
        return sig
    return _repo_signature(target)


def _diff(old: dict, new: dict) -> list[str]:
    if not old:
        return ["now tracking (baseline captured)"]
    if new.get("_error"):
        return [f"error fetching: {new['_error']}"]
    changes: list[str] = []
    t = new.get("type")
    if t == "pr":
        for field in ("state", "draft", "merged", "mergeable_state", "title"):
            if old.get(field) != new.get(field):
                changes.append(f"{field}: {old.get(field)} -> {new.get(field)}")
        oc, nc = old.get("checks", {}), new.get("checks", {})
        if (oc.get("success"), oc.get("failure"), oc.get("pending")) != \
           (nc.get("success"), nc.get("failure"), nc.get("pending")):
            changes.append(
                f"CI/Actions: {nc.get('success',0)} ok / {nc.get('failure',0)} failing / "
                f"{nc.get('pending',0)} running"
                + (f" (failing: {', '.join(filter(None, nc.get('names_failing', [])))})"
                   if nc.get("names_failing") else "")
            )
        if old.get("reviews") != new.get("reviews"):
            changes.append(f"reviews: {new.get('reviews')}")
        if old.get("comments") != new.get("comments"):
            changes.append(f"comments: {old.get('comments')} -> {new.get('comments')}")
        if old.get("head_sha") != new.get("head_sha"):
            changes.append("new commits pushed")
    elif t == "issue":
        for field in ("state", "title"):
            if old.get(field) != new.get(field):
                changes.append(f"{field}: {old.get(field)} -> {new.get(field)}")
        if old.get("labels") != new.get("labels"):
            changes.append(f"labels: {new.get('labels')}")
        if old.get("assignees") != new.get("assignees"):
            changes.append(f"assignees: {new.get('assignees')}")
        if old.get("comments") != new.get("comments"):
            changes.append(f"comments: {old.get('comments')} -> {new.get('comments')}")
    elif t == "repo":
        if old.get("latest_run") != new.get("latest_run"):
            lr = new.get("latest_run", {})
            changes.append(
                f"Actions run '{lr.get('name')}' on {lr.get('branch')}: "
                f"{lr.get('status')}/{lr.get('conclusion')}"
            )
    return changes


# --------------------------------------------------------------------------- #
# Watch management
# --------------------------------------------------------------------------- #

@mcp.tool()
def gh_watch(target: str) -> str:
    """Start watching a target for state changes.
    target = 'owner/repo#123' (a PR or issue) or 'owner/repo' (repo Actions/activity)."""
    state = _load_state()
    sig = _signature(target)
    if sig.get("_error"):
        return f"Could not watch {target}: {sig['_error']}"
    state["watches"][target] = True
    state["snapshots"][target] = sig
    _save_state(state)
    label = sig.get("title") or target
    return f"Now watching {target} ({sig.get('type')}): {label}"


@mcp.tool()
def gh_unwatch(target: str) -> str:
    """Stop watching a target."""
    state = _load_state()
    state["watches"].pop(target, None)
    state["snapshots"].pop(target, None)
    _save_state(state)
    return f"Stopped watching {target}."


@mcp.tool()
def gh_list_watches() -> str:
    """List everything currently being watched."""
    state = _load_state()
    if not state["watches"]:
        return "(watching nothing yet — use gh_watch)"
    lines = []
    for tgt in sorted(state["watches"]):
        snap = state["snapshots"].get(tgt, {})
        lines.append(f"- {tgt} [{snap.get('type','?')}] {snap.get('title','')}".rstrip())
    return "\n".join(lines)


@mcp.tool()
def gh_poll() -> str:
    """THE hook. Check every watched target and report what changed since the
    last poll (CI/Actions, reviews, merge state, comments, open/closed, etc.).
    Updates the cached state so the next poll only shows new changes."""
    state = _load_state()
    if not state["watches"]:
        return "(watching nothing yet — use gh_watch first)"
    out: list[str] = []
    for tgt in sorted(state["watches"]):
        new = _signature(tgt)
        old = state["snapshots"].get(tgt, {})
        changes = _diff(old, new)
        if changes and changes != ["now tracking (baseline captured)"]:
            out.append(f"### {tgt}\n" + "\n".join(f"  - {c}" for c in changes))
        if not new.get("_error"):
            state["snapshots"][tgt] = new
    _save_state(state)
    return "\n\n".join(out) if out else "No changes since last poll."


# --------------------------------------------------------------------------- #
# On-demand status (no watching required)
# --------------------------------------------------------------------------- #

@mcp.tool()
def gh_pr_status(repo: str, number: int) -> str:
    """Full current status of a pull request: state, draft/merge state, reviews,
    and CI/Actions check results. repo = 'owner/repo'."""
    sig = _pr_signature(repo, number)
    if sig.get("_error"):
        return f"Error: {sig['_error']}"
    c = sig.get("checks", {})
    return (
        f"PR {repo}#{number}: {sig['title']}\n"
        f"  state={sig['state']} draft={sig['draft']} merged={sig['merged']} "
        f"mergeable={sig['mergeable_state']}\n"
        f"  commits={sig['commits']} comments={sig['comments']} head={sig['head_sha'][:8]}\n"
        f"  reviews={sig['reviews']}\n"
        f"  checks: {c.get('success',0)} ok / {c.get('failure',0)} failing / "
        f"{c.get('pending',0)} running"
        + (f"  failing: {', '.join(filter(None, c.get('names_failing', [])))}"
           if c.get("names_failing") else "")
    )


@mcp.tool()
def gh_issue_status(repo: str, number: int) -> str:
    """Current status of an issue: state, labels, assignees, comment count."""
    sig = _issue_signature(repo, number)
    if sig.get("_error"):
        return f"Error: {sig['_error']}"
    return (
        f"Issue {repo}#{number}: {sig['title']}\n"
        f"  state={sig['state']} labels={sig['labels']} "
        f"assignees={sig['assignees']} comments={sig['comments']}"
    )


@mcp.tool()
def gh_workflow_runs(repo: str, branch: str = "", limit: int = 8) -> str:
    """Recent GitHub Actions workflow runs (optionally for a branch), with
    status and conclusion. repo = 'owner/repo'."""
    owner, name = _split_repo(repo)
    params: dict = {"per_page": limit}
    if branch:
        params["branch"] = branch
    runs = _api(f"/repos/{owner}/{name}/actions/runs", params)
    if isinstance(runs, dict) and runs.get("_error"):
        return f"Error: {runs['_error']}"
    wruns = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
    if not wruns:
        return "(no workflow runs)"
    lines = []
    for r in wruns[:limit]:
        lines.append(
            f"- {r.get('name')} [{r.get('head_branch')}] "
            f"{r.get('status')}/{r.get('conclusion')}  ({r.get('html_url')})"
        )
    return "\n".join(lines)


@mcp.tool()
def gh_repo_activity(repo: str, limit: int = 10) -> str:
    """Recent repository events (pushes, PRs, issues, comments). repo='owner/repo'."""
    owner, name = _split_repo(repo)
    events = _api(f"/repos/{owner}/{name}/events", {"per_page": limit})
    if isinstance(events, dict) and events.get("_error"):
        return f"Error: {events['_error']}"
    if not isinstance(events, list) or not events:
        return "(no recent events)"
    lines = []
    for e in events[:limit]:
        actor = (e.get("actor") or {}).get("login", "?")
        lines.append(f"- {e.get('type')} by {actor} at {e.get('created_at')}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")

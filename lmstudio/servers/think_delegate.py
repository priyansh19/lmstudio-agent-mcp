"""
think_delegate.py — Escalation MCP for local SLMs (LM Studio only).

Your small local model handles day-to-day work. When a task needs ultra-level
reasoning or knowledge beyond the model's cutoff, YOU (the local model) call
one of these tools. The tool forwards the task to a connected expert and
returns the answer so you can continue implementing locally.

Default backend: Claude Code CLI (`claude -p`) using your subscription login —
NOT the Anthropic API (no API key billing). Optional fallbacks: anthropic API,
OpenAI-compatible API.

Run:
    uv run python mcp/think_delegate.py
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("think-delegate")

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) think-delegate/1.0"
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_WS_RE = re.compile(r"\n\s*\n\s*\n+")


def _provider() -> str:
    return os.environ.get("THINK_PROVIDER", "claude-cli").strip().lower()


def _think_model(deep: bool = False) -> str:
    if deep:
        return os.environ.get("THINK_DEEP_MODEL", os.environ.get("THINK_MODEL", "opus"))
    return os.environ.get("THINK_MODEL", "sonnet")


def _claude_bin() -> str:
    explicit = os.environ.get("CLAUDE_CLI", "").strip()
    if explicit:
        return explicit
    found = shutil.which("claude")
    return found or "claude"


def _strip_html(raw: str) -> str:
    raw = _SCRIPT_RE.sub(" ", raw)
    raw = _TAG_RE.sub("", raw)
    raw = html.unescape(raw)
    raw = _WS_RE.sub("\n\n", raw)
    return raw.strip()


def _web_search(query: str, max_results: int = 5) -> str:
    endpoint = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(endpoint, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"(web search failed: {exc!r})"

    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_re = re.compile(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    links = pattern.findall(body)
    snippets = snippet_re.findall(body)
    chunks: list[str] = []
    for i, (href, title) in enumerate(links[:max_results]):
        real = href
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            real = urllib.parse.unquote(m.group(1))
        snip = _strip_html(snippets[i]) if i < len(snippets) else ""
        chunks.append(f"{i + 1}. {_strip_html(title)}\n   {real}\n   {snip}")
    return "\n\n".join(chunks) if chunks else "(no web results)"


def _parse_claude_json(stdout: str) -> str:
    stdout = stdout.strip()
    if not stdout:
        return "(empty response from Claude CLI)"
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout

    if isinstance(data, str):
        return data.strip()

    for key in ("result", "text", "content", "output"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    if isinstance(data.get("message"), dict):
        msg = data["message"]
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            joined = "\n".join(p for p in parts if p).strip()
            if joined:
                return joined

    return stdout


def _subprocess_env_for_cli() -> dict[str, str]:
    """Use Claude subscription auth, not pay-per-token API billing."""
    env = os.environ.copy()
    if os.environ.get("THINK_USE_SUBSCRIPTION", "1").strip().lower() not in {
        "0", "false", "no",
    }:
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


def _call_claude_cli(system: str, user: str, model: str, *, deep: bool = False) -> str:
    claude = _claude_bin()
    if claude == "claude" and not shutil.which("claude"):
        return (
            "Error: Claude Code CLI not found. Install from https://code.claude.com "
            "then run: claude auth login"
        )

    timeout = int(os.environ.get("CLAUDE_CLI_TIMEOUT", "300"))
    cwd = os.environ.get("CLAUDE_CLI_CWD", os.path.expanduser("~"))

    cmd = [
        claude,
        "--bare",
        "-p",
        "Analyze the stdin content and respond per your system instructions. "
        "Do not use tools — text answer only.",
        "--system-prompt",
        system,
        "--output-format",
        os.environ.get("CLAUDE_CLI_OUTPUT", "json"),
        "--tools",
        "",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--max-turns",
        "1",
        "--model",
        model,
    ]

    effort = os.environ.get("THINK_EFFORT", "").strip()
    if deep and not effort:
        effort = os.environ.get("THINK_DEEP_EFFORT", "high")
    if effort:
        cmd.extend(["--effort", effort])

    try:
        proc = subprocess.run(
            cmd,
            input=user.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            env=_subprocess_env_for_cli(),
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"Error: Claude CLI timed out after {timeout}s"
    except OSError as exc:
        return f"Error: failed to run Claude CLI: {exc!r}"

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        hint = ""
        if "not logged in" in stderr.lower() or "authentication" in stderr.lower():
            hint = " Run: claude auth login"
        return (
            f"Claude CLI error (exit {proc.returncode}): "
            f"{stderr.strip() or stdout.strip()[:1500]}{hint}"
        )

    fmt = os.environ.get("CLAUDE_CLI_OUTPUT", "json").lower()
    if fmt == "json":
        return _parse_claude_json(stdout)
    return stdout.strip() or "(empty response from Claude CLI)"


def _call_anthropic(system: str, user: str, model: str, max_tokens: int = 8192) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return (
            "Error: ANTHROPIC_API_KEY is not set. Prefer THINK_PROVIDER=claude-cli "
            "(subscription, no API key). Or set ANTHROPIC_API_KEY for API billing."
        )

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"Anthropic API error {exc.code}: {detail[:2000]}"
    except Exception as exc:  # noqa: BLE001
        return f"Anthropic request failed: {exc!r}"

    parts: list[str] = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts).strip() or "(empty response from expert model)"


def _call_openai(system: str, user: str, model: str, max_tokens: int = 8192) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return (
            "Error: OPENAI_API_KEY is not set. Set THINK_PROVIDER=openai and "
            "OPENAI_API_KEY in the think-delegate MCP env."
        )
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", model)

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"OpenAI-compatible API error {exc.code}: {detail[:2000]}"
    except Exception as exc:  # noqa: BLE001
        return f"OpenAI-compatible request failed: {exc!r}"

    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return (msg.get("content") or "").strip() or "(empty response from expert model)"


def _consult_expert(
    system: str,
    user: str,
    *,
    deep: bool = False,
    max_tokens: int = 8192,
) -> str:
    model = _think_model(deep=deep)
    provider = _provider()

    if provider in {"claude-cli", "claude", "cli"}:
        return _call_claude_cli(system, user, model, deep=deep)
    if provider == "openai":
        return _call_openai(system, user, model, max_tokens=max_tokens)
    if provider in {"anthropic", "api"}:
        return _call_anthropic(system, user, model, max_tokens=max_tokens)
    return f"Error: unknown THINK_PROVIDER={provider!r}. Use claude-cli, anthropic, or openai."


_DEEP_SYSTEM = """You are the expert reasoning backend for a local coding assistant.
The local model is small and delegated this task to you because it requires deep
analysis, careful architecture, subtle debugging, or multi-step planning.

Respond with:
1. Clear conclusions and recommended approach
2. Concrete steps the local model can execute with its file/shell/git tools
3. Code snippets or pseudocode where helpful
4. Risks, edge cases, and what to verify

Be direct and actionable. The local model will implement — you think; it acts.
Do not attempt to edit files or run commands — return text only."""


_RESEARCH_SYSTEM = """You are the research backend for a local coding assistant.
The local model delegated this because it needs current or specialized knowledge
beyond its training cutoff.

Use the web search snippets provided (if any) plus your knowledge. Clearly separate:
- Facts supported by the search snippets (cite source numbers)
- Reasonable inference
- Things the local model should verify with fetch_url or official docs

End with actionable next steps the local model can take with its tools.
Do not attempt to edit files or run commands — return text only."""


def run_deep_think(task: str, context: str = "", ultra: bool = False) -> str:
    """Programmatic deep_think (used by triage_core and MCP)."""
    if not task.strip():
        return "Error: task cannot be empty."

    user_parts = [f"## Task\n{task.strip()}"]
    if context.strip():
        user_parts.append(f"## Context\n{context.strip()}")
    user_parts.append(
        "\n## Instructions\nProvide your expert analysis for the local agent to act on."
    )

    header = f"[think-delegate → {_provider()} / {_think_model(deep=ultra)}]\n\n"
    return header + _consult_expert(
        _DEEP_SYSTEM,
        "\n\n".join(user_parts),
        deep=ultra,
    )


@mcp.tool()
def deep_think(
    task: str,
    context: str = "",
    ultra: bool = False,
) -> str:
    """Delegate hard reasoning to Claude Code CLI (subscription) or configured expert.

    Call this when YOU (the local model) or the user needs ultra-level thinking:
    architecture decisions, subtle bugs, security review, complex refactors,
    algorithm design, or anything beyond your reasoning capacity.

    Args:
        task: What to analyze or decide. Be specific.
        context: Relevant code, errors, constraints, or background (optional).
        ultra: If true, use THINK_DEEP_MODEL (default: opus via Claude CLI).

    Returns the expert's analysis. YOU continue locally — read/write files, run
    tests, commit — using this answer as guidance.
    """
    return run_deep_think(task, context, ultra=ultra)


@mcp.tool()
def latest_knowledge(
    question: str,
    context: str = "",
    search_web: bool = True,
) -> str:
    """Delegate a question needing recent knowledge to Claude CLI (or configured expert).

    Call this when the task depends on information after your training cutoff,
    current library versions, recent API changes, or facts you are unsure about.

    Optionally runs a web search first and passes snippets to the expert.

    Args:
        question: What you need to know.
        context: Why you need it, what you're building (optional).
        search_web: If true (default), search the web before consulting the expert.

    Returns a synthesized answer with sources where possible. Continue locally
    with coding-tools / fetch_url to verify and implement.
    """
    if not question.strip():
        return "Error: question cannot be empty."

    research = ""
    if search_web:
        research = _web_search(question.strip(), max_results=5)

    user_parts = [f"## Question\n{question.strip()}"]
    if context.strip():
        user_parts.append(f"## Context\n{context.strip()}")
    if research:
        user_parts.append(f"## Web search results\n{research}")
    user_parts.append(
        "\n## Instructions\nSynthesize an answer the local coding agent can use."
    )

    header = f"[think-delegate research → {_provider()} / {_think_model(deep=False)}]\n\n"
    return header + _consult_expert(
        _RESEARCH_SYSTEM,
        "\n\n".join(user_parts),
        deep=False,
    )


@mcp.tool()
def delegate_status() -> str:
    """Check whether think-delegate is configured and which expert backend is active.

    Call this if a delegation tool failed or the user asks whether cloud escalation
    is available.
    """
    provider = _provider()
    lines = [
        "think-delegate MCP status",
        f"  provider: {provider}",
        f"  standard model: {_think_model(deep=False)}",
        f"  ultra model: {_think_model(deep=True)}",
    ]

    if provider in {"claude-cli", "claude", "cli"}:
        claude = _claude_bin()
        if claude != "claude":
            ok = Path(claude).is_file() or shutil.which(claude) is not None
        else:
            ok = shutil.which("claude") is not None
        lines.extend([
            f"  claude CLI: {claude}",
            f"  cli found: {'yes' if ok else 'no'}",
            f"  subscription mode: {os.environ.get('THINK_USE_SUBSCRIPTION', '1')}",
            f"  timeout: {os.environ.get('CLAUDE_CLI_TIMEOUT', '300')}s",
            "",
            "Uses Claude Code subscription (claude auth login), NOT Anthropic API billing.",
            "Ensure: claude auth login  (do NOT set ANTHROPIC_API_KEY for subscription)",
        ])
    elif provider == "openai":
        ok = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        lines.append(f"  OPENAI_API_KEY: {'set' if ok else 'MISSING'}")
        lines.append(f"  OPENAI_BASE_URL: {os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')}")
    else:
        ok = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
        lines.append(f"  ANTHROPIC_API_KEY: {'set' if ok else 'MISSING'}")

    lines.extend([
        "",
        "Tools: deep_think (hard reasoning), latest_knowledge (recent facts + web)",
        "Usage: local SLM calls these when user says 'think deeper' or task is too hard.",
    ])
    if not ok:
        if provider in {"claude-cli", "claude", "cli"}:
            lines.append("\n⚠ Install Claude Code CLI and run: claude auth login")
        else:
            lines.append("\n⚠ Add API key to think-delegate env in ~/.lmstudio/mcp.json")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")

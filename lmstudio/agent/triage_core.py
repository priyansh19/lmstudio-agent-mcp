"""
triage_core.py — Phase 1: score user prompts and auto-route to Claude when needed.

Architecture (Architecture_Daigram.excalidraw):
  User Prompt → Local LLM Scoring Agent → score >= threshold → Local LLM Agent
                                      → score < threshold  → Claude via think-delegate
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "triage.json"

SCORER_SYSTEM = """You are a triaging scorer for a local coding assistant stack.
A SMALL local model (Gemma-class) handles easy tasks with MCP tools (files, shell, git).
Claude (expert) handles hard reasoning, architecture, subtle bugs, and recent knowledge.

Rate how confidently the LOCAL model alone can handle the user request on scale 0-10:
  10 = trivial (list files, read README, simple grep)
  8-9 = straightforward coding with tools
  5-7 = moderate; local might struggle but could try
  3-4 = hard; needs expert analysis first
  0-2 = must delegate (architecture, security audit, complex debug, current events)

Respond with ONLY valid JSON (no markdown):
{"score": <number>, "reason": "<one sentence>", "needs_claude": <true|false>}

Set needs_claude true when score would be below 7."""


@dataclass
class TriageResult:
    score: float
    reason: str
    route: str  # "local" | "claude"
    user_prompt: str
    expert_response: str | None = None
    threshold: float = 7.0

    def summary(self) -> str:
        lines = [
            f"Triage score: {self.score:.1f} / 10 (threshold {self.threshold})",
            f"Route: {self.route}",
            f"Reason: {self.reason}",
        ]
        if self.expert_response:
            lines.append("")
            lines.append(self.expert_response)
        return "\n".join(lines)


def load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "enabled": True,
        "threshold": 7.0,
        "ultra_threshold": 4.0,
        "lmstudio_url": "http://127.0.0.1:1234",
        "bridge_triage": True,
    }
    if CONFIG_PATH.is_file():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for k, v in raw.items():
            if not k.startswith("_"):
                cfg[k] = v
    if os.environ.get("TRIAGE_ENABLED", "").strip().lower() in {"0", "false", "no"}:
        cfg["enabled"] = False
    if os.environ.get("TRIAGE_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
        cfg["enabled"] = True
    if os.environ.get("TRIAGE_THRESHOLD"):
        cfg["threshold"] = float(os.environ["TRIAGE_THRESHOLD"])
    if os.environ.get("LMSTUDIO_URL"):
        cfg["lmstudio_url"] = os.environ["LMSTUDIO_URL"].rstrip("/")
    return cfg


def _parse_score_json(text: str) -> tuple[float, str, bool | None]:
    text = text.strip()
    if not text:
        return 2.0, "scorer returned empty; delegating to expert", True
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        num = re.search(r'"?score"?\s*[:=]\s*(\d+(?:\.\d+)?)', text, re.I)
        if num:
            score = max(0.0, min(10.0, float(num.group(1))))
            return score, "parsed score from non-JSON scorer output", None
        return 2.0, "could not parse scorer output; delegating to expert", True
    score = float(data.get("score", 5.0))
    score = max(0.0, min(10.0, score))
    reason = str(data.get("reason", "")).strip() or "no reason given"
    needs = data.get("needs_claude")
    if isinstance(needs, bool):
        return score, reason, needs
    return score, reason, None


def _chat_completion(
    lm_base: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 512,
    temperature: float = 0.1,
) -> str:
    url = f"{lm_base.rstrip('/')}/v1/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return (msg.get("content") or "").strip()


def resolve_model(lm_base: str) -> str:
    lm_base = lm_base.rstrip("/")
    try:
        with urllib.request.urlopen(f"{lm_base}/api/v1/models", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        loaded = [
            m["key"] for m in data.get("models", [])
            if m.get("type") == "llm" and m.get("loaded_instances")
        ]
        if loaded:
            return loaded[0]
    except Exception:  # noqa: BLE001
        pass
    with urllib.request.urlopen(f"{lm_base}/v1/models", timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for item in data.get("data", []):
        mid = item.get("id", "")
        if mid and "embed" not in mid.lower():
            return mid
    raise RuntimeError(f"No LLM loaded at {lm_base}")


def score_prompt(
    user_prompt: str,
    context: str = "",
    *,
    lm_base: str | None = None,
    model: str | None = None,
) -> tuple[float, str]:
    """Return (score 0-10, reason). Uses local LM Studio model."""
    cfg = load_config()
    lm = (lm_base or cfg["lmstudio_url"]).rstrip("/")
    resolved = model or resolve_model(lm)
    user_block = f"User request:\n{user_prompt.strip()}"
    if context.strip():
        user_block += f"\n\nAdditional context:\n{context.strip()}"
    try:
        content = _chat_completion(
            lm,
            resolved,
            [
                {"role": "system", "content": SCORER_SYSTEM},
                {"role": "user", "content": user_block},
            ],
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 2.0, f"scoring unavailable ({exc!r}); delegating to expert"
    score, reason, needs_claude = _parse_score_json(content)
    if needs_claude is True and score >= threshold_from_cfg():
        score = min(score, threshold_from_cfg() - 0.1)
        reason = f"{reason} (needs_claude=true)"
    return score, reason


def threshold_from_cfg() -> float:
    return float(load_config().get("threshold", 7.0))


def triage_prompt(
    user_prompt: str,
    context: str = "",
    *,
    auto_delegate: bool = True,
    lm_base: str | None = None,
    model: str | None = None,
) -> TriageResult:
    """Score prompt and optionally delegate to Claude when below threshold."""
    cfg = load_config()
    threshold = float(cfg.get("threshold", 7.0))
    ultra_below = float(cfg.get("ultra_threshold", 4.0))

    if not user_prompt.strip():
        return TriageResult(
            score=0.0,
            reason="empty prompt",
            route="local",
            user_prompt=user_prompt,
            threshold=threshold,
        )

    if not cfg.get("enabled", True):
        return TriageResult(
            score=10.0,
            reason="triage disabled",
            route="local",
            user_prompt=user_prompt,
            threshold=threshold,
        )

    score, reason = score_prompt(user_prompt, context, lm_base=lm_base, model=model)
    route = "local" if score >= threshold else "claude"

    result = TriageResult(
        score=score,
        reason=reason,
        route=route,
        user_prompt=user_prompt,
        threshold=threshold,
    )

    if route == "claude" and auto_delegate:
        from servers.think_delegate import run_deep_think  # noqa: PLC0415

        ultra = score < ultra_below
        expert = run_deep_think(
            task=user_prompt.strip(),
            context=context.strip(),
            ultra=ultra,
        )
        result.expert_response = expert

    return result


def extract_last_user_message(messages: list[dict[str, Any]]) -> str:
    """Pull the latest user text from an OpenAI-style messages array."""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") in ("text", "input_text"):
                    parts.append(str(part.get("text", "")))
            joined = "\n".join(p for p in parts if p).strip()
            if joined:
                return joined
    return ""

"""
summarizer_core.py — Phase 3: distill episodic chat batches into semantic facts.

Architecture (Architecture_Daigram.excalidraw):
  Save responses → when N episodic chats accumulate → Summarizer Agent → vector DB facts
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from agent.triage_core import _chat_completion, load_config as load_triage_config, resolve_model
from agent.vector_memory import VectorMemoryStore, load_config, store_semantic

SUMMARIZER_SYSTEM = """You are a memory consolidator for a local coding assistant.
You receive recent chat episodes (user questions + assistant answers).
Extract durable facts worth remembering long-term: user preferences, project decisions,
names/paths, recurring tasks, technical choices, and stable context.

Ignore: greetings, one-off trivial commands, duplicate info, speculative guesses.

Respond with ONLY valid JSON (no markdown):
{"facts": ["fact one", "fact two", ...]}

Rules:
- Each fact is one concise standalone sentence (under 200 chars).
- 0-8 facts per batch; empty array if nothing durable.
- Do not invent facts not supported by the episodes."""


@dataclass
class SummarizeResult:
    ran: bool
    reason: str
    facts_stored: int = 0
    episodes_processed: int = 0
    facts: list[str] | None = None

    def summary(self) -> str:
        lines = [
            f"Summarizer: {'ran' if self.ran else 'skipped'} — {self.reason}",
        ]
        if self.ran:
            lines.append(f"Episodes processed: {self.episodes_processed}")
            lines.append(f"Facts stored: {self.facts_stored}")
            if self.facts:
                lines.append("Facts:")
                lines.extend(f"  - {f}" for f in self.facts)
        return "\n".join(lines)


def _parse_facts_json(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    raw = data.get("facts", [])
    if not isinstance(raw, list):
        return []
    facts: list[str] = []
    for item in raw:
        s = str(item).strip()
        if s and s not in facts:
            facts.append(s[:500])
    return facts


def _lmstudio_url() -> str:
    cfg = load_triage_config()
    return str(cfg.get("lmstudio_url", "http://127.0.0.1:1234")).rstrip("/")


def distill_episodes(episodes: list[str]) -> list[str]:
    """Use local LLM to extract semantic facts from episodic chat text."""
    if not episodes:
        return []
    lm = _lmstudio_url()
    model = resolve_model(lm)
    block = "\n\n---\n\n".join(f"Episode {i + 1}:\n{e}" for i, e in enumerate(episodes))
    content = _chat_completion(
        lm,
        model,
        [
            {"role": "system", "content": SUMMARIZER_SYSTEM},
            {"role": "user", "content": f"Consolidate these chat episodes:\n\n{block}"},
        ],
        max_tokens=1024,
        temperature=0.2,
    )
    return _parse_facts_json(content)


def run_summarization(*, batch_size: int | None = None, force: bool = False) -> SummarizeResult:
    """Process up to batch_size unsummarized episodic memories into semantic facts."""
    cfg = load_config()
    if not cfg.get("enabled", True):
        return SummarizeResult(ran=False, reason="RAG disabled")
    if not cfg.get("summarizer_enabled", True):
        return SummarizeResult(ran=False, reason="summarizer disabled")

    n = batch_size or int(cfg.get("summarize_every_n", 10))
    store = VectorMemoryStore()
    pending = store.count_unsummarized("episodic")

    if not force and pending < n:
        return SummarizeResult(
            ran=False,
            reason=f"{pending}/{n} unsummarized episodes (waiting for N)",
        )

    take = n if not force else min(pending, n)
    if take <= 0:
        return SummarizeResult(ran=False, reason="no unsummarized episodes")

    batch = store.list_unsummarized("episodic", limit=take)
    if not batch:
        return SummarizeResult(ran=False, reason="no episodes to summarize")

    facts = distill_episodes([b.content for b in batch])
    batch_id = str(uuid.uuid4())
    stored: list[str] = []

    for fact in facts:
        mid = store_semantic(
            fact,
            source="summarizer",
            batch_id=batch_id,
            distilled_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        stored.append(mid)

    store.mark_summarized([b.id for b in batch], batch_id=batch_id)

    return SummarizeResult(
        ran=True,
        reason=f"consolidated {len(batch)} episodes",
        facts_stored=len(stored),
        episodes_processed=len(batch),
        facts=facts,
    )


def maybe_run_summarizer() -> SummarizeResult | None:
    """Run summarizer if unsummarized episodic count reached N."""
    cfg = load_config()
    if not cfg.get("enabled", True) or not cfg.get("summarizer_enabled", True):
        return None
    n = int(cfg.get("summarize_every_n", 10))
    store = VectorMemoryStore()
    if store.count_unsummarized("episodic") < n:
        return None
    return run_summarization(batch_size=n)

"""
rag_context.py — Phase 2 RAG context injection for the local agent.

Combines semantic + episodic vector retrieval with optional graph memory recall.
"""

from __future__ import annotations

import time
from typing import Any

from agent.memory_context import recall as graph_recall
from agent.vector_memory import load_config, rag_search, store_episode


def _format_hits(label: str, hits: list[Any]) -> list[str]:
    if not hits:
        return []
    lines = [f"{label} (RAG top-k):"]
    for hit in hits:
        meta = hit.metadata or {}
        extra = ""
        if meta:
            tags = ", ".join(f"{k}={v}" for k, v in meta.items() if v)
            if tags:
                extra = f" [{tags}]"
        lines.append(f"- ({hit.score:.2f}) {hit.content}{extra}")
    return lines


def build_rag_context(query: str, *, include_graph: bool = True) -> str:
    """Return a context block from vector RAG (+ optional graph memory)."""
    cfg = load_config()
    if not cfg.get("enabled", True):
        return graph_recall(query) if include_graph else ""

    semantic, episodic = rag_search(query)
    lines: list[str] = []

    graph_block = graph_recall(query) if include_graph else ""
    if graph_block:
        lines.append(graph_block)

    lines.extend(_format_hits("Semantic memory", semantic))
    lines.extend(_format_hits("Episodic memory", episodic))

    return "\n".join(lines).strip()


def augment_user_message(query: str, *, include_graph: bool = True) -> str:
    """Prepend RAG + graph memory to the user message."""
    block = build_rag_context(query, include_graph=include_graph)
    if not block:
        return query
    return f"{block}\n\n---\n\nUser request: {query}"


def save_turn(user_prompt: str, assistant_response: str, *, workspace: str = "") -> str | None:
    """Persist a completed chat turn into episodic memory."""
    cfg = load_config()
    if not cfg.get("enabled", True) or not cfg.get("auto_save_episodes", True):
        return None
    user_prompt = user_prompt.strip()
    assistant_response = assistant_response.strip()
    if not user_prompt or not assistant_response:
        return None
    content = (
        f"User: {user_prompt}\n"
        f"Assistant: {assistant_response[:2000]}"
    )
    return store_episode(
        content,
        workspace=workspace,
        saved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def save_turn_and_maybe_summarize(
    user_prompt: str,
    assistant_response: str,
    *,
    workspace: str = "",
) -> tuple[str | None, str | None]:
    """Save episodic turn; run Phase 3 summarizer when N episodes accumulate."""
    episode_id = save_turn(user_prompt, assistant_response, workspace=workspace)
    summary_msg: str | None = None
    if episode_id:
        from agent.summarizer_core import maybe_run_summarizer  # noqa: PLC0415

        result = maybe_run_summarizer()
        if result and result.ran:
            summary_msg = result.summary()
    return episode_id, summary_msg

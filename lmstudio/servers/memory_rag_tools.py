"""
memory_rag_tools.py — MCP server for Phase 2 semantic + episodic vector memory.

Uses LM Studio embedding models and SQLite-backed vector search (RAG top-k).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP

from agent.rag_context import build_rag_context
from agent.summarizer_core import run_summarization
from agent.vector_memory import (
    VectorMemoryStore,
    load_config,
    store_episode,
    store_semantic,
)

mcp = FastMCP("memory-rag")


@mcp.tool()
def remember_fact(fact: str, source: str = "") -> str:
    """Store a durable semantic fact (user profile, preferences, project knowledge)."""
    if not fact.strip():
        return "Error: fact cannot be empty."
    meta = {"source": source} if source.strip() else {}
    mid = store_semantic(fact.strip(), **meta)
    return f"Stored semantic memory `{mid}`: {fact.strip()[:200]}"


@mcp.tool()
def remember_episode(summary: str, session: str = "") -> str:
    """Store an episodic memory (dated event or chat summary)."""
    if not summary.strip():
        return "Error: summary cannot be empty."
    meta = {"session": session} if session.strip() else {}
    mid = store_episode(summary.strip(), **meta)
    return f"Stored episodic memory `{mid}`: {summary.strip()[:200]}"


@mcp.tool()
def search_semantic(query: str, top_k: int = 5) -> str:
    """RAG search over semantic (fact) memories."""
    cfg = load_config()
    store = VectorMemoryStore()
    hits = store.search(
        "semantic",
        query,
        top_k=top_k,
        min_score=float(cfg.get("min_score", 0.25)),
    )
    if not hits:
        return "No semantic memories matched."
    lines = [f"Semantic RAG ({len(hits)} hits):"]
    for h in hits:
        lines.append(f"- [{h.score:.2f}] {h.content}")
    return "\n".join(lines)


@mcp.tool()
def search_episodic(query: str, top_k: int = 5) -> str:
    """RAG search over episodic (chat/event) memories."""
    cfg = load_config()
    store = VectorMemoryStore()
    hits = store.search(
        "episodic",
        query,
        top_k=top_k,
        min_score=float(cfg.get("min_score", 0.25)),
    )
    if not hits:
        return "No episodic memories matched."
    lines = [f"Episodic RAG ({len(hits)} hits):"]
    for h in hits:
        lines.append(f"- [{h.score:.2f}] {h.content}")
    return "\n".join(lines)


@mcp.tool()
def rag_preview(query: str) -> str:
    """Preview the RAG context block injected into the local agent for this query."""
    block = build_rag_context(query)
    return block or "(no RAG context — empty stores or RAG disabled)"


@mcp.tool()
def summarize_now(batch_size: int = 10) -> str:
    """Force-run Phase 3 summarizer on unsummarized episodic memories."""
    result = run_summarization(batch_size=max(1, batch_size), force=True)
    return result.summary()


@mcp.tool()
def memory_rag_status() -> str:
    """Show vector memory + summarizer configuration and store counts."""
    cfg = load_config()
    store = VectorMemoryStore()
    pending = store.count_unsummarized("episodic")
    n = int(cfg.get("summarize_every_n", 10))
    return "\n".join([
        "memory-rag MCP — Phase 2/3 vector RAG + summarizer",
        f"  enabled: {cfg.get('enabled', True)}",
        f"  semantic_top_k: {cfg.get('semantic_top_k', 5)}",
        f"  episodic_top_k: {cfg.get('episodic_top_k', 5)}",
        f"  min_score: {cfg.get('min_score', 0.25)}",
        f"  auto_save_episodes: {cfg.get('auto_save_episodes', True)}",
        f"  summarizer_enabled: {cfg.get('summarizer_enabled', True)}",
        f"  summarize_every_n: {n} (pending: {pending})",
        f"  db: {store.path}",
        f"  semantic count: {store.count('semantic')}",
        f"  episodic count: {store.count('episodic')}",
        "",
        "Tools: remember_fact, remember_episode, search_semantic, search_episodic,",
        "       rag_preview, summarize_now",
    ])


if __name__ == "__main__":
    mcp.run(transport="stdio")

"""
memory_context.py — Automatic memory recall for local agents.

Reads the knowledge-graph memory file (.agent-memory.json) and returns facts
relevant to the user's query. Injected into every prompt so the model does NOT
need to remember to call search_nodes (local models often skip that).

The memory MCP server is still used for WRITES (create_entities, add_observations).
This module handles READS automatically.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT_MEMORY = Path(__file__).resolve().parent.parent / ".agent-memory.json"

_STOP = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "and", "or", "but", "if", "then", "else", "when", "up", "out", "about",
    "what", "which", "who", "whom", "this", "that", "these", "those", "i",
    "you", "he", "she", "it", "we", "they", "me", "my", "your", "our", "their",
    "how", "why", "where", "there", "here", "all", "any", "some", "no", "not",
})


def _memory_path() -> Path:
    return Path(os.environ.get("MEMORY_FILE_PATH", str(DEFAULT_MEMORY)))


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9_./-]+", text.lower())
    return {w for w in words if len(w) > 1 and w not in _STOP}


def load_graph(path: Path | None = None) -> tuple[list[dict], list[dict]]:
    path = path or _memory_path()
    entities: list[dict] = []
    relations: list[dict] = []
    if not path.exists():
        return entities, relations
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "entity":
            entities.append(obj)
        elif obj.get("type") == "relation":
            relations.append(obj)
    return entities, relations


def recall(query: str, max_observations: int = 12) -> str:
    """Return a compact block of memory facts relevant to `query`."""
    entities, relations = load_graph()
    if not entities:
        return ""

    q = _tokenize(query)
    if not q:
        q = _tokenize("user project preferences")

    scored: list[tuple[float, str, str, str]] = []
    for ent in entities:
        name = ent.get("name", "")
        etype = ent.get("entityType", "")
        name_toks = _tokenize(name)
        for obs in ent.get("observations", []):
            obs_toks = _tokenize(obs)
            overlap = len(q & (name_toks | obs_toks))
            if overlap == 0 and not q & name_toks:
                continue
            score = overlap + 0.5 * len(q & name_toks)
            scored.append((score, name, etype, obs))

    scored.sort(key=lambda x: -x[0])
    if not scored:
        # Fall back: return top entity summaries
        lines = ["Known context (general):"]
        for ent in entities[:3]:
            obs = ent.get("observations", [])
            if obs:
                lines.append(f"- {ent['name']} ({ent.get('entityType','')}): {obs[0]}")
        return "\n".join(lines)

    lines = ["Relevant memory (auto-recalled):"]
    seen: set[str] = set()
    for _, name, etype, obs in scored[:max_observations]:
        key = f"{name}:{obs}"
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- [{name} / {etype}] {obs}")

    # Add relations touching recalled entities
    recalled_names = {s[1] for s in scored[:max_observations]}
    rel_lines = []
    for rel in relations:
        if rel.get("from") in recalled_names or rel.get("to") in recalled_names:
            rel_lines.append(
                f"- {rel['from']} --{rel.get('relationType','')}--> {rel['to']}"
            )
    if rel_lines:
        lines.append("Relations:")
        lines.extend(rel_lines[:6])

    return "\n".join(lines)


def augment_user_message(query: str) -> str:
    """Prepend recalled memory to the user message."""
    block = recall(query)
    if not block:
        return query
    return f"{block}\n\n---\n\nUser request: {query}"

"""
vector_memory.py — Phase 2 semantic + episodic vector stores (SQLite).

Architecture (Architecture_Daigram.excalidraw):
  - Semantic Memory: durable facts, user profile
  - Episodic Memory: dated events, past chat history
  - RAG top-k retrieval injected into agent context
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent.embeddings import embed_texts

MemoryKind = Literal["semantic", "episodic"]

DEFAULT_DB = Path(__file__).resolve().parent.parent / ".vector-memory.db"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "memory.json"


def _db_path() -> Path:
    return Path(os.environ.get("VECTOR_MEMORY_DB", str(DEFAULT_DB)))


def load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "enabled": True,
        "semantic_top_k": 5,
        "episodic_top_k": 5,
        "min_score": 0.25,
        "auto_save_episodes": True,
        "summarizer_enabled": True,
        "summarize_every_n": 10,
    }
    if CONFIG_PATH.is_file():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for k, v in raw.items():
            if not k.startswith("_"):
                cfg[k] = v
    if os.environ.get("RAG_ENABLED", "").strip().lower() in {"0", "false", "no"}:
        cfg["enabled"] = False
    if os.environ.get("SUMMARIZER_ENABLED", "").strip().lower() in {"0", "false", "no"}:
        cfg["summarizer_enabled"] = False
    return cfg


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class MemoryHit:
    id: str
    kind: MemoryKind
    content: str
    score: float
    metadata: dict[str, Any]
    created_at: float


class VectorMemoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    embedding BLOB NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)")
            conn.commit()

    def add(
        self,
        kind: MemoryKind,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> str:
        content = content.strip()
        if not content:
            raise ValueError("content cannot be empty")
        vec = embed_texts([content])[0]
        mid = memory_id or str(uuid.uuid4())
        meta = json.dumps(metadata or {})
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memories (id, kind, content, metadata, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (mid, kind, content, meta, _pack(vec), now),
            )
            conn.commit()
        return mid

    def search(
        self,
        kind: MemoryKind,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[MemoryHit]:
        query = query.strip()
        if not query:
            return []
        qvec = embed_texts([query])[0]
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, kind, content, metadata, embedding, created_at FROM memories WHERE kind = ?",
                (kind,),
            ).fetchall()

        hits: list[MemoryHit] = []
        for row in rows:
            score = _cosine(qvec, _unpack(row["embedding"]))
            if score < min_score:
                continue
            hits.append(
                MemoryHit(
                    id=row["id"],
                    kind=row["kind"],
                    content=row["content"],
                    score=score,
                    metadata=json.loads(row["metadata"] or "{}"),
                    created_at=row["created_at"],
                )
            )
        hits.sort(key=lambda h: -h.score)
        return hits[:top_k]

    def _is_summarized(self, metadata: dict[str, Any]) -> bool:
        return bool(metadata.get("summarized"))

    def count_unsummarized(self, kind: MemoryKind) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT metadata FROM memories WHERE kind = ?", (kind,)
            ).fetchall()
        count = 0
        for row in rows:
            meta = json.loads(row["metadata"] or "{}")
            if not self._is_summarized(meta):
                count += 1
        return count

    def list_unsummarized(self, kind: MemoryKind, limit: int = 10) -> list[MemoryHit]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, kind, content, metadata, created_at
                FROM memories WHERE kind = ?
                ORDER BY created_at ASC
                """,
                (kind,),
            ).fetchall()
        hits: list[MemoryHit] = []
        for row in rows:
            meta = json.loads(row["metadata"] or "{}")
            if self._is_summarized(meta):
                continue
            hits.append(
                MemoryHit(
                    id=row["id"],
                    kind=row["kind"],
                    content=row["content"],
                    score=0.0,
                    metadata=meta,
                    created_at=row["created_at"],
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def mark_summarized(self, memory_ids: list[str], **metadata: Any) -> None:
        if not memory_ids:
            return
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._connect() as conn:
            for mid in memory_ids:
                row = conn.execute(
                    "SELECT metadata FROM memories WHERE id = ?", (mid,)
                ).fetchone()
                if not row:
                    continue
                meta = json.loads(row["metadata"] or "{}")
                meta["summarized"] = True
                meta["summarized_at"] = stamp
                for k, v in metadata.items():
                    meta[k] = v
                conn.execute(
                    "UPDATE memories SET metadata = ? WHERE id = ?",
                    (json.dumps(meta), mid),
                )
            conn.commit()

    def count(self, kind: MemoryKind | None = None) -> int:
        with self._connect() as conn:
            if kind:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM memories WHERE kind = ?", (kind,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"])

    def list_recent(self, kind: MemoryKind, limit: int = 10) -> list[MemoryHit]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, kind, content, metadata, created_at
                FROM memories WHERE kind = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (kind, limit),
            ).fetchall()
        return [
            MemoryHit(
                id=r["id"],
                kind=r["kind"],
                content=r["content"],
                score=0.0,
                metadata=json.loads(r["metadata"] or "{}"),
                created_at=r["created_at"],
            )
            for r in rows
        ]


def store_semantic(content: str, **metadata: Any) -> str:
    return VectorMemoryStore().add("semantic", content, metadata=metadata)


def store_episode(content: str, **metadata: Any) -> str:
    return VectorMemoryStore().add("episodic", content, metadata=metadata)


def rag_search(query: str) -> tuple[list[MemoryHit], list[MemoryHit]]:
    """Top-k semantic + episodic hits for a user query."""
    cfg = load_config()
    if not cfg.get("enabled", True):
        return [], []
    store = VectorMemoryStore()
    min_score = float(cfg.get("min_score", 0.25))
    semantic = store.search(
        "semantic",
        query,
        top_k=int(cfg.get("semantic_top_k", 5)),
        min_score=min_score,
    )
    episodic = store.search(
        "episodic",
        query,
        top_k=int(cfg.get("episodic_top_k", 5)),
        min_score=min_score,
    )
    return semantic, episodic

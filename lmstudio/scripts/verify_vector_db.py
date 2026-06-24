#!/usr/bin/env python3
"""
verify_vector_db.py — Proof report: embeddings stored in .vector-memory.db

Simulates agent chat turns (same path as local_agent) then dumps DB evidence.
"""

from __future__ import annotations

import json
import struct
import sqlite3
import sys
import time
from pathlib import Path

LMSTUDIO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LMSTUDIO))

DB = LMSTUDIO / ".vector-memory.db"
REPORT = LMSTUDIO / ".vector-db-report.json"


def _embedding_dim(blob: bytes) -> int:
    return len(blob) // 4 if blob else 0


def _embedding_preview(blob: bytes, n: int = 5) -> list[float]:
    dim = _embedding_dim(blob)
    if dim == 0:
        return []
    vals = struct.unpack(f"{min(n, dim)}f", blob[: min(n, dim) * 4])
    return [round(v, 6) for v in vals]


def simulate_chat_turns() -> list[dict]:
    from agent.rag_context import save_turn_and_maybe_summarize

    turns = [
        (
            "What is the workspace root for this project?",
            "The workspace root is ~/Desktop/lmstudio-agent-mcp. Code lives under lmstudio/.",
        ),
        (
            "How does Phase 2 vector memory work?",
            "Phase 2 uses LM Studio embeddings stored in SQLite (.vector-memory.db) with semantic and episodic kinds.",
        ),
        (
            "Remember that I prefer uv over pip for Python deps.",
            "Noted — I'll use uv run for all Python commands in this repo.",
        ),
    ]
    results = []
    for user, assistant in turns:
        eid, summ = save_turn_and_maybe_summarize(user, assistant, workspace=str(LMSTUDIO.parent))
        results.append({
            "user": user[:80],
            "episode_id": eid,
            "summarizer": summ.splitlines()[0] if summ else None,
        })
        time.sleep(0.3)
    return results


def dump_db() -> dict:
    if not DB.is_file():
        return {"error": f"DB not found: {DB}"}

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, kind, content, metadata, length(embedding) AS emb_bytes, created_at FROM memories ORDER BY created_at"
    ).fetchall()
    conn.close()

    items = []
    for r in rows:
        conn2 = sqlite3.connect(DB)
        blob = conn2.execute("SELECT embedding FROM memories WHERE id = ?", (r["id"],)).fetchone()[0]
        conn2.close()
        meta = json.loads(r["metadata"] or "{}")
        dim = _embedding_dim(blob)
        items.append({
            "id": r["id"],
            "kind": r["kind"],
            "content_preview": (r["content"] or "")[:120],
            "embedding_bytes": r["emb_bytes"],
            "embedding_dim": dim,
            "embedding_preview": _embedding_preview(blob, 6),
            "metadata": meta,
            "created_at": r["created_at"],
        })

    semantic = sum(1 for i in items if i["kind"] == "semantic")
    episodic = sum(1 for i in items if i["kind"] == "episodic")
    with_emb = sum(1 for i in items if i["embedding_dim"] > 0)

    return {
        "db_path": str(DB),
        "db_size_bytes": DB.stat().st_size,
        "total_rows": len(items),
        "semantic_count": semantic,
        "episodic_count": episodic,
        "rows_with_embeddings": with_emb,
        "embedding_model_env": "text-embedding-nomic-embed-text-v1.5 (via LM Studio)",
        "rows": items,
    }


def main() -> None:
    print("=== Vector DB verification ===\n")
    print("1) Simulating chat turns (save_turn_and_maybe_summarize)...")
    try:
        turns = simulate_chat_turns()
        for t in turns:
            print(f"   episode_id={t['episode_id']}  user={t['user'][:50]}...")
            if t.get("summarizer"):
                print(f"   -> {t['summarizer']}")
    except Exception as exc:  # noqa: BLE001
        print(f"   ERROR during simulation: {exc!r}")
        sys.exit(1)

    print("\n2) Reading SQLite store...")
    report = dump_db()
    report["simulated_turns"] = turns
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"   DB: {report['db_path']}")
    print(f"   Size: {report['db_size_bytes']:,} bytes")
    print(f"   Rows: {report['total_rows']} (semantic={report['semantic_count']}, episodic={report['episodic_count']})")
    print(f"   Rows with non-empty embeddings: {report['rows_with_embeddings']}/{report['total_rows']}")

    print("\n3) Sample rows (proof of embeddings):")
    for row in report["rows"][-5:]:
        print(f"   [{row['kind']}] dim={row['embedding_dim']} bytes={row['embedding_bytes']}")
        print(f"      content: {row['content_preview'][:90]}...")
        print(f"      vec[:6]: {row['embedding_preview']}")

    if report["rows_with_embeddings"] == 0:
        print("\nFAIL: No embeddings found in database.")
        sys.exit(1)

    print(f"\nReport written: {REPORT}")
    print("PASS: Embeddings are stored in the vector database.")


if __name__ == "__main__":
    main()

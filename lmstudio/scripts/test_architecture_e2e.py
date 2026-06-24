#!/usr/bin/env python3
"""
test_architecture_e2e.py — End-to-end test of every architecture link.

Usage:
    cd lmstudio && uv run python scripts/test_architecture_e2e.py
    cd lmstudio && uv run python scripts/test_architecture_e2e.py --chat-turns 3
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

LMSTUDIO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LMSTUDIO))
REPORT_PATH = LMSTUDIO / ".architecture-e2e-report.json"


@dataclass
class LinkResult:
    name: str
    status: str  # PASS | FAIL | WARN | SKIP
    detail: str


@dataclass
class E2EReport:
    links: list[LinkResult] = field(default_factory=list)
    db_before: dict = field(default_factory=dict)
    db_after: dict = field(default_factory=dict)
    chat_turns: list[dict] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str) -> None:
        self.links.append(LinkResult(name, status, detail))
        icon = {"PASS": "✓", "FAIL": "✗", "WARN": "!", "SKIP": "-"}.get(status, "?")
        print(f"  [{icon} {status}] {name}")
        print(f"         {detail}")


def _lm_ok() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=5) as r:
            data = json.loads(r.read())
        ids = [m["id"] for m in data.get("data", [])]
        has_llm = any("embed" not in i.lower() for i in ids)
        has_emb = any("embed" in i.lower() for i in ids)
        if not has_llm:
            return False, f"no LLM in API: {ids}"
        if not has_emb:
            return False, f"no embedding model: {ids}"
        return True, f"LLM + embedding online ({len(ids)} models)"
    except Exception as exc:  # noqa: BLE001
        return False, repr(exc)


def _db_snapshot() -> dict:
    from agent.vector_memory import VectorMemoryStore

    store = VectorMemoryStore()
    return {
        "path": str(store.path),
        "semantic": store.count("semantic"),
        "episodic": store.count("episodic"),
        "unsummarized": store.count_unsummarized("episodic"),
        "size_bytes": store.path.stat().st_size if store.path.is_file() else 0,
    }


def _sample_rows(kind: str, limit: int = 3) -> list[dict]:
    from agent.vector_memory import VectorMemoryStore

    store = VectorMemoryStore()
    import sqlite3

    conn = sqlite3.connect(store.path)
    rows = conn.execute(
        """
        SELECT id, kind, substr(content,1,100) AS preview, length(embedding) AS emb
        FROM memories WHERE kind = ? ORDER BY created_at DESC LIMIT ?
        """,
        (kind, limit),
    ).fetchall()
    conn.close()
    return [{"id": r[0], "preview": r[2], "emb_bytes": r[3]} for r in rows]


def _chat_local(user: str) -> str:
    from agent.triage_core import _chat_completion, resolve_model

    model = resolve_model("http://127.0.0.1:1234")
    return _chat_completion(
        "http://127.0.0.1:1234",
        model,
        [
            {"role": "system", "content": "You are a helpful local assistant. Be concise."},
            {"role": "user", "content": user},
        ],
        max_tokens=256,
        temperature=0.3,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat-turns", type=int, default=3, help="Live chat turns with Gemma")
    ap.add_argument("--force-summarize", action="store_true", help="Run summarizer after chat")
    args = ap.parse_args()

    report = E2EReport()
    print("=" * 60)
    print("ARCHITECTURE E2E TEST")
    print("=" * 60)

    # --- Infra ---
    ok, msg = _lm_ok()
    report.add("LM Studio server + models", "PASS" if ok else "FAIL", msg)
    if not ok:
        _write_report(report)
        sys.exit(1)

    report.db_before = _db_snapshot()
    print(f"\nDB before: episodic={report.db_before['episodic']} semantic={report.db_before['semantic']}")

    # --- Phase 4: Procedural memory ---
    try:
        from agent.procedural_memory import discover_skill_files, load_procedural_context

        files = discover_skill_files(str(LMSTUDIO.parent))
        block = load_procedural_context(str(LMSTUDIO.parent))
        report.add(
            "Phase 4 — Skill.md → system prompt",
            "PASS" if files and "Procedural memory" in block else "FAIL",
            f"{len(files)} skill file(s), {len(block)} chars in block",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("Phase 4 — Skill.md → system prompt", "FAIL", repr(exc))

    # --- Phase 1: Scoring ---
    try:
        from agent.triage_core import score_prompt, triage_prompt

        easy_score, easy_reason = score_prompt("list files on my desktop")
        easy_ok = easy_score >= 7.0
        report.add(
            "Phase 1 — Scorer (easy → local)",
            "PASS" if easy_ok else "WARN",
            f"score={easy_score:.1f} — {easy_reason}",
        )

        hard_score, hard_reason = score_prompt(
            "Design a formal proof of Byzantine fault tolerant consensus"
        )
        hard_route = "claude" if hard_score < 7.0 else "local"
        report.add(
            "Phase 1 — Scorer (hard → delegate)",
            "PASS" if hard_score < 7.0 else "WARN",
            f"score={hard_score:.1f} route={hard_route} — {hard_reason}",
        )

        # Don't auto-delegate to Claude in test (needs claude CLI)
        triage = triage_prompt("list desktop files", auto_delegate=False)
        report.add(
            "Phase 1 — triage_prompt()",
            "PASS" if triage.route == "local" else "WARN",
            f"route={triage.route} score={triage.score:.1f}",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("Phase 1 — Scoring / triage", "FAIL", repr(exc))

    # --- Phase 2+3: Live chat → episodic save ---
    prompts = [
        "In one sentence: what is lmstudio-agent-mcp?",
        "Remember: my favorite Python tool is uv, not pip.",
        "What embedding model does our vector memory use?",
    ][: max(1, args.chat_turns)]

    print(f"\n--- Live chat ({len(prompts)} turns) ---")
    episodic_before = report.db_before["episodic"]
    try:
        from agent.rag_context import save_turn_and_maybe_summarize

        for i, prompt in enumerate(prompts, 1):
            print(f"\nTurn {i} user: {prompt}")
            assistant = _chat_local(prompt)
            print(f"Turn {i} assistant: {assistant[:200]}{'...' if len(assistant) > 200 else ''}")
            eid, summ = save_turn_and_maybe_summarize(
                prompt, assistant, workspace=str(LMSTUDIO.parent)
            )
            turn = {"prompt": prompt, "response_preview": assistant[:300], "episode_id": eid, "summarizer": summ}
            report.chat_turns.append(turn)
            if not eid:
                report.add(f"Chat turn {i} → episodic store", "FAIL", "save_turn returned None")
            else:
                report.add(f"Chat turn {i} → episodic store", "PASS", f"episode_id={eid[:8]}…")
            if summ:
                report.add("Phase 3 — auto-summarizer (N reached)", "PASS", summ.splitlines()[0])
            time.sleep(0.5)

        report.db_after = _db_snapshot()
        new_ep = report.db_after["episodic"] - episodic_before
        report.add(
            "Phase 2 — episodic embeddings in SQLite",
            "PASS" if new_ep >= len(prompts) else "FAIL",
            f"+{new_ep} episodic rows (total {report.db_after['episodic']})",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("Live chat → episodic pipeline", "FAIL", repr(exc))
        report.db_after = _db_snapshot()

    # --- Phase 2: RAG retrieval ---
    try:
        from agent.vector_memory import rag_search

        sem, ep = rag_search("uv python favorite tool")
        hit = ep or sem
        report.add(
            "Phase 2 — RAG top-k retrieval",
            "PASS" if hit else "WARN",
            f"semantic={len(sem)} episodic={len(ep)}"
            + (f" top_score={hit[0].score:.3f}" if hit else ""),
        )
        if hit:
            report.add(
                "Phase 2 — RAG content match",
                "PASS" if hit[0].score >= 0.25 else "WARN",
                hit[0].content[:100],
            )
    except Exception as exc:  # noqa: BLE001
        report.add("Phase 2 — RAG retrieval", "FAIL", repr(exc))

    # --- Phase 3: Force summarizer if not auto-triggered ---
    unsumm = report.db_after.get("unsummarized", 0)
    sem_before = report.db_after.get("semantic", 0)
    if args.force_summarize or unsumm >= 3:
        try:
            from agent.summarizer_core import run_summarization

            print("\n--- Running summarizer (force) ---")
            result = run_summarization(batch_size=min(unsumm, 10), force=True)
            report.db_after = _db_snapshot()
            new_sem = report.db_after["semantic"] - sem_before
            report.add(
                "Phase 3 — Summarizer → semantic facts",
                "PASS" if result.ran and result.facts_stored > 0 else ("WARN" if result.ran else "FAIL"),
                result.summary().replace("\n", " | "),
            )
            if result.facts:
                for f in result.facts[:5]:
                    report.add("  distilled fact", "PASS", f[:120])
        except Exception as exc:  # noqa: BLE001
            report.add("Phase 3 — Summarizer", "FAIL", repr(exc))

    # --- Verify semantic RAG after distill ---
    try:
        from agent.vector_memory import rag_search

        sem, _ = rag_search("user prefers uv over pip")
        report.add(
            "Phase 3 — semantic facts searchable via RAG",
            "PASS" if sem else "WARN",
            f"{len(sem)} semantic hit(s)" + (f": {sem[0].content[:80]}" if sem else ""),
        )
    except Exception as exc:  # noqa: BLE001
        report.add("Phase 3 — semantic RAG after distill", "FAIL", repr(exc))

    # --- Embedding proof ---
    try:
        samples = _sample_rows("episodic", 2) + _sample_rows("semantic", 2)
        all_have_emb = all(s["emb_bytes"] == 3072 for s in samples if s)
        report.add(
            "Embeddings stored (768-dim / 3072 bytes)",
            "PASS" if all_have_emb and samples else "FAIL",
            str(samples[:3]),
        )
    except Exception as exc:  # noqa: BLE001
        report.add("Embedding blob verification", "FAIL", repr(exc))

    # --- Bridge (optional) ---
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2) as r:
            health = json.loads(r.read())
        report.add(
            "Bridge :8765 (optional)",
            "PASS",
            f"resolved={health.get('resolved')}",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("Bridge :8765 (optional)", "WARN", f"not running: {exc!r}")

    # --- Summary ---
    print("\n" + "=" * 60)
    fails = sum(1 for l in report.links if l.status == "FAIL")
    warns = sum(1 for l in report.links if l.status == "WARN")
    passes = sum(1 for l in report.links if l.status == "PASS")
    print(f"RESULT: {passes} PASS, {warns} WARN, {fails} FAIL")
    print(f"DB after: episodic={report.db_after.get('episodic')} semantic={report.db_after.get('semantic')}")
    print(f"Report: {REPORT_PATH}")
    print("=" * 60)

    _write_report(report)
    sys.exit(1 if fails else 0)


def _write_report(report: E2EReport) -> None:
    payload = {
        "links": [{"name": l.name, "status": l.status, "detail": l.detail} for l in report.links],
        "db_before": report.db_before,
        "db_after": report.db_after,
        "chat_turns": report.chat_turns,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

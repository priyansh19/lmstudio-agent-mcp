#!/usr/bin/env python3
"""
test_agent_stack.py — Smoke tests for Phases 1–4 (no LM Studio required for core logic).

Usage:
    cd lmstudio && uv run python scripts/test_agent_stack.py
    cd lmstudio && uv run python scripts/test_agent_stack.py --live
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

LMSTUDIO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LMSTUDIO))


def ok(name: str) -> None:
    print(f"  OK  {name}")


def fail(name: str, detail: str) -> None:
    print(f"  FAIL {name}: {detail}")
    sys.exit(1)


def test_triage_parse() -> None:
    from agent.triage_core import _parse_score_json

    score, reason, needs = _parse_score_json('{"score": 8.5, "reason": "easy", "needs_claude": false}')
    assert score == 8.5 and needs is False, (score, needs)
    score2, _, needs2 = _parse_score_json("")
    assert score2 < 7 and needs2 is True
    ok("triage JSON parse + empty fallback")


def test_summarizer_parse() -> None:
    from agent.summarizer_core import _parse_facts_json

    facts = _parse_facts_json('{"facts": ["User prefers Python", "Repo root is Desktop"]}')
    assert len(facts) == 2
    assert _parse_facts_json("") == []
    ok("summarizer facts parse")


def test_procedural_memory() -> None:
    from agent.procedural_memory import discover_skill_files, load_procedural_context

    files = discover_skill_files(str(LMSTUDIO))
    assert any(p.name.lower() == "skill.md" for p in files), files
    block = load_procedural_context(str(LMSTUDIO))
    assert "Procedural memory" in block
    assert "Interaction style" in block or "interaction" in block.lower()
    ok(f"procedural memory ({len(files)} skill file(s))")


def test_vector_memory_metadata() -> None:
    from agent.vector_memory import VectorMemoryStore

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        store = VectorMemoryStore(db)
        # Direct insert without embeddings — test metadata helpers only
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (id, kind, content, metadata, embedding, created_at)
                VALUES ('e1', 'episodic', 'User: hi\\nAssistant: hello', '{}', X'0000', 1.0)
                """,
            )
            conn.commit()
        assert store.count_unsummarized("episodic") == 1
        store.mark_summarized(["e1"], batch_id="test-batch")
        assert store.count_unsummarized("episodic") == 0
    ok("vector memory summarize metadata")


def test_rag_context_augment() -> None:
    from agent.rag_context import augment_user_message

    msg = augment_user_message("list files", include_graph=False)
    assert msg.endswith("list files") and ("User request:" in msg or msg == "list files")
    ok("rag augment message format")


def test_configs_load() -> None:
    from agent.triage_core import load_config as triage_cfg
    from agent.vector_memory import load_config as memory_cfg
    from agent.procedural_memory import load_config as proc_cfg

    assert triage_cfg().get("threshold") == 7.0
    assert memory_cfg().get("summarize_every_n") == 10
    assert proc_cfg().get("enabled") is True
    ok("config files load")


def test_live_lmstudio(url: str) -> None:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/v1/models", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("data") or []
        ok(f"LM Studio reachable ({len(models)} models in catalog)")
    except (urllib.error.URLError, TimeoutError) as exc:
        fail("LM Studio live check", repr(exc))


def test_live_embeddings(url: str) -> None:
    from agent.embeddings import resolve_embedding_model

    try:
        model = resolve_embedding_model(url)
        ok(f"embedding model resolved: {model}")
    except Exception as exc:  # noqa: BLE001
        print(f"  SKIP embedding model: {exc!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Also ping LM Studio if running")
    ap.add_argument("--lmstudio-url", default="http://127.0.0.1:1234")
    args = ap.parse_args()

    print("Agent stack tests (Phases 1–4)\n")
    test_configs_load()
    test_triage_parse()
    test_summarizer_parse()
    test_procedural_memory()
    test_vector_memory_metadata()
    test_rag_context_augment()

    if args.live:
        print("\nLive checks:")
        test_live_lmstudio(args.lmstudio_url)
        test_live_embeddings(args.lmstudio_url)

    print("\nAll tests passed.")


if __name__ == "__main__":
    main()

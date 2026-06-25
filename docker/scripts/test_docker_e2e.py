#!/usr/bin/env python3
"""End-to-end Docker stack test — memory stores, networking, bridge plumbing."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

LM = os.environ.get("LMSTUDIO_URL", "http://host.docker.internal:1234")
BRIDGE = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8765")
VECTOR_DB = Path(os.environ["VECTOR_MEMORY_DB"])
GRAPH_MEM = Path(os.environ["MEMORY_FILE_PATH"])
SKILLS = Path(os.environ["SKILLS_DIR"])
WORKSPACE = Path(os.environ["WORKSPACE_ROOTS"])

sys.path.insert(0, "/app/lmstudio")

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    results.append((name, status, detail))
    icon = "✓" if ok else "✗"
    print(f"  [{icon} {status}] {name}")
    print(f"         {detail}")


def main() -> int:
    print("=" * 60)
    print("DOCKER STACK E2E TEST")
    print("=" * 60)

    # --- Volume mounts ---
    check(
        "Desktop bind — vector DB path",
        VECTOR_DB.parent.is_dir(),
        str(VECTOR_DB),
    )
    check(
        "Desktop bind — graph memory path",
        GRAPH_MEM.parent.is_dir(),
        str(GRAPH_MEM),
    )
    check(
        "Desktop bind — skills dir",
        SKILLS.is_dir() and any(SKILLS.glob("*.md")),
        f"{len(list(SKILLS.glob('*.md')))} skill file(s)",
    )
    check(
        "Desktop bind — workspace",
        WORKSPACE.is_dir(),
        str(WORKSPACE),
    )

    # --- Container networking → LM Studio on host ---
    try:
        with urllib.request.urlopen(f"{LM.rstrip('/')}/v1/models", timeout=10) as r:
            data = json.loads(r.read())
        ids = [m["id"] for m in data.get("data", [])]
        has_llm = any("embed" not in i.lower() for i in ids)
        has_emb = any("embed" in i.lower() for i in ids)
        check(
            "Network — agent → host LM Studio :1234",
            has_llm and has_emb,
            f"LLM={'yes' if has_llm else 'no'} embed={'yes' if has_emb else 'no'} ({len(ids)} models)",
        )
    except Exception as exc:  # noqa: BLE001
        check("Network — agent → host LM Studio :1234", False, repr(exc))

    # --- Bridge health (from inside agent container) ---
    try:
        with urllib.request.urlopen(f"{BRIDGE.rstrip('/')}/health", timeout=5) as r:
            health = json.loads(r.read())
        check(
            "Bridge — :8765 health inside container",
            health.get("ok") is True and bool(health.get("resolved")),
            json.dumps(health),
        )
    except Exception as exc:  # noqa: BLE001
        check("Bridge — :8765 health inside container", False, repr(exc))

    # --- Phase 2: vector store write + RAG ---
    try:
        from agent.vector_memory import VectorMemoryStore, rag_search, store_episode, store_semantic

        store = VectorMemoryStore(VECTOR_DB)
        before_sem = store.count("semantic")
        before_ep = store.count("episodic")

        eid = store_episode(
            "Docker e2e test: user prefers uv over pip for Python packages.",
            metadata={"source": "docker_e2e"},
        )
        sid = store_semantic(
            "User runs lmstudio-agent stack in Docker with Desktop volume mounts.",
            metadata={"source": "docker_e2e"},
        )
        after_sem = store.count("semantic")
        after_ep = store.count("episodic")

        check(
            "Phase 2 — episodic write (vector store)",
            eid and after_ep > before_ep,
            f"episode_id={eid[:8]}… total={after_ep}",
        )
        check(
            "Phase 2 — semantic write (vector store)",
            sid and after_sem > before_sem,
            f"semantic_id={sid[:8]}… total={after_sem}",
        )

        sem, ep = rag_search("uv python package manager")
        hit = sem or ep
        check(
            "Phase 2 — RAG retrieval across stores",
            bool(hit) and hit[0].score >= 0.25,
            f"semantic={len(sem)} episodic={len(ep)} top_score={hit[0].score:.3f}" if hit else "no hits",
        )

        # Embedding blob size (768-dim = 3072 bytes)
        conn = sqlite3.connect(VECTOR_DB)
        row = conn.execute("SELECT length(embedding) FROM memories LIMIT 1").fetchone()
        conn.close()
        check(
            "Phase 2 — embeddings in SQLite (3072 bytes)",
            row and row[0] == 3072,
            f"embedding_bytes={row[0] if row else None}",
        )
        check(
            "Phase 2 — vector DB file on Desktop mount",
            VECTOR_DB.is_file() and VECTOR_DB.stat().st_size > 0,
            f"{VECTOR_DB.stat().st_size} bytes",
        )
    except Exception as exc:  # noqa: BLE001
        check("Phase 2 — vector memory pipeline", False, repr(exc))

    # --- Phase 4: procedural memory ---
    try:
        from agent.procedural_memory import discover_skill_files, load_procedural_context

        files = discover_skill_files(str(WORKSPACE))
        block = load_procedural_context(str(WORKSPACE))
        check(
            "Phase 4 — Skill.md from Desktop skills mount",
            bool(files) and "Procedural memory" in block,
            f"{len(files)} file(s), {len(block)} chars",
        )
    except Exception as exc:  # noqa: BLE001
        check("Phase 4 — procedural memory", False, repr(exc))

    # --- Graph memory write/read ---
    try:
        from agent.memory_context import augment_user_message

        # Seed a graph entity line if empty
        if GRAPH_MEM.stat().st_size == 0:
            GRAPH_MEM.write_text(
                json.dumps(
                    {
                        "type": "entity",
                        "name": "DockerTest",
                        "entityType": "System",
                        "observations": ["Stack verified via docker e2e test"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        ctx = augment_user_message("Tell me about DockerTest system")
        check(
            "Graph memory — read from Desktop mount",
            "DockerTest" in ctx or "docker" in ctx.lower(),
            ctx[:120] if ctx else "(empty)",
        )
        check(
            "Graph memory — file persisted on mount",
            GRAPH_MEM.is_file() and GRAPH_MEM.stat().st_size > 0,
            f"{GRAPH_MEM.stat().st_size} bytes",
        )
    except Exception as exc:  # noqa: BLE001
        check("Graph memory pipeline", False, repr(exc))

    # --- Phase 1: triage scoring via host LM ---
    try:
        from agent.triage_core import score_prompt

        score, reason = score_prompt("list files in workspace")
        check(
            "Phase 1 — triage scorer via host LM",
            score >= 0,
            f"score={score:.1f} — {reason[:80]}",
        )
    except Exception as exc:  # noqa: BLE001
        check("Phase 1 — triage scorer", False, repr(exc))

    # --- Bridge chat completion proxy ---
    try:
        payload = json.dumps(
            {
                "model": "local/current",
                "messages": [{"role": "user", "content": "Reply with exactly: docker-ok"}],
                "max_tokens": 16,
                "temperature": 0,
            }
        ).encode()
        req = urllib.request.Request(
            f"{BRIDGE.rstrip('/')}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read())
        reply = body["choices"][0]["message"]["content"]
        check(
            "Bridge — chat completion proxy to LM Studio",
            "docker" in reply.lower() or "ok" in reply.lower(),
            reply[:80],
        )
    except Exception as exc:  # noqa: BLE001
        check("Bridge — chat completion proxy", False, repr(exc))

    # --- Summary ---
    print("\n" + "=" * 60)
    fails = sum(1 for _, s, _ in results if s == "FAIL")
    passes = sum(1 for _, s, _ in results if s == "PASS")
    print(f"RESULT: {passes} PASS, {fails} FAIL")
    print("=" * 60)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

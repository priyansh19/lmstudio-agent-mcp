# memory-rag — Phase 2 semantic + episodic vector RAG

**MCP server:** `memory-rag`  
**Source:** `servers/memory_rag_tools.py` + `agent/vector_memory.py`  
**Config:** `config/memory.json`  
**Store:** `.vector-memory.db` (SQLite, local)

---

## Architecture role

From [Architecture_Daigram.excalidraw](../../Architecture_Daigram.excalidraw):

| Store | Contents | Retrieval |
|---|---|---|
| **Semantic** | Durable facts, user profile, project knowledge | RAG top-k |
| **Episodic** | Dated events, past chat turns | RAG top-k |

Both feed into the local agent system context before each turn (`agent/rag_context.py`).

---

## Tools

| Tool | Purpose |
|---|---|
| `remember_fact` | Write semantic memory |
| `remember_episode` | Write episodic memory |
| `search_semantic` | Query facts |
| `search_episodic` | Query past events/chats |
| `rag_preview` | Preview injected context block |
| `summarize_now` | Force Phase 3 summarizer run |
| `memory_rag_status` | Config + counts |

---

## Requirements

Load an **embedding model** in LM Studio (e.g. `nomic-embed-text`, `text-embedding-bge-small`). The stack calls `POST /v1/embeddings` on your LM Studio server.

Optional env:

| Variable | Purpose |
|---|---|
| `LMSTUDIO_URL` | Default `http://127.0.0.1:1234` |
| `EMBEDDING_MODEL` | Force a specific embedding model key |
| `VECTOR_MEMORY_DB` | Override SQLite path |
| `RAG_ENABLED=0` | Disable RAG injection |

---

## Agent integration

| Component | Behavior |
|---|---|
| **`local_agent.py`** | Auto-injects RAG before each turn (`--no-rag` to disable) |
| **`local_agent.py`** | Saves completed turns to episodic store |
| **LM Studio MCP** | Model can call `remember_fact` / `search_*` manually |

Phase 3 (summarizer → distill facts) builds on this store.

---

## Phase 3 — Summarizer

When **N** unsummarized episodic chats accumulate (default **10**), a local LLM summarizer runs automatically:

1. Reads the oldest batch of episodic memories
2. Distills durable facts (preferences, decisions, project context)
3. Writes facts to **semantic** memory
4. Marks episodes as `summarized` in metadata

| Setting | Default | Config key |
|---|---|---|
| Enable | `true` | `summarizer_enabled` |
| Batch size N | `10` | `summarize_every_n` |

**MCP tool:** `summarize_now` — force a consolidation run.

**Agent integration:** `save_turn_and_maybe_summarize()` in `rag_context.py` triggers after each saved turn.

Disable: `SUMMARIZER_ENABLED=0` or `"summarizer_enabled": false` in `config/memory.json`.

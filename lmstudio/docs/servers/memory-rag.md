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

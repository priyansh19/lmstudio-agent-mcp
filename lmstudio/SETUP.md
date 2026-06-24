# LM Studio Local Agent — Complete Setup Guide

This document is the **authoritative setup guide** for reproducing the full local
AI agent stack on a fresh macOS machine. Everything in this repo is designed so
you run **one script** (`bootstrap.sh`) and get the same environment every time.

**Author setup:** priyansh19 · `priyansh.9071@gmail.com`
**Target platform:** macOS (Apple Silicon or Intel)  
**Primary tools:** LM Studio, MCP servers

---

## Table of contents

1. [What this stack does](#1-what-this-stack-does)
2. [Architecture](#2-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Fresh machine setup (one command)](#4-fresh-machine-setup-one-command)
5. [LM Studio configuration](#5-lm-studio-configuration)
6. [GitHub integration](#6-github-integration)
7. [Memory system](#7-memory-system)
8. [MCP server reference](#8-mcp-server-reference)
9. [Daily usage](#9-daily-usage)
10. [Troubleshooting](#10-troubleshooting)
11. [Repository layout](#11-repository-layout)

---

## 1. What this stack does

A local LLM in LM Studio (Gemma, Devstral, Qwen, etc.) is normally just a
chatbot — it can only talk. This project gives it **real powers**:

| Capability | How |
|---|---|
| Read/write/edit files | `coding-tools` MCP server |
| Run shell, Python, Node | `coding-tools` |
| Search code structurally | `codebase-memory` (knowledge graph) |
| Browse the web / automate UI | `playwright`, `web-tools` |
| Git commit & push | Local git + macOS keychain |
| GitHub API (PRs, issues, search) | `github` + `github-watch` MCP |
| Docker operations | `docker-tools` |
| Live library docs | `context7` |
| Persistent memory across chats | `memory` MCP + auto-recall + `memory-rag` vector RAG |
| Prompt triage / expert fallback | `triage` + `think-delegate` |

**Key design goal:** swap models in LM Studio without changing other config. The **bridge** (optional) resolves whatever model is loaded on each request.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  You (LM Studio Chat / Terminal agent / OpenAI bridge clients)  │
└────────────┬───────────────────────────────┬────────────────────┘
             │                               │
    LM Studio GUI                    Optional bridge :8765
    (MCP tools in chat)              (local/current)
             │                               │
             └───────────────┬───────────────┘
                             ▼
                  LM Studio server :1234/v1
                  (LLM + embedding model for RAG)
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        coding-tools   memory-rag       triage
        web-tools      memory           think-delegate
        docker-tools   codebase-memory  github …
```

See [../Architecture_Daigram.excalidraw](../Architecture_Daigram.excalidraw) and [../README.md](../README.md) for the full architecture.

**Config files written outside this repo:**

| File | Purpose |
|---|---|
| `~/.lmstudio/mcp.json` | LM Studio MCP servers |
| `~/Library/LaunchAgents/com.lmstudio-agent.bridge.plist` | Auto-start bridge (optional) |
| macOS Keychain | GitHub push credentials |
| `.agent-memory.json` (in repo, gitignored) | Knowledge-graph memory |

---

## 3. Prerequisites

Install manually **before** bootstrap if you prefer; otherwise bootstrap installs them:

| Tool | Why |
|---|---|
| **LM Studio** | Local LLM runtime ([lmstudio.ai](https://lmstudio.ai)) |
| **Homebrew** | Node.js, optional packages |
| **uv** | Modern Python (system Python 3.9 is too old for `mcp`) |
| **Node.js / npx** | Community MCP servers (`playwright`, `memory`, etc.) |

Hardware: Apple Silicon Mac Mini with 16 GB+ RAM recommended for 7B+ coder models.

---

## 4. Fresh machine setup (one command)

### Clone this repository

```bash
git clone https://github.com/priyansh19/lmstudio-agent-mcp.git
cd lmstudio-agent-mcp
```

### Run bootstrap

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

**Interactive mode** (first time): asks about GitHub, Google, Slack, LaunchAgent.

**Non-interactive** (recommended defaults):

```bash
./bootstrap.sh --yes
```

**With GitHub token:**

```bash
GITHUB_TOKEN=ghp_xxx \
GIT_NAME="priyansh19" \
GIT_EMAIL="priyansh.9071@gmail.com" \
./bootstrap.sh --yes
```

### What bootstrap runs (8 steps)

| Step | Action |
|------|--------|
| 1 | Install Homebrew, uv, Node, LM Studio CLI |
| 1b | **Fix macOS `/tmp` permissions** (LM Studio model load) |
| 2 | `uv sync` — Python dependencies |
| 3 | Choose workspace sandbox (default `~/Desktop`) |
| 4 | Install `codebase-memory-mcp`, seed memory, index this repo |
| 5 | Install MCP servers into `~/.lmstudio/mcp.json` |
| 5b | **think-delegate** — Claude CLI escalation (subscription, no API key) |
| 6 | GitHub — git identity, keychain, `github` + `github-watch` MCP (optional) |
| 7 | Google / Brave / Firecrawl / Slack (optional) |
| 8 | macOS LaunchAgent — bridge starts on every login (optional) |

### Other modes

```bash
./bootstrap.sh --minimal    # skip optional connector prompts
./bootstrap.sh --deps-only  # refresh Python env only
./bootstrap.sh --help
```

`install.sh` and `setup.sh` are wrappers — **`bootstrap.sh` is the only script you need**.

---

## 5. LM Studio configuration

After bootstrap:

### Start the server and load a model

```bash
lms server start          # or enable server in LM Studio GUI
lms load                  # pick a tool-capable model
```

**Model recommendations for tool use:**

| Model | Notes |
|---|---|
| Qwen2.5-Coder-7B-Instruct | Best balance for coding + tools |
| Devstral Small | Strong coder, vision capable |
| Gemma 4 | Works for simple tasks; weak at multi-step tools |

### System prompt

Paste the contents of **`lmstudio/prompts/system-prompt.md`** into:

**LM Studio → Chat → System Prompt** (right sidebar)

This instructs the model to use memory, codebase-memory, GitHub workflow, and playwright.

### Enable MCP servers

**LM Studio → Program → Edit mcp.json** — toggle servers on, then restart LM Studio.

Installed by default:

- `coding-tools`, `web-tools`, `docker-tools`
- `codebase-memory`, `memory`, `git`, `time`, `context7`, `playwright`
- `github`, `github-watch` (if you configured GitHub during bootstrap)

### Verify

```bash
curl http://127.0.0.1:1234/v1/models
```

Ask in chat: *"List files on my Desktop"* — the model should call `list_directory`.

---

## 6. GitHub integration

Bootstrap step 6 (or manual):

```bash
GITHUB_TOKEN=ghp_xxx ./scripts/setup_github.sh "Your Name" "you@example.com"
```

This does three things:

1. **Git identity** — `git config user.name` / `user.email`
2. **Push auth** — token stored in macOS Keychain (HTTPS push works)
3. **MCP servers** — `github` (full API) + `github-watch` (PR/CI polling)

### GitHub MCP split (Claude-parity)

| Server | Use for |
|---|---|
| `github` | Create repos, PRs, issues, code search, releases, Actions |
| `github-watch` | `gh_watch` + `gh_poll` — CI status, reviews, merge state |
| Local `git` + `coding-tools` | Edit files, commit, push from cloned repos |

Create token at: https://github.com/settings/tokens  
Scopes: `repo`, `workflow`, `read:org`

---

## 7. Memory system

### Two layers

| Layer | What | Where |
|---|---|---|
| **Auto-recall** | Injects relevant facts into every terminal-agent message | `agent/memory_context.py` |
| **Memory MCP** | Model writes durable facts via `add_observations` | `.agent-memory.json` |

### Seed memory

Bootstrap runs `scripts/seed_memory.py` — pre-loads facts about you and this project.

Re-seed after editing `scripts/seed_memory.py`:

```bash
uv run python scripts/seed_memory.py
```

### LM Studio chat

Paste `lmstudio/prompts/system-prompt.md` so the model reads/writes memory via MCP tools.

**Never store secrets in memory** — only credential *locations* (e.g. "token in keychain").

---

## 8. MCP server reference

See **[CATALOG.md](CATALOG.md)** for the full annotated list.

### Custom servers (this repo)

| Server | Tools |
|---|---|
| `coding-tools` | Files, shell, Python/Node, git wrappers |
| `web-tools` | `fetch_url`, `web_search` |
| `docker-tools` | ps, build, run, exec, logs, compose |
| `github-watch` | PR/issue CI polling |

### Community servers (installed via npx/uvx)

| Server | Purpose |
|---|---|
| `codebase-memory` | AST knowledge graph — 99% fewer tokens vs grep loops |
| `memory` | Persistent knowledge graph |
| `context7` | Live library documentation |
| `playwright` | Browser automation |
| `git` | Rich git operations |
| `github` | Full GitHub REST API |

---

## 9. Daily usage

### Terminal autonomous agent

```bash
cd ~/Desktop/lmstudio-agent-mcp
uv run python agent/local_agent.py --root "$HOME/Desktop"
```

Memory auto-recall is on by default. One-shot task:

```bash
uv run python agent/local_agent.py --root "$HOME/Desktop" \
  --task "create hello.py that prints fib(20) and run it"
```

### LM Studio chat

1. Load model + start server
2. System prompt pasted
3. MCP servers toggled on
4. Chat normally — approve tool calls in the UI

### Reconfigure anytime

```bash
./bootstrap.sh --yes
```

---

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| **`PermissionError: /tmp/tmp...` when loading model** | Run `./scripts/fix_macos_tmp.sh --fix` or re-run `./bootstrap.sh` (step 1b). Expected: `drwxrwxrwt` on `/private/tmp` |
| MCP server fails to start | Check LM Studio Developer Logs; re-run `uv run python scripts/install_to_lmstudio.py` |
| `git` MCP error "not a valid Git repository" | Fixed — git server no longer requires a fixed repo path |
| Bridge not running after reboot | `launchctl print gui/$(id -u)/com.lmstudio-agent.bridge` |
| Bridge 503 / no model | Load a model in LM Studio + `lms server start` |
| RAG returns nothing | Load an embedding model in LM Studio; check `memory-rag` MCP |
| Memory empty in chat | Paste system prompt; run `seed_memory.py`; model may skip tools on small models |
| GitHub push fails | Re-run `setup_github.sh` with fresh token |
| think-delegate fails | Install Claude CLI + `claude auth login`. Do not set `ANTHROPIC_API_KEY` on that server |
| codebase-memory not found | Re-run bootstrap step 4 |

**Logs:**

```bash
tail -f ~/Desktop/lmstudio-agent-mcp/.bridge.log
```

---

## 11. Repository layout

```
lmstudio-agent-mcp/
├── README.md                     ← architecture + overview
├── Architecture_Daigram.excalidraw
└── lmstudio/
    ├── bootstrap.sh              ← setup script (start here)
    ├── SETUP.md                  ← this guide
    ├── agent/
    │   ├── local_agent.py        ← terminal autonomous agent
    │   ├── lmstudio_bridge.py    ← OpenAI bridge (:8765)
    │   ├── triage_core.py        ← Phase 1 scoring
    │   ├── vector_memory.py      ← Phase 2 RAG stores
    │   └── rag_context.py        ← RAG injection
    ├── servers/                  ← MCP Python servers
    ├── config/                   ← triage.json, memory.json, …
    ├── mcp/mcp.json              ← LM Studio MCP template
    └── scripts/
        ├── install_to_lmstudio.py
        └── install_bridge_launchagent.sh
```

---

## Quick reference card

```bash
# Full setup (fresh Mac)
git clone https://github.com/priyansh19/lmstudio-agent-mcp.git && cd lmstudio-agent-mcp/lmstudio
./bootstrap.sh --yes

# Start LM Studio (LLM + embedding model)
lms server start && lms load

# Verify bridge (optional)
curl http://127.0.0.1:8765/health

# Terminal agent
uv run python agent/local_agent.py --root ~/Desktop
```

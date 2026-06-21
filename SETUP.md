# LM Studio Local Agent — Complete Setup Guide

This document is the **authoritative setup guide** for reproducing the full local
AI agent stack on a fresh macOS machine. Everything in this repo is designed so
you run **one script** (`bootstrap.sh`) and get the same environment every time.

**Author setup:** priyansh19  
**Target platform:** macOS (Apple Silicon or Intel)  
**Primary tools:** LM Studio, OpenClaw (optional), MCP servers

---

## Table of contents

1. [What this stack does](#1-what-this-stack-does)
2. [Architecture](#2-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Fresh machine setup (one command)](#4-fresh-machine-setup-one-command)
5. [LM Studio configuration](#5-lm-studio-configuration)
6. [OpenClaw + WhatsApp integration](#6-openclaw--whatsapp-integration)
7. [GitHub integration](#7-github-integration)
8. [Memory system](#8-memory-system)
9. [MCP server reference](#9-mcp-server-reference)
10. [Daily usage](#10-daily-usage)
11. [Troubleshooting](#11-troubleshooting)
12. [Repository layout](#12-repository-layout)

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
| Persistent memory across chats | `memory` MCP + auto-recall |
| WhatsApp / 24×7 agent | OpenClaw → LM Studio bridge |

**Key design goal:** swap models in LM Studio without changing OpenClaw or any
other config. The **bridge** resolves whatever model is loaded on each request.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  You (LM Studio Chat / OpenClaw WhatsApp / Terminal agent)      │
└────────────┬───────────────────────────────┬────────────────────┘
             │                               │
    LM Studio GUI                    OpenClaw gateway
    (MCP tools in chat)              (model: local-agent/local/current)
             │                               │
             │                      ┌────────▼────────┐
             │                      │ Bridge :8765    │
             │                      │ local/current   │
             │                      │ (LaunchAgent)   │
             │                      └────────┬────────┘
             │                               │
             └───────────────┬───────────────┘
                             ▼
                  LM Studio server :1234/v1
                  (whatever model you loaded)
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        coding-tools   codebase-memory   github
        web-tools      context7          playwright
        docker-tools   memory            git …
```

**Config files written outside this repo:**

| File | Purpose |
|---|---|
| `~/.lmstudio/mcp.json` | LM Studio MCP servers |
| `~/.openclaw/openclaw.json` | OpenClaw model + MCP sync |
| `~/Library/LaunchAgents/com.lmstudio-agent.bridge.plist` | Auto-start bridge |
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
| **OpenClaw** (optional) | 24×7 agent, WhatsApp ([openclaw.ai](https://openclaw.ai)) |

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

**Interactive mode** (first time): asks about GitHub, Google, Slack, OpenClaw, LaunchAgent.

**Non-interactive** (recommended defaults):

```bash
./bootstrap.sh --yes
```

**With GitHub token:**

```bash
GITHUB_TOKEN=ghp_xxx \
GIT_NAME="priyansh19" \
GIT_EMAIL="guptapriyansh1907@gmail.com" \
./bootstrap.sh --yes
```

### What bootstrap runs (9 steps)

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
| 8 | OpenClaw → bridge config (optional) |
| 9 | macOS LaunchAgent — bridge starts on every login |

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

Paste the contents of **`config/lmstudio-system-prompt.md`** into:

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

## 6. OpenClaw + WhatsApp integration

OpenClaw lets your local model respond on WhatsApp 24/7 without cloud API costs.

### How model swapping works

OpenClaw is configured **once** with:

```
provider: local-agent
model:    local-agent/local/current
endpoint: http://127.0.0.1:8765/v1
```

The **bridge** (port 8765) asks LM Studio which model is loaded on every request.
Change models in LM Studio anytime — OpenClaw config never changes.

### Setup (included in bootstrap step 8)

```bash
uv run python scripts/setup_openclaw_lmstudio.py --with-mcp
openclaw gateway restart
```

`--with-mcp` copies your LM Studio MCP servers into OpenClaw so WhatsApp messages
get the same tools.

### Auto-start bridge on login (bootstrap step 9)

```bash
bash scripts/install_bridge_launchagent.sh
```

Verify after reboot:

```bash
curl http://127.0.0.1:8765/health
# → {"ok": true, "stable_model": "local/current", "resolved": "your-model-id"}
```

### Daily workflow

1. Mac boots → bridge starts automatically (LaunchAgent)
2. Open LM Studio → load any model → `lms server start`
3. OpenClaw gateway running → WhatsApp messages use the loaded model

---

## 7. GitHub integration

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

## 8. Memory system

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

Paste `config/lmstudio-system-prompt.md` so the model reads/writes memory via MCP tools.

**Never store secrets in memory** — only credential *locations* (e.g. "token in keychain").

---

## 9. MCP server reference

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

## 10. Daily usage

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

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| **`PermissionError: /tmp/tmp...` when loading model** | Run `./scripts/fix_macos_tmp.sh --fix` or re-run `./bootstrap.sh` (step 1b). Expected: `drwxrwxrwt` on `/private/tmp` |
| MCP server fails to start | Check LM Studio Developer Logs; re-run `uv run python scripts/install_to_lmstudio.py` |
| `git` MCP error "not a valid Git repository" | Fixed — git server no longer requires a fixed repo path |
| Bridge not running after reboot | `launchctl print gui/$(id -u)/com.lmstudio-agent.bridge` |
| Bridge 503 / no model | Load a model in LM Studio + `lms server start` |
| OpenClaw still uses Claude | `openclaw models status` → should show `local-agent/local/current` |
| Memory empty in chat | Paste system prompt; run `seed_memory.py`; model may skip tools on small models |
| GitHub push fails | Re-run `setup_github.sh` with fresh token |
| think-delegate fails | Install Claude CLI + `claude auth login`. Do not set `ANTHROPIC_API_KEY` on that server |
| codebase-memory not found | Re-run bootstrap step 4 |

**Logs:**

```bash
tail -f ~/Desktop/lmstudio-agent-mcp/.bridge.log
```

---

## 12. Repository layout

```
lmstudio-agent-mcp/
├── bootstrap.sh              ← THE setup script (start here)
├── install.sh                ← wrapper → bootstrap.sh
├── setup.sh                  ← wrapper → bootstrap.sh --deps-only
├── SETUP.md                  ← this guide
├── README.md                 ← project overview
├── CATALOG.md                ← MCP server catalog
├── agent/
│   ├── local_agent.py        ← terminal autonomous agent
│   ├── lmstudio_bridge.py    ← OpenAI bridge for OpenClaw (:8765)
│   └── memory_context.py     ← auto memory recall
├── mcp_server/
│   ├── coding_tools.py       ← filesystem + shell + git
│   ├── web_tools.py          ← fetch + search
│   ├── docker_tools.py       ← Docker operations
│   └── github_watch_tools.py ← PR/CI polling
├── config/
│   ├── mcp.json              ← LM Studio MCP template
│   ├── optional-with-keys.json
│   └── lmstudio-system-prompt.md
└── scripts/
    ├── install_to_lmstudio.py
    ├── setup_openclaw_lmstudio.py
    ├── setup_github.sh
    ├── install_bridge_launchagent.sh
    ├── fix_macos_tmp.sh          ← repair /tmp for LM Studio model loading
    ├── setup_think_delegate.sh   ← Claude CLI escalation MCP
    └── seed_memory.py
```

---

## Quick reference card

```bash
# Full setup (fresh Mac)
git clone https://github.com/priyansh19/lmstudio-agent-mcp.git && cd lmstudio-agent-mcp
./bootstrap.sh --yes

# Start LM Studio
lms server start && lms load

# Verify bridge
curl http://127.0.0.1:8765/health

# Terminal agent
uv run python agent/local_agent.py --root ~/Desktop

# Restart OpenClaw
openclaw gateway restart
```

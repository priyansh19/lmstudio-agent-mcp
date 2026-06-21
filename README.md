# LM Studio Agent MCP — give your local model real powers

> **Full setup guide:** see **[SETUP.md](SETUP.md)** — step-by-step instructions to
> reproduce this entire stack on a fresh Mac with one command (`./bootstrap.sh`).

This turns a local LLM running in **LM Studio** (e.g. Gemma) from a chatbot into
an **autonomous agent** that can read/write/edit files, search code, run shell
commands, execute Python/Node, browse the web, and use git.

It ships two things:

1. **MCP servers** (`mcp_server/`) — standard Model Context Protocol tool
   connectors you can plug into LM Studio's GUI via `mcp.json`.
2. **A standalone agent** (`agent/local_agent.py`) — a terminal coding agent that
   uses LM Studio's `.act()` multi-round tool-calling loop with the same tools.

Everything is sandboxed to a workspace root you choose, with a guardrail
blocklist on destructive shell commands.

---

## How it actually works

LLMs can only output text. "Tool use" means: the model emits a structured
request → your code runs the function → the result is fed back → the model
continues. LM Studio supports this two ways, and this repo uses both:

| Path | What it is | Best for |
| --- | --- | --- |
| **MCP servers** (`config/mcp.json`) | Tools exposed over the Model Context Protocol; LM Studio's chat UI calls them | Chatting in the LM Studio app with tools |
| **`.act()` agent** (`agent/local_agent.py`) | A Python loop that auto-runs tools across multiple rounds | A real autonomous coding agent in your terminal |

---

## Plug-and-play server catalog

Beyond the custom servers below, this repo ships a curated catalog of verified
community MCP servers (filesystem, fetch, memory, git, time, context7, playwright,
GitHub, Google Workspace/Gmail, Slack, databases, and more). See
[`CATALOG.md`](CATALOG.md). Install the zero-config ones into LM Studio in one
command:

```bash
uv run python scripts/install_to_lmstudio.py            # no-key servers
uv run python scripts/install_to_lmstudio.py --include-keys --only github google-workspace
```

This merges them into `~/.lmstudio/mcp.json` (backing up your existing config).

## Tools included

**Filesystem & code (`coding_tools.py`)**
`list_allowed_roots`, `list_directory`, `read_file`, `write_file`, `edit_file`,
`create_directory`, `move_path`, `delete_path`, `find_files`, `grep`,
`run_shell`, `run_python`, `run_node`, `git_status`, `git_diff`, `git_log`,
`git_commit`.

**Web (`web_tools.py`)**
`fetch_url` (read any page as text), `web_search` (keyless DuckDuckGo search).

---

## OpenClaw → LM Studio (swap models without config changes)

OpenClaw should **not** point directly at LM Studio's model list (that changes every
time you load a different model). Instead, use the **bridge** — a stable OpenAI
server that always exposes one model id: `local/current`.

```
OpenClaw  →  bridge :8765/v1  →  LM Studio :1234/v1  →  whatever model is loaded
             model: local/current      (auto-resolved each request)
```

### One-time setup

```bash
cd ~/Desktop/lmstudio-agent-mcp

# 1) Configure OpenClaw (writes ~/.openclaw/openclaw.json once)
uv run python scripts/setup_openclaw_lmstudio.py --with-mcp

# 2) Auto-start bridge on every Mac login (recommended)
bash scripts/install_bridge_launchagent.sh

# Or run manually once:
# uv run python agent/lmstudio_bridge.py

# 3) LM Studio: load any model + keep server running
lms server start

# 4) Restart OpenClaw gateway
openclaw gateway restart
```

After this, OpenClaw's primary model is **`local-agent/local/current`**. Change
models in LM Studio anytime — OpenClaw config stays the same.

Verify:
```bash
curl http://127.0.0.1:8765/health
openclaw models status
```

`--with-mcp` copies your LM Studio MCP servers into OpenClaw's `mcp.servers` so
WhatsApp/Telegram messages get the same tools (coding-tools, github, codebase-memory, etc.).

## Setup — one command

**`bootstrap.sh`** is the single script that reproduces this entire stack on a fresh Mac:

```bash
cd ~/Desktop/lmstudio-agent-mcp
./bootstrap.sh              # interactive (first time)
./bootstrap.sh --yes        # accept recommended defaults
./bootstrap.sh --minimal    # skip GitHub/Google/Slack prompts
./bootstrap.sh --deps-only  # refresh Python deps only
./bootstrap.sh --help
```

Non-interactive with secrets:
```bash
GITHUB_TOKEN=ghp_xxx GIT_NAME="you" GIT_EMAIL=you@mail.com ./bootstrap.sh --yes
```

`install.sh` and `setup.sh` are thin wrappers that call `bootstrap.sh`.

<details>
<summary>What bootstrap runs (9 steps)</summary>

1. Prerequisites — Homebrew, uv, Node, LM Studio CLI
2. Python dependencies (`uv sync`)
3. Workspace sandbox (`~/Desktop` by default)
4. codebase-memory-mcp + memory seed + repo index
5. LM Studio MCP servers → `~/.lmstudio/mcp.json`
6. GitHub (optional) — git identity, keychain, github + github-watch MCP
7. Google / Brave / Firecrawl / Slack (optional)
8. OpenClaw → stable bridge (`local-agent/local/current`)
9. LaunchAgent — bridge auto-starts on Mac login

</details>

Then start LM Studio's server and load a tool-capable model:

```bash
npx lmstudio install-cli   # one time
lms server start
lms load                   # pick a model (bigger = better at tools)
```

> Model tip: tool use is much more reliable on capable instruct models. Gemma
> works for simple tasks; for serious coding, a 7B+ tool-tuned model (e.g.
> Qwen2.5-Coder-7B-Instruct) will behave far better.

---

## Use it

### Autonomous CLI agent (recommended)

```bash
uv run python agent/local_agent.py --root "$HOME/Desktop"
# optional: --model qwen2.5-coder-7b-instruct
# one-shot:  --task "create a python script that prints fib(20) and run it"
```

Type a request; the agent plans, calls tools across multiple rounds, and
verifies its own work.

### Plug into the LM Studio app

Open LM Studio → `Program` → `Edit mcp.json`, and merge the `mcpServers` block
from [`config/mcp.json`](config/mcp.json) (or copy the whole file into
`~/.lmstudio/mcp.json`). Toggle the servers on, then ask the model to do things
in chat — it will request tool calls you approve.

Edit the `--root` path in `config/mcp.json` to control which directory the tools
may touch.

---

## Safety

- All file/shell operations are confined to the configured workspace root(s).
- Destructive commands (`rm -rf /`, `mkfs`, `sudo`, fork bombs, …) are blocked.
- This is a **guardrail, not a jail.** Only point it at directories you're
  willing to let a model modify, and review tool calls in the LM Studio UI.

---

## Layout

```
lmstudio-agent-mcp/
├── mcp_server/
│   ├── coding_tools.py   # filesystem + shell + code + git MCP server
│   └── web_tools.py      # web fetch + search MCP server
├── agent/
│   └── local_agent.py    # autonomous .act() terminal agent
├── config/
│   └── mcp.json          # LM Studio MCP connector config
├── pyproject.toml        # deps (uv)
├── requirements.txt      # deps (pip fallback)
└── setup.sh              # one-shot setup
```

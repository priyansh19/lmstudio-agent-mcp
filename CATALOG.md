# MCP Server Catalog — plug-and-play for LM Studio

A curated set of MCP servers that turn your local model into a capable agent.
Everything here runs via `npx` (Node) or `uvx`/`uv` (Python) — **no cloning, no
build steps**. You already have Node 26 and uv installed, so these "just run".

Install all the zero-config ones into LM Studio in one command:

```bash
uv run python scripts/install_to_lmstudio.py
```

Add the API-key/OAuth ones once you've filled their credentials:

```bash
uv run python scripts/install_to_lmstudio.py --include-keys
# or a subset:
uv run python scripts/install_to_lmstudio.py --include-keys --only github google-workspace
```

Then open LM Studio → **Program → mcp.json** and toggle servers on.

---

## Tier 1 — Local custom servers (built in this repo)

| Server | Tools | Notes |
| --- | --- | --- |
| `coding-tools` | read/write/edit files, grep, find, run_shell, run_python, run_node, git | Sandboxed to `~/Desktop`. The core coding muscle. |
| `web-tools` | fetch_url, web_search (keyless) | Lightweight, no dependencies. |
| `docker-tools` | ps, images, build, run, exec, logs, stop/rm, compose | Operates your Docker Engine. |

## Tier 2 — Zero-config community servers (no API key)

Installed by default. Verified package names/versions.

| Server | Package | What it gives the model |
| --- | --- | --- |
| `filesystem` | `@modelcontextprotocol/server-filesystem` | Official, hardened file access (scoped to `~/Desktop`). |
| `fetch` | `mcp-server-fetch` (uvx) | Fetch a URL → clean markdown for the model. |
| `memory` | `@modelcontextprotocol/server-memory` | Persistent knowledge-graph memory across chats. |
| `sequential-thinking` | `@modelcontextprotocol/server-sequential-thinking` | Structured step-by-step reasoning scratchpad. |
| `git` | `mcp-server-git` (uvx) | Rich git operations (status, diff, log, commit, branch). |
| `time` | `mcp-server-time` (uvx) | Current time / timezone conversion. |
| `context7` | `@upstash/context7-mcp` | **Live, version-accurate library docs** — huge for coding. |
| `playwright` | `@playwright/mcp` | Real browser automation: navigate, click, scrape, screenshot. |

> Why these matter for a *coding* agent: `context7` stops the model inventing
> outdated APIs, `playwright` lets it test web apps it writes, `git` + `filesystem`
> + `coding-tools` let it actually ship changes, and `memory` keeps context
> across sessions.

## Tier 3 — API key / OAuth servers (`config/optional-with-keys.json`)

| Server | Package | Requires | Use for |
| --- | --- | --- | --- |
| `github` | `@modelcontextprotocol/server-github` | Personal access token | Repos, issues, PRs, code search, releases |
| `github-watch` | local (this repo) | Same GitHub token | **Hook-like state awareness**: watch PRs/issues/repos, poll for CI/Actions/review/merge changes |
| `google-workspace` | `workspace-mcp` (uvx) | Google Cloud OAuth client | **Gmail, Calendar, Drive, Docs, Sheets, Slides** |
| `slack` | `@modelcontextprotocol/server-slack` | Bot token + team ID | Read/post Slack |
| `brave-search` | `@modelcontextprotocol/server-brave-search` | Brave API key (free) | Higher-quality web search |
| `firecrawl` | `firecrawl-mcp` | Firecrawl key | Robust web crawling → markdown |
| `postgres` | `@modelcontextprotocol/server-postgres` | Connection string | Query/inspect Postgres |
| `sqlite` | `mcp-server-sqlite` (uvx) | DB file path | Query local SQLite |
| `puppeteer` | `@modelcontextprotocol/server-puppeteer` | (none) | Alt browser automation |
| `sentry` | `mcp-server-sentry` (uvx) | Auth token | Inspect error/issue data |
| `think-delegate` | local (this repo) | Anthropic or OpenAI API key | **Local SLM → cloud expert**: `deep_think`, `latest_knowledge` |

---

## Think-delegate — local SLM calls a cloud expert on demand

For day-to-day work you use a **small local model** in LM Studio. When something
needs ultra reasoning or knowledge after your cutoff, the **local model** calls
`think-delegate` — it does not replace your chat model.

```
You: "Fix this race condition — use deep_think if you're stuck"
Local SLM → deep_think(task, context, ultra=true)
         → Anthropic API (Sonnet/Opus)
         ← expert analysis
Local SLM → coding-tools / git → implements the fix
```

Install (Claude Code CLI + subscription login — **no API key**):

```bash
# One-time: install CLI and log in with your Claude subscription
claude auth login

uv run python scripts/install_to_lmstudio.py --only think-delegate
```

Toggle `think-delegate` on in LM Studio. Paste `config/lmstudio-system-prompt.md`
so the local model knows when to delegate.

| Tool | When to call |
| --- | --- |
| `deep_think` | Architecture, subtle bugs, security, complex design (`ultra=true` → Opus) |
| `latest_knowledge` | Recent APIs, versions, current facts (optional web search first) |
| `delegate_status` | Check CLI + config |

Env vars (in `~/.lmstudio/mcp.json`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `THINK_PROVIDER` | `claude-cli` | `claude-cli` (subscription) or `anthropic` / `openai` (API billing) |
| `THINK_MODEL` | `sonnet` | Standard escalation (CLI alias or full model id) |
| `THINK_DEEP_MODEL` | `opus` | `ultra=true` tier |
| `THINK_USE_SUBSCRIPTION` | `1` | Strips `ANTHROPIC_API_KEY` so CLI uses subscription, not API |
| `CLAUDE_CLI` | auto | Path to `claude` binary if not on PATH |
| `CLAUDE_CLI_TIMEOUT` | `300` | Max seconds per delegation |

**Do not set `ANTHROPIC_API_KEY`** if you want subscription pricing — the API key
forces pay-per-token billing even when the CLI is installed.

Example prompts you can type:

- *"Use deep_think on this deadlock — include the stack trace in context."*
- *"I need latest knowledge on FastMCP 2.x breaking changes."*
- *"Escalate to expert: review this auth design for OWASP gaps."*

---

## "Hooks" — keeping the model in sync with GitHub (`github-watch`)

MCP is pull-based, so true push webhooks can't reach the model directly. The
`github-watch` server gives equivalent awareness by caching state and reporting
*deltas*:

```
gh_watch("priyansh19/myrepo#12")    # track a PR
gh_watch("priyansh19/myrepo")       # track repo Actions + activity
gh_poll()                           # -> "PR #12: CI 3 ok / 1 failing (test-e2e); review: changes_requested"
```

On-demand (no watching needed): `gh_pr_status`, `gh_issue_status`,
`gh_workflow_runs`, `gh_repo_activity`.

To make it *feel* like real-time hooks, have the agent call `gh_poll()` on a
loop (e.g. via the `/loop` skill, or a cron that prompts the agent). Each poll
only surfaces what changed since the last one. State is cached in
`~/.lmstudio-agent/github_watch_state.json`.

> Want genuine push events (GitHub → your machine instantly)? That needs a
> public endpoint; the usual local trick is a `smee.io` relay forwarding repo
> webhooks to a tiny local receiver that appends events to a file the agent
> reads. Ask and I'll add that bridge.

## Google Workspace (Gmail + Calendar + Drive + Docs + Sheets) — setup

This is the most powerful SaaS connector and the one you asked about. It uses
the maintained `workspace-mcp` server. ~5 minutes:

1. Go to <https://console.cloud.google.com/> → create (or pick) a project.
2. **APIs & Services → Enable APIs**: enable Gmail API, Google Calendar API,
   Google Drive API, Google Docs API, Google Sheets API (enable what you need).
3. **APIs & Services → OAuth consent screen**: choose *External*, add yourself
   as a *Test user* (your Gmail address). No app verification needed for testing.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Application type: Desktop app**. Copy the **Client ID** and **Client secret**.
5. Paste them into `config/optional-with-keys.json` under `google-workspace`
   (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `USER_GOOGLE_EMAIL`).
6. Install it:

   ```bash
   uv run python scripts/install_to_lmstudio.py --include-keys --only google-workspace
   ```

7. First time the model uses a Google tool, a browser window opens for you to
   authorize. Tokens are cached after that.

Adjust which apps are exposed with the `--tools` list in the config
(e.g. `gmail calendar drive docs sheets slides forms chat`).

---

## GitHub — connect, commit & push (one command)

There are two connections, both set up by one token:

- **`git push`** from cloned repos → token stored in the macOS keychain.
- **GitHub API** (create repos, open PRs, manage issues) → the `github` MCP server.

Steps:

1. Create a token at <https://github.com/settings/tokens>:
   - **Classic**: scopes `repo`, `workflow`, `read:org`, or
   - **Fine-grained**: `Contents`, `Pull requests`, `Issues` = Read/Write.
2. Run the setup script (it verifies the token, sets your git identity, stores
   the credential for pushes, and installs the `github` MCP server):

   ```bash
   GITHUB_TOKEN=ghp_xxx ./scripts/setup_github.sh "Your Name" "you@example.com"
   ```

3. Restart LM Studio and toggle `github` on.

Now the typical agent loop works end to end:

```
clone repo  ->  agent edits files (coding-tools)  ->  git_commit  ->  git push
                                  └─ or, with no local clone, the github MCP
                                     server pushes/opens a PR via the API
```

Your token is injected from the environment at install time, so it is never
written into the repo's JSON files (it lands only in ~/.lmstudio/mcp.json).

---

## Adding more servers yourself

Find any MCP server (e.g. on the official list at
`github.com/modelcontextprotocol/servers` or community "awesome-mcp-servers"
lists). Most are one line:

```json
"some-server": { "command": "npx", "args": ["-y", "<package>"], "env": {} }
```

Add it to `config/optional-with-keys.json`, then re-run the installer with
`--only some-server`.

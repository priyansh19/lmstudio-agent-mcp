#!/usr/bin/env bash
#
# bootstrap.sh — Single setup script for the LM Studio local agent stack.
#
# Run this on a fresh Mac to reproduce the entire environment:
#   prerequisites → Python deps → MCP servers → GitHub → OpenClaw → auto-start bridge
#
# Usage:
#   ./bootstrap.sh                 # interactive (recommended first time)
#   ./bootstrap.sh --yes           # accept all recommended defaults, skip optional prompts
#   ./bootstrap.sh --deps-only      # only prerequisites + Python deps
#   ./bootstrap.sh --help
#
# Non-interactive secrets (optional):
#   GITHUB_TOKEN=ghp_xxx GIT_NAME="you" GIT_EMAIL=you@mail.com ./bootstrap.sh --yes
#   SANDBOX=/path/to/workspace ./bootstrap.sh --yes
#
# Re-run anytime to refresh configs or rotate credentials. Idempotent.
#
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin:${PATH}"

# --------------------------------------------------------------------------- #
# Flags
# --------------------------------------------------------------------------- #
OPT_YES=false
OPT_MINIMAL=false
OPT_DEPS_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --yes|-y) OPT_YES=true ;;
    --minimal) OPT_MINIMAL=true ;;
    --deps-only) OPT_DEPS_ONLY=true ;;
    --help|-h)
      sed -n '2,22p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

# --------------------------------------------------------------------------- #
# UI helpers
# --------------------------------------------------------------------------- #
bold() { printf "\033[1m%s\033[0m\n" "$1"; }
info() { printf "  %s\n" "$1"; }
ok()   { printf "  ✓ %s\n" "$1"; }
hr()   { printf "\n%s\n" "════════════════════════════════════════════════════════════"; }

ask() {
  local prompt="$1" default="${2:-}" reply
  if $OPT_YES && [ -n "$default" ]; then echo "$default"; return; fi
  if [ -n "$default" ]; then
    read -r -p "$prompt [$default]: " reply </dev/tty || true
    echo "${reply:-$default}"
  else
    read -r -p "$prompt: " reply </dev/tty || true
    echo "$reply"
  fi
}
ask_secret() {
  local prompt="$1" reply
  if $OPT_YES; then echo ""; return; fi
  read -r -s -p "$prompt: " reply </dev/tty || true
  printf "\n" >&2
  echo "$reply"
}
confirm() {
  local prompt="$1" reply
  if $OPT_YES; then return 0; fi
  read -r -p "$prompt [y/N]: " reply </dev/tty || true
  [[ "$reply" =~ ^[Yy] ]]
}

step() { hr; bold "STEP $1 — $2"; }

# --------------------------------------------------------------------------- #
# STEP 1 — Prerequisites
# --------------------------------------------------------------------------- #
step_prereqs() {
  step 1 "Prerequisites (Homebrew, uv, Node, LM Studio CLI)"
  [[ "$(uname)" == "Darwin" ]] || info "Note: optimized for macOS."

  if ! command -v brew >/dev/null 2>&1; then
    if $OPT_YES || confirm "Install Homebrew?"; then
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || true)"
    fi
  fi
  command -v brew >/dev/null 2>&1 && ok "Homebrew: $(brew --version | head -1)"

  if ! command -v uv >/dev/null 2>&1; then
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  ok "uv: $(uv --version)"

  if ! command -v npx >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
      brew install node
    else
      echo "ERROR: npx not found. Install Node.js, then re-run." >&2
      exit 1
    fi
  fi
  ok "node: $(node --version)"

  if ! command -v lms >/dev/null 2>&1; then
    npx -y lmstudio install-cli 2>/dev/null || info "Install LM Studio app, then: npx lmstudio install-cli"
  fi
  command -v lms >/dev/null 2>&1 && ok "lms CLI present" || info "lms not on PATH yet (open LM Studio once)"
}

# --------------------------------------------------------------------------- #
# STEP 1b — macOS /tmp (LM Studio model load requires writable /tmp)
# --------------------------------------------------------------------------- #
step_macos_tmp() {
  [[ "$(uname)" == "Darwin" ]] || return 0
  step "1b" "macOS /tmp permissions (LM Studio model loading)"
  if bash "$REPO/scripts/fix_macos_tmp.sh" 2>/dev/null; then
    ok "/tmp writable"
    return 0
  fi
  info "/tmp is not writable — LM Studio may fail with PermissionError on model load"
  if $OPT_YES || confirm "Attempt to repair /private/tmp now (requires sudo)?"; then
    if bash "$REPO/scripts/fix_macos_tmp.sh" --fix; then
      ok "/tmp repaired"
    else
      info "Manual fix: ./scripts/fix_macos_tmp.sh --fix  (see SETUP.md if sudo fails)"
    fi
  else
    info "Skipped — run later: ./scripts/fix_macos_tmp.sh --fix"
  fi
}

# --------------------------------------------------------------------------- #
# STEP 2 — Python dependencies
# --------------------------------------------------------------------------- #
step_python() {
  step 2 "Python dependencies"
  uv sync
  uv run python -c "import mcp, lmstudio; print('  mcp + lmstudio OK')"
  ok "Dependencies installed"
}

# --------------------------------------------------------------------------- #
# STEP 3 — Sandbox
# --------------------------------------------------------------------------- #
step_sandbox() {
  step 3 "Workspace sandbox"
  info "Directory the agent may read/write/run in."
  SANDBOX="${SANDBOX:-$(ask "Sandbox root" "$HOME/Desktop")}"
  SANDBOX="${SANDBOX/#\~/$HOME}"
  mkdir -p "$SANDBOX"
  export SANDBOX_ROOT="$SANDBOX"
  ok "Sandbox: $SANDBOX"
}

# --------------------------------------------------------------------------- #
# STEP 4 — Code intelligence + memory seed
# --------------------------------------------------------------------------- #
step_code_intel() {
  step 4 "Code intelligence (codebase-memory-mcp) + memory seed"
  if [ -x "${HOME}/.local/bin/codebase-memory-mcp" ]; then
    ok "codebase-memory-mcp: $("${HOME}/.local/bin/codebase-memory-mcp" --version 2>/dev/null || echo installed)"
  elif $OPT_YES || confirm "Install codebase-memory-mcp?"; then
    curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash
    export PATH="${HOME}/.local/bin:${PATH}"
    ok "codebase-memory-mcp installed"
  else
    info "Skipped codebase-memory-mcp"
  fi
  uv run python scripts/seed_memory.py 2>/dev/null && ok "Memory graph seeded" || true
  if [ -x "${HOME}/.local/bin/codebase-memory-mcp" ]; then
    "${HOME}/.local/bin/codebase-memory-mcp" cli index_repository \
      "{\"repo_path\":\"${REPO}\",\"name\":\"lmstudio-agent-mcp\"}" >/dev/null 2>&1 \
      && ok "Indexed this repo in codebase-memory" || info "Index skipped (LM Studio not required for this)"
  fi
}

# --------------------------------------------------------------------------- #
# STEP 5 — LM Studio MCP servers
# --------------------------------------------------------------------------- #
step_lmstudio_mcp() {
  step 5 "LM Studio MCP servers → ~/.lmstudio/mcp.json"
  info "Installs: coding-tools, web-tools, docker-tools, codebase-memory,"
  info "  memory, git, time, context7, playwright, think-delegate"
  info "Removes deprecated: filesystem, fetch"
  uv run python scripts/install_to_lmstudio.py --sandbox "$SANDBOX"
  ok "LM Studio MCP config updated (backup saved)"
}

# --------------------------------------------------------------------------- #
# STEP 5b — think-delegate (Claude CLI escalation for local SLMs)
# --------------------------------------------------------------------------- #
step_think_delegate() {
  step "5b" "think-delegate (local SLM → Claude CLI subscription)"
  info "Escalate hard reasoning via deep_think / latest_knowledge — no API key."
  if $OPT_YES || confirm "Install think-delegate + verify Claude CLI?"; then
    SANDBOX="$SANDBOX" bash "$REPO/scripts/setup_think_delegate.sh" || info "think-delegate setup had warnings"
    ok "think-delegate configured"
  else
    info "Skipped — run later: ./scripts/setup_think_delegate.sh"
  fi
}

# --------------------------------------------------------------------------- #
# STEP 6 — GitHub (optional)
# --------------------------------------------------------------------------- #
step_github() {
  $OPT_MINIMAL && return 0
  step 6 "GitHub (optional — commit/push + github + github-watch MCP)"
  local token="${GITHUB_TOKEN:-${GITHUB_PERSONAL_ACCESS_TOKEN:-}}"
  if [ -z "$token" ]; then
    $OPT_YES && return 0
    confirm "Set up GitHub?" || return 0
    token="$(ask_secret "GitHub token (ghp_... ; https://github.com/settings/tokens)")"
  fi
  [ -z "$token" ] && { info "Skipped GitHub"; return 0; }
  local name="${GIT_NAME:-$(ask "Git author name" "$(git config --global user.name 2>/dev/null || echo "")")}"
  local email="${GIT_EMAIL:-$(ask "Git author email" "$(git config --global user.email 2>/dev/null || echo "")")}"
  GITHUB_TOKEN="$token" ./scripts/setup_github.sh "$name" "$email"
  GITHUB_PERSONAL_ACCESS_TOKEN="$token" \
    uv run python scripts/install_to_lmstudio.py --include-keys --only github-watch --sandbox "$SANDBOX"
  ok "GitHub configured"
}

# --------------------------------------------------------------------------- #
# STEP 7 — Other connectors (optional)
# --------------------------------------------------------------------------- #
step_optional_connectors() {
  $OPT_MINIMAL && return 0
  step 7 "Other optional connectors"
  if confirm "Google Workspace (Gmail/Calendar/Drive)?"; then
    local gid gsec gemail
    gid="$(ask "GOOGLE_OAUTH_CLIENT_ID")"
    gsec="$(ask_secret "GOOGLE_OAUTH_CLIENT_SECRET")"
    gemail="$(ask "Google account email")"
    if [ -n "$gid" ] && [ -n "$gsec" ]; then
      GOOGLE_OAUTH_CLIENT_ID="$gid" GOOGLE_OAUTH_CLIENT_SECRET="$gsec" USER_GOOGLE_EMAIL="$gemail" \
        uv run python scripts/install_to_lmstudio.py --include-keys --only google-workspace --sandbox "$SANDBOX"
      ok "Google Workspace MCP added"
    fi
  fi
  if confirm "Brave Search?"; then
    local k; k="$(ask_secret "BRAVE_API_KEY")"
    [ -n "$k" ] && BRAVE_API_KEY="$k" uv run python scripts/install_to_lmstudio.py --include-keys --only brave-search --sandbox "$SANDBOX"
  fi
  if confirm "Firecrawl?"; then
    local k; k="$(ask_secret "FIRECRAWL_API_KEY")"
    [ -n "$k" ] && FIRECRAWL_API_KEY="$k" uv run python scripts/install_to_lmstudio.py --include-keys --only firecrawl --sandbox "$SANDBOX"
  fi
  if confirm "Slack?"; then
    local tok team; tok="$(ask_secret "SLACK_BOT_TOKEN")"; team="$(ask "SLACK_TEAM_ID")"
    [ -n "$tok" ] && SLACK_BOT_TOKEN="$tok" SLACK_TEAM_ID="$team" \
      uv run python scripts/install_to_lmstudio.py --include-keys --only slack --sandbox "$SANDBOX"
  fi
}

# --------------------------------------------------------------------------- #
# STEP 8 — OpenClaw → LM Studio bridge
# --------------------------------------------------------------------------- #
step_openclaw() {
  step 8 "OpenClaw → stable LM Studio bridge"
  if ! command -v openclaw >/dev/null 2>&1; then
    info "OpenClaw not installed — skip (install from openclaw.ai if needed)"
    return 0
  fi
  if $OPT_YES || confirm "Configure OpenClaw (model: local-agent/local/current + MCP sync)?"; then
    uv run python scripts/setup_openclaw_lmstudio.py --with-mcp
    ok "OpenClaw configured"
    info "Restart gateway: openclaw gateway restart"
  fi
}

# --------------------------------------------------------------------------- #
# STEP 9 — Auto-start bridge on login
# --------------------------------------------------------------------------- #
step_launchagent() {
  step 9 "Auto-start bridge on Mac login (LaunchAgent)"
  info "Bridge: http://127.0.0.1:8765/v1  model: local/current"
  if $OPT_YES || confirm "Install LaunchAgent (recommended)?"; then
    bash scripts/install_bridge_launchagent.sh
    ok "Bridge will start on every login"
  else
    info "Start manually: uv run python agent/lmstudio_bridge.py"
  fi
}

# --------------------------------------------------------------------------- #
# Done
# --------------------------------------------------------------------------- #
print_finish() {
  hr
  bold "SETUP COMPLETE"
  echo
  info "What you have now:"
  info "  • LM Studio MCP tools     → ~/.lmstudio/mcp.json (incl. think-delegate)"
  info "  • Claude escalation       → deep_think via Claude CLI subscription"
  info "  • OpenClaw (if configured) → local-agent/local/current (swap models in LM Studio only)"
  info "  • Bridge auto-start       → ~/Library/LaunchAgents/com.lmstudio-agent.bridge.plist"
  info "  • Sandbox                 → $SANDBOX"
  echo
  bold "Every time you use it:"
  info "  1. LM Studio:  lms server start  &&  lms load   (pick any model)"
  info "  2. LM Studio:  paste config/lmstudio-system-prompt.md into Chat → System Prompt"
  info "  3. LM Studio:  toggle MCP servers on (Program → mcp.json)"
  info "  4. OpenClaw:   message yourself — uses whatever model LM Studio has loaded"
  echo
  bold "Useful commands:"
  info "  curl http://127.0.0.1:8765/health"
  info "  uv run python agent/local_agent.py --root \"$SANDBOX\""
  info "  tail -f $REPO/.bridge.log"
  echo
  info "Re-run ./bootstrap.sh anytime to refresh or rotate credentials."
}

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
main() {
  hr
  bold "LM Studio Local Agent — bootstrap"
  info "Repo: $REPO"
  $OPT_YES && info "Mode: --yes (recommended defaults)"
  $OPT_MINIMAL && info "Mode: --minimal (skip optional connectors)"

  step_prereqs
  step_macos_tmp
  step_python
  $OPT_DEPS_ONLY && { ok "Deps-only mode — done."; exit 0; }
  step_sandbox
  step_code_intel
  step_lmstudio_mcp
  step_think_delegate
  step_github
  step_optional_connectors
  step_openclaw
  step_launchagent
  print_finish
}

main "$@"

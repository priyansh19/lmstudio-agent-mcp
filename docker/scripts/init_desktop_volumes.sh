#!/usr/bin/env bash
#
# init_desktop_volumes.sh — Create Desktop bind-mount dirs for Docker stack.
#
# Creates:
#   ~/Desktop/lmstudio-agent/
#     memory/vector/   → semantic + episodic SQLite (.vector-memory.db)
#     memory/graph/    → knowledge-graph JSON
#     memory/skills/   → procedural Skill.md files
#     workspace/       → agent coding sandbox
#     backup/          → local git clone synced to private GitHub repo
#
# Usage:
#   ./docker/scripts/init_desktop_volumes.sh
#   LMSTUDIO_AGENT_DATA_ROOT=/path ./docker/scripts/init_desktop_volumes.sh
#
set -euo pipefail

ROOT="${LMSTUDIO_AGENT_DATA_ROOT:-${HOME}/Desktop/lmstudio-agent}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  ✓ %s\n" "$1"; }
info() { printf "  → %s\n" "$1"; }

bold "Creating LM Studio agent data on Desktop"

mkdir -p \
  "$ROOT/memory/vector" \
  "$ROOT/memory/graph" \
  "$ROOT/memory/skills" \
  "$ROOT/workspace" \
  "$ROOT/backup"

# Placeholder files so bind mounts work before first agent run
touch "$ROOT/memory/vector/vector-memory.db"
touch "$ROOT/memory/graph/agent-memory.json"

# Seed procedural skill from repo if missing
SKILL_SRC="$REPO_ROOT/lmstudio/skills/Skill.md"
if [ -f "$SKILL_SRC" ] && [ ! -f "$ROOT/memory/skills/Skill.md" ]; then
  cp "$SKILL_SRC" "$ROOT/memory/skills/Skill.md"
  ok "Copied Skill.md into memory/skills/"
fi

# Init local backup git repo if empty
if [ ! -d "$ROOT/backup/.git" ]; then
  git -C "$ROOT/backup" init -b main
  cp "$REPO_ROOT/docker/memory-backup/gitignore.template" "$ROOT/backup/.gitignore"
  mkdir -p "$ROOT/backup/vector" "$ROOT/backup/graph" "$ROOT/backup/skills"
  git -C "$ROOT/backup" add -A
  git -C "$ROOT/backup" commit -m "Initial memory backup scaffold" --allow-empty
  ok "Initialized backup git repo at $ROOT/backup"
fi

ok "Data root: $ROOT"
info "  memory/vector/vector-memory.db"
info "  memory/graph/agent-memory.json"
info "  memory/skills/"
info "  workspace/"
info "  backup/  (private GitHub sync target)"

ENV_FILE="$REPO_ROOT/docker/.env"
ENV_EXAMPLE="$REPO_ROOT/docker/.env.example"
if [ ! -f "$ENV_FILE" ] && [ -f "$ENV_EXAMPLE" ]; then
  sed "s|^LMSTUDIO_AGENT_DATA_ROOT=.*|LMSTUDIO_AGENT_DATA_ROOT=$ROOT|" "$ENV_EXAMPLE" > "$ENV_FILE"
  ok "Created docker/.env with LMSTUDIO_AGENT_DATA_ROOT=$ROOT"
fi

echo
info "Next: edit docker/.env and set MEMORY_BACKUP_GIT_REMOTE to your private repo"
info "Then: docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --build"

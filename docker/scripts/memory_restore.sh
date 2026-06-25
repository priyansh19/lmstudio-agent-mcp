#!/usr/bin/env bash
#
# memory_restore.sh — Restore agent memories from a private GitHub backup repo.
#
# Clones (or pulls) the backup repo and copies vector DB, graph memory, and
# skills back into Desktop bind mounts. Use after machine loss or fresh setup.
#
# Usage:
#   ./docker/scripts/memory_restore.sh git@github.com:you/lmstudio-agent-memory.git
#   MEMORY_BACKUP_GIT_REMOTE=... ./docker/scripts/memory_restore.sh
#
set -euo pipefail

REMOTE="${1:-${MEMORY_BACKUP_GIT_REMOTE:-}}"
BRANCH="${MEMORY_BACKUP_GIT_BRANCH:-main}"
ROOT="${LMSTUDIO_AGENT_DATA_ROOT:-${HOME}/Desktop/lmstudio-agent}"

if [ -z "$REMOTE" ]; then
  echo "Usage: $0 <git-remote-url>" >&2
  echo "  or set MEMORY_BACKUP_GIT_REMOTE" >&2
  exit 1
fi

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  ✓ %s\n" "$1"; }

bold "Restoring LM Studio agent memory from $REMOTE"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LMSTUDIO_AGENT_DATA_ROOT="$ROOT" bash "$SCRIPT_DIR/init_desktop_volumes.sh"

CLONE_DIR="$ROOT/.restore-tmp"
rm -rf "$CLONE_DIR"
git clone --depth 1 -b "$BRANCH" "$REMOTE" "$CLONE_DIR"

rsync -a "$CLONE_DIR/vector/" "$ROOT/memory/vector/"
rsync -a "$CLONE_DIR/graph/" "$ROOT/memory/graph/"
rsync -a "$CLONE_DIR/skills/" "$ROOT/memory/skills/"

# Refresh local backup mirror
rsync -a "$CLONE_DIR/" "$ROOT/backup/" --exclude .git
if [ -d "$ROOT/backup/.git" ]; then
  git -C "$ROOT/backup" add -A
  git -C "$ROOT/backup" commit -m "Restored from $REMOTE $(date -Iseconds)" || true
fi

rm -rf "$CLONE_DIR"

ok "Restored into $ROOT"
ok "  vector-memory.db → memory/vector/"
ok "  agent-memory.json → memory/graph/"
ok "  skills → memory/skills/"
echo
echo "Restart containers: docker compose -f docker/docker-compose.yml --env-file docker/.env restart"

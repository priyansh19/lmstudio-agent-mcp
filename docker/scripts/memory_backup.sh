#!/usr/bin/env bash
#
# memory_backup.sh — One-shot push of Desktop memory files to private GitHub repo.
# The memory-backup container does this automatically; use this for manual sync.
#
set -euo pipefail

ROOT="${LMSTUDIO_AGENT_DATA_ROOT:-${HOME}/Desktop/lmstudio-agent}"
REMOTE="${MEMORY_BACKUP_GIT_REMOTE:-}"
BRANCH="${MEMORY_BACKUP_GIT_BRANCH:-main}"

if [ -z "$REMOTE" ]; then
  echo "Set MEMORY_BACKUP_GIT_REMOTE in docker/.env" >&2
  exit 1
fi

mkdir -p "$ROOT/backup/vector" "$ROOT/backup/graph" "$ROOT/backup/skills"
rsync -a "$ROOT/memory/vector/" "$ROOT/backup/vector/"
rsync -a "$ROOT/memory/graph/" "$ROOT/backup/graph/"
rsync -a "$ROOT/memory/skills/" "$ROOT/backup/skills/"

if [ ! -d "$ROOT/backup/.git" ]; then
  git -C "$ROOT/backup" init -b main
  git -C "$ROOT/backup" remote add origin "$REMOTE"
fi

git -C "$ROOT/backup" add -A
git -C "$ROOT/backup" diff --cached --quiet && { echo "No changes"; exit 0; }
git -C "$ROOT/backup" commit -m "Manual memory backup $(date -Iseconds)"
git -C "$ROOT/backup" push origin "$BRANCH"
echo "Pushed to $REMOTE"

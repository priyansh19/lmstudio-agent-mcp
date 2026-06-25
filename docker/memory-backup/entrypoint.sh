#!/usr/bin/env bash
set -euo pipefail

INTERVAL="${BACKUP_INTERVAL_SEC:-300}"
REMOTE="${GIT_REMOTE:-}"
BRANCH="${GIT_BRANCH:-main}"
NAME="${GIT_USER_NAME:-lmstudio-agent}"
EMAIL="${GIT_USER_EMAIL:-agent@local}"

git config --global user.name "$NAME"
git config --global user.email "$EMAIL"
git config --global init.defaultBranch main

init_repo() {
  mkdir -p /repo
  if [ ! -d /repo/.git ]; then
    echo "Initializing backup repo at /repo"
    git -C /repo init
    cp /templates/.gitignore /repo/.gitignore 2>/dev/null || true
    git -C /repo add -A
    git -C /repo commit -m "Initial memory backup scaffold" --allow-empty || true
    if [ -n "$REMOTE" ]; then
      git -C /repo remote add origin "$REMOTE" 2>/dev/null || \
        git -C /repo remote set-url origin "$REMOTE"
      git -C /repo push -u origin "$BRANCH" || echo "First push failed — set MEMORY_BACKUP_GIT_REMOTE and retry"
    fi
  elif [ -n "$REMOTE" ]; then
    git -C /repo remote add origin "$REMOTE" 2>/dev/null || \
      git -C /repo remote set-url origin "$REMOTE"
  fi
}

sync_once() {
  mkdir -p /repo/vector /repo/graph /repo/skills
  rsync -a --delete /source/vector/ /repo/vector/
  rsync -a --delete /source/graph/ /repo/graph/
  rsync -a --delete /source/skills/ /repo/skills/

  if [ -f /repo/vector/vector-memory.db ] && [ ! -s /repo/vector/vector-memory.db ]; then
    : # empty placeholder is fine before first agent run
  fi

  git -C /repo add -A
  if git -C /repo diff --cached --quiet; then
    echo "$(date -Iseconds) — no memory changes"
    return 0
  fi

  git -C /repo commit -m "Memory backup $(date -Iseconds)"
  if [ -n "$REMOTE" ]; then
    git -C /repo push origin "$BRANCH" && \
      echo "$(date -Iseconds) — pushed to $REMOTE"
  else
    echo "$(date -Iseconds) — committed locally (set MEMORY_BACKUP_GIT_REMOTE to push)"
  fi
}

init_repo

if [ -n "$REMOTE" ] && [ -d /repo/.git ]; then
  git -C /repo pull --rebase origin "$BRANCH" 2>/dev/null || true
fi

echo "Memory backup loop every ${INTERVAL}s"
while true; do
  sync_once || echo "Backup sync failed — will retry"
  sleep "$INTERVAL"
done

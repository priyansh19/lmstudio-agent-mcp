#!/usr/bin/env bash
set -euo pipefail

# Ensure memory and workspace dirs exist (bind mounts may be empty on first run).
mkdir -p \
  "$(dirname "${VECTOR_MEMORY_DB}")" \
  "$(dirname "${MEMORY_FILE_PATH}")" \
  "${SKILLS_DIR}" \
  "${WORKSPACE_ROOTS}"

cd /app/lmstudio

case "${1:-bridge}" in
  bridge)
    exec uv run python agent/lmstudio_bridge.py \
      --port "${BRIDGE_PORT}" \
      --lmstudio "${LMSTUDIO_URL}"
    ;;
  agent)
    shift
    exec uv run python agent/local_agent.py --root "${WORKSPACE_ROOTS}" "$@"
    ;;
  agent-task)
    shift
    exec uv run python agent/local_agent.py --root "${WORKSPACE_ROOTS}" --task "$*"
    ;;
  mcp)
    shift
    server="${1:?usage: mcp <server-name>}"
    exec uv run python "servers/${server}.py" --root "${WORKSPACE_ROOTS}"
    ;;
  shell)
    exec bash
    ;;
  *)
    exec "$@"
    ;;
esac

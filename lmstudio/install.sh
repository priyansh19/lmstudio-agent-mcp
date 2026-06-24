#!/usr/bin/env bash
# Backward-compatible alias — use bootstrap.sh directly.
exec "$(dirname "$0")/bootstrap.sh" "$@"

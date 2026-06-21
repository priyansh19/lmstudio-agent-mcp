#!/usr/bin/env bash
# Refresh Python dependencies only.
exec "$(dirname "$0")/bootstrap.sh" --deps-only "$@"

#!/usr/bin/env bash
#
# fix_macos_tmp.sh — Repair /private/tmp permissions on macOS.
#
# LM Studio (and many Python tools) write temp files under /tmp when loading
# models. If /private/tmp is locked down (drwx------), you get:
#   PermissionError: [Errno 13] Permission denied: '/tmp/tmpXXXXXX'
#
# Usage:
#   ./scripts/fix_macos_tmp.sh          # check only
#   ./scripts/fix_macos_tmp.sh --fix    # attempt repair (may prompt for sudo)
#
set -euo pipefail

OPT_FIX=false
for arg in "$@"; do
  case "$arg" in
    --fix|-f) OPT_FIX=true ;;
    --help|-h)
      sed -n '2,12p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

if [[ "$(uname)" != "Darwin" ]]; then
  echo "Not macOS — skipping /tmp check."
  exit 0
fi

_test_tmp() {
  local probe="/tmp/.lmstudio-agent-write-test-$$"
  if touch "$probe" 2>/dev/null; then
    rm -f "$probe"
    return 0
  fi
  return 1
}

_show_perms() {
  if ls -ld /private/tmp >/dev/null 2>&1; then
    ls -ld /private/tmp
  else
    echo "  /private/tmp: not readable (likely wrong permissions)"
  fi
}

if _test_tmp; then
  echo "OK: /tmp is writable."
  exit 0
fi

echo "WARNING: /tmp is NOT writable."
echo "  LM Studio may fail to load models with:"
echo "  PermissionError: [Errno 13] Permission denied: '/tmp/tmp...'"
echo
echo "Current permissions:"
_show_perms
echo
echo "Expected: drwxrwxrwt  root  wheel  /private/tmp"

if ! $OPT_FIX; then
  echo
  echo "Run with --fix to attempt repair:"
  echo "  ./scripts/fix_macos_tmp.sh --fix"
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "ERROR: sudo not found — fix manually as admin:" >&2
  echo "  sudo chmod 1777 /private/tmp && sudo chown root:wheel /private/tmp" >&2
  exit 1
fi

echo
echo "Attempting repair (you may be prompted for your Mac password)..."
sudo chflags -R norestricted /private/tmp 2>/dev/null || true
if ! sudo chmod 1777 /private/tmp; then
  echo "ERROR: chmod failed. You may need Recovery Mode — see SETUP.md troubleshooting." >&2
  exit 1
fi
sudo chown root:wheel /private/tmp 2>/dev/null || true

if _test_tmp; then
  echo "OK: /tmp repaired and writable."
  ls -ld /private/tmp
  exit 0
fi

echo "ERROR: /tmp still not writable after repair." >&2
echo "See SETUP.md → Troubleshooting → /tmp Permission denied" >&2
exit 1

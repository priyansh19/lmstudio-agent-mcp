#!/usr/bin/env bash
#
# setup_think_delegate.sh — Install think-delegate MCP + verify Claude Code CLI.
#
# Uses Claude Code subscription (claude auth login), NOT Anthropic API keys.
#
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
export PATH="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin:${PATH}"

SANDBOX="${SANDBOX:-${SANDBOX_ROOT:-$HOME/Desktop}}"

echo "Installing think-delegate → ~/.lmstudio/mcp.json"
uv run python scripts/install_to_lmstudio.py --only think-delegate --sandbox "$SANDBOX"

if ! command -v claude >/dev/null 2>&1; then
  echo
  echo "Claude Code CLI not found."
  echo "  Install: https://code.claude.com/docs/en/setup"
  echo "  Then run: claude auth login"
  exit 0
fi

echo "Claude CLI: $(command -v claude) ($(claude --version 2>/dev/null || echo unknown))"

if claude auth status --text 2>/dev/null | grep -qi "logged in"; then
  echo "OK: Claude subscription auth active."
elif claude auth status 2>/dev/null; then
  echo "OK: Claude auth status returned 0."
else
  echo
  echo "Claude CLI is not logged in. Run once:"
  echo "  claude auth login"
  echo
  echo "Do NOT set ANTHROPIC_API_KEY on think-delegate — that forces API billing."
fi

echo
echo "Toggle think-delegate ON in LM Studio → Program → mcp.json"

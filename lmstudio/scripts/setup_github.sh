#!/usr/bin/env bash
# Connects your machine (and therefore your local LLM) to GitHub.
#
# Does three things with ONE token:
#   1. Sets your git commit identity (name/email).
#   2. Stores your token in the macOS keychain so `git push` works over HTTPS.
#   3. Installs the GitHub MCP server into LM Studio with the same token,
#      so the model can create repos, open PRs, manage issues, etc.
#
# Usage:
#   GITHUB_TOKEN=ghp_xxx ./scripts/setup_github.sh "Your Name" "you@example.com"
#
# Create a token at: https://github.com/settings/tokens
#   - Classic token: scopes  repo, workflow, read:org
#   - Or a fine-grained token with Contents + Pull requests + Issues (Read/Write)

set -euo pipefail
cd "$(dirname "$0")/.."

TOKEN="${GITHUB_TOKEN:-${GITHUB_PERSONAL_ACCESS_TOKEN:-}}"
NAME="${1:-}"
EMAIL="${2:-}"

if [ -z "$TOKEN" ]; then
  echo "ERROR: set your token first, e.g.:"
  echo "  GITHUB_TOKEN=ghp_xxx ./scripts/setup_github.sh \"Your Name\" \"you@example.com\""
  exit 1
fi

echo "==> Verifying token with GitHub..."
LOGIN=$(curl -fsS -H "Authorization: Bearer $TOKEN" https://api.github.com/user \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('login',''))" || true)
if [ -z "$LOGIN" ]; then
  echo "ERROR: token rejected by GitHub. Check it has not expired and has the right scopes."
  exit 1
fi
echo "    Authenticated as: $LOGIN"

# Default identity from the GitHub account if not provided.
if [ -z "$NAME" ]; then NAME="$LOGIN"; fi
if [ -z "$EMAIL" ]; then EMAIL="${LOGIN}@users.noreply.github.com"; fi

echo "==> Setting git identity: $NAME <$EMAIL>"
git config --global user.name "$NAME"
git config --global user.email "$EMAIL"

echo "==> Enabling macOS keychain credential helper"
git config --global credential.helper osxkeychain

echo "==> Storing token in keychain for github.com pushes"
printf "protocol=https\nhost=github.com\nusername=%s\npassword=%s\n\n" \
  "$LOGIN" "$TOKEN" | git credential approve

echo "==> Installing GitHub MCP server into LM Studio"
GITHUB_PERSONAL_ACCESS_TOKEN="$TOKEN" \
  uv run python scripts/install_to_lmstudio.py --include-keys --only github

cat <<EOF

Done. Your local LLM can now:
  - push to GitHub from cloned repos (git over HTTPS uses the keychain token)
  - use the 'github' MCP server in LM Studio for repos / PRs / issues

Test the push path:
  cd ~/Desktop && git clone https://github.com/$LOGIN/<some-repo>.git
  # let the agent edit + commit, then:  git push

Restart LM Studio (or Program -> mcp.json) and toggle 'github' on.
EOF

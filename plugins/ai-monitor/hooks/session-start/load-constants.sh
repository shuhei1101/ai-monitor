#!/usr/bin/env bash
#
# SessionStart フック: constants.env の静的定数 + 動的値（REPO_SLUG / WIKI_BASE）を
# CLAUDE_ENV_FILE 経由でセッション環境変数として展開する
#
# 注意: フックは子プロセスとして実行されるため、単なる export ではセッションに残らない。
# CLAUDE_ENV_FILE に `export KEY="value"` 形式で追記するのが公式の永続化手段。
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${PLUGIN_ROOT}/constants.env"

REPO_SLUG=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
WIKI_BASE="https://raw.githubusercontent.com/${REPO_SLUG}/master/docs/wiki"

if [ -z "${CLAUDE_ENV_FILE:-}" ]; then
  echo "load-constants.sh: CLAUDE_ENV_FILE が未設定のため定数を展開できません" >&2
  exit 1
fi

# コメント行・空行を除いた KEY="value" を export 付きで追記する
grep -Ev '^[[:space:]]*(#|$)' "$ENV_FILE" | sed 's/^/export /' >> "$CLAUDE_ENV_FILE"
{
  echo "export REPO_SLUG=\"${REPO_SLUG}\""
  echo "export WIKI_BASE=\"${WIKI_BASE}\""
} >> "$CLAUDE_ENV_FILE"

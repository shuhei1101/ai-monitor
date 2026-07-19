#!/usr/bin/env bash
#
# SessionStart フック: constants.env の静的定数と、settings.yaml から解決した
# セッション固有値（REPO_SLUG / WIKI_BASE）を CLAUDE_ENV_FILE 経由で
# セッション環境変数として展開する
#
# 注意: フックは子プロセスとして実行されるため、単なる export ではセッションに残らない。
# CLAUDE_ENV_FILE に `export KEY="value"` 形式で追記するのが公式の永続化手段。
#
# settings.yaml が無い・git remote が無い・対象プロジェクトが未登録の場合は、
# 警告を出して REPO_SLUG / WIKI_BASE の展開だけをスキップする
# （監視対象外のリポジトリでもセッション自体は開けるようにするため）。
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${PLUGIN_ROOT}/constants.env"
SETTINGS_FILE="${HOME}/.config/ai-monitor/settings.yaml"

if [ -z "${CLAUDE_ENV_FILE:-}" ]; then
  echo "load-constants.sh: CLAUDE_ENV_FILE が未設定のため定数を展開できません" >&2
  exit 1
fi

# コメント行・空行を除いた KEY="value" を export 付きで追記する
grep -Ev '^[[:space:]]*(#|$)' "$ENV_FILE" | sed 's/^/export /' >> "$CLAUDE_ENV_FILE"

skip() {
  echo "load-constants.sh: WARN: $1（REPO_SLUG / WIKI_BASE の展開をスキップ）" >&2
  exit 0
}

[ -f "$SETTINGS_FILE" ] || skip "settings.yaml がありません: ${SETTINGS_FILE}"

# CWD の git remote からリポジトリ（owner/name）を解決する
REMOTE_URL=$(git remote get-url origin 2>/dev/null) || skip "git remote (origin) がありません"
REPO_SLUG=$(echo "$REMOTE_URL" | sed -E 's#^(git@[^:]+:|ssh://[^/]+/|https?://[^/]+/)##; s#\.git$##')

# settings.yaml の projects[] から一致するプロジェクトの wiki_base を解決する
WIKI_BASE=$(python3 - "$SETTINGS_FILE" "$REPO_SLUG" <<'EOF'
import sys

import yaml

settings_path, repo_slug = sys.argv[1], sys.argv[2]
with open(settings_path, encoding="utf-8") as f:
    settings = yaml.safe_load(f)
projects = [p for p in settings["projects"] if p["repo"] == repo_slug]
if not projects:
    raise SystemExit(f"projects に {repo_slug} の定義がありません")
print(projects[0]["wiki_base"])
EOF
) || skip "settings.yaml から wiki_base を解決できません（repo=${REPO_SLUG}）"

{
  echo "export REPO_SLUG=\"${REPO_SLUG}\""
  echo "export WIKI_BASE=\"${WIKI_BASE}\""
} >> "$CLAUDE_ENV_FILE"

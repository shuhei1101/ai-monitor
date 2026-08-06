#!/usr/bin/env bash
#
# SessionStart フック: constants.env の静的定数と、settings.yaml から解決した
# セッション固有値（REPO_SLUG / WIKI_BASE / AI_MONITOR_WIKI_BASE）を CLAUDE_ENV_FILE 経由で
# セッション環境変数として展開する
#
# 注意: フックは子プロセスとして実行されるため、単なる export ではセッションに残らない。
# CLAUDE_ENV_FILE に `export KEY="value"` 形式で追記するのが公式の永続化手段。
#
# settings.yaml が無い・git remote が無い・対象プロジェクトが未登録の場合は、
# REPO_SLUG / WIKI_BASE / AI_MONITOR_WIKI_BASE の展開だけをスキップする
# （監視対象外のリポジトリでもセッション自体は開けるようにするため）。
#
# 解決結果は stdout に出す。SessionStart フックの stdout はセッションのコンテキストへ
# 注入されるため、登録漏れに気づかないまま Wiki 参照なしで動く事故を防げる。
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${PLUGIN_ROOT}/constants.env"
CONFIG_DIR="${HOME}/.config/ai-monitor"
SETTINGS_FILE="${CONFIG_DIR}/settings.yaml"
# 環境差分 yaml（`AI_MONITOR_ENV` が指す）を共通 yaml より優先して見る。
# モニター本体（`shared/settings.py`）と同じ優先順にしないと、
# sandbox のように環境差分側にしか登録が無いプロジェクトを解決できない。
ENV_SETTINGS_FILE=""
if [ -n "${AI_MONITOR_ENV:-}" ]; then
  ENV_SETTINGS_FILE="${CONFIG_DIR}/settings.${AI_MONITOR_ENV}.yaml"
fi

if [ -z "${CLAUDE_ENV_FILE:-}" ]; then
  echo "load-constants.sh: CLAUDE_ENV_FILE が未設定のため定数を展開できません" >&2
  exit 1
fi

# コメント行・空行を除いた KEY="value" を export 付きで追記する
grep -Ev '^[[:space:]]*(#|$)' "$ENV_FILE" | sed 's/^/export /' >> "$CLAUDE_ENV_FILE"

skip() {
  # 解決できなかったときは 3 つとも空に倒す。
  # 親プロセスから継承した値が残ると、別リポジトリを指したまま「実在しそうな値」として
  # URL の組み立てなどに使われ、実際に開くまで誤りに気づけない。
  {
    echo 'export REPO_SLUG=""'
    echo 'export WIKI_BASE=""'
    echo 'export AI_MONITOR_WIKI_BASE=""'
  } >> "$CLAUDE_ENV_FILE"
  echo "ai-monitor: 監視対象として解決できませんでした（$1）。REPO_SLUG / WIKI_BASE / AI_MONITOR_WIKI_BASE は空にしました。"
  echo "ai-monitor: 監視対象にする場合は ${SETTINGS_FILE} の projects[] に本リポジトリを登録してください。"
  exit 0
}

[ -f "$SETTINGS_FILE" ] || skip "settings.yaml がありません: ${SETTINGS_FILE}"

# CWD の git remote からリポジトリ（owner/name）を解決する
REMOTE_URL=$(git remote get-url origin 2>/dev/null) || skip "git remote (origin) がありません"
REPO_SLUG=$(echo "$REMOTE_URL" | sed -E 's#^(git@[^:]+:|ssh://[^/]+/|https?://[^/]+/)##; s#\.git$##')

# settings から プロジェクトの wiki_base と ai_monitor_wiki_base を解決する
BASES=$(python3 - "$SETTINGS_FILE" "$ENV_SETTINGS_FILE" "$REPO_SLUG" <<'EOF'
import pathlib
import sys

import yaml

settings_path, env_settings_path, repo_slug = sys.argv[1], sys.argv[2], sys.argv[3]


def load(path: str) -> dict:
    """yaml を読む（無ければ空 dict）。"""
    if not path or not pathlib.Path(path).is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


base, env = load(settings_path), load(env_settings_path)
# 環境差分を優先して探す（モニター本体と同じ優先順）
projects = [p for p in (env.get("projects") or []) + (base.get("projects") or []) if p["repo"] == repo_slug]
if not projects:
    raise SystemExit(f"projects に {repo_slug} の定義がありません")
wiki_base = env.get("ai_monitor_wiki_base") or base.get("ai_monitor_wiki_base")
if not wiki_base:
    raise SystemExit("ai_monitor_wiki_base が未設定です")
print(projects[0]["wiki_base"])
print(wiki_base)
EOF
) || skip "settings から wiki_base / ai_monitor_wiki_base を解決できません（repo=${REPO_SLUG}）"

WIKI_BASE=$(echo "$BASES" | sed -n 1p)
AI_MONITOR_WIKI_BASE=$(echo "$BASES" | sed -n 2p)

{
  echo "export REPO_SLUG=\"${REPO_SLUG}\""
  echo "export WIKI_BASE=\"${WIKI_BASE}\""
  echo "export AI_MONITOR_WIKI_BASE=\"${AI_MONITOR_WIKI_BASE}\""
} >> "$CLAUDE_ENV_FILE"

echo "ai-monitor: 監視対象 ${REPO_SLUG} として解決しました（WIKI_BASE=${WIKI_BASE}）。"

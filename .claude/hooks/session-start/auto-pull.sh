#!/usr/bin/env bash
# gh-kit Session Start: リポジトリ同期スクリプト
#
# GH_KIT_REPO_PATH が設定されていればメインリポジトリを、
# GH_KIT_WIKI_PATH が設定されていれば Wiki ローカルクローンを
# それぞれ git pull --ff-only で同期する。
#
# 失敗しても警告を出して続行（fast-forward できない状況は基本的に発生しない想定）。

set -euo pipefail

pull_repo() {
  local label="$1"
  local path="$2"

  if [ ! -d "$path/.git" ]; then
    echo "[gh-kit:auto-pull] WARN: ${label} のパスが git リポジトリではありません: ${path}" >&2
    return
  fi

  echo "[gh-kit:auto-pull] ${label} を pull 中: ${path}"
  if git -C "$path" pull --ff-only 2>&1; then
    echo "[gh-kit:auto-pull] ${label} の pull 完了"
  else
    echo "[gh-kit:auto-pull] WARN: ${label} の pull に失敗しました（続行）: ${path}" >&2
  fi
}

# メインリポジトリ同期
if [ -n "${GH_KIT_REPO_PATH:-}" ]; then
  pull_repo "メインリポジトリ" "$GH_KIT_REPO_PATH"
fi

# Wiki ローカルクローン同期
if [ -n "${GH_KIT_WIKI_PATH:-}" ]; then
  pull_repo "Wiki リポジトリ" "$GH_KIT_WIKI_PATH"
fi

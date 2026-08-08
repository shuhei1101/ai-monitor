#!/usr/bin/env bash
# 検証で作った Issue / PR / ブランチ / マイルストーンを片付ける。
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck disable=SC1091
source .state

WT="${WT:-/mnt/c/Users/shuhe/repo/ai-monitor/.claude/worktrees/poc-epic-issue-link-link-methods}"

echo "== PR を close =="
for n in "$PR_EPIC" "$PR_STORY" "$PR_WORK" "$PR_POC" $(cat .state.extra_pr 2>/dev/null || true); do
  state=$(gh api "repos/$REPO/pulls/$n" --jq '.state')
  if [ "$state" = "open" ]; then
    gh pr close "$n" --repo "$REPO" --delete-branch >/dev/null && echo "#$n closed"
  else
    echo "#$n は既に $state"
  fi
done

echo
echo "== 起点 Issue を close =="
gh issue close "$ISSUE" --repo "$REPO" --reason "not planned" >/dev/null && echo "#$ISSUE closed"

echo
echo "== 残ったブランチを削除 =="
for b in epic story work poc extra; do
  if gh api "repos/$REPO/git/refs/heads/$PREFIX-$b" >/dev/null 2>&1; then
    gh api --method DELETE "repos/$REPO/git/refs/heads/$PREFIX-$b" && echo "$PREFIX-$b 削除"
  fi
  git -C "$WT" branch -D "$PREFIX-$b" >/dev/null 2>&1 || true
done

echo
echo "== マイルストーンを削除 =="
gh api --method DELETE "repos/$REPO/milestones/$(cat .state.milestone)" && echo "milestone 削除"

echo
echo "== 残骸の確認 =="
gh api "repos/$REPO/milestones?state=all" --jq '.[].title' || true
git -C "$WT" ls-remote --heads origin "$PREFIX-*" || echo "(リモートブランチなし)"

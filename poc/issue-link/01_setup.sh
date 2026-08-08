#!/usr/bin/env bash
# 検証用の面（起点 Issue 1 本 + PR 4 本）を本番リポジトリに作る。
# 作った番号は .state に書き出し、以降のスクリプトが読む。
set -euo pipefail

cd "$(dirname "$0")"

REPO="${REPO:-shuhei1101/ai-monitor}"
WT="${WT:-/mnt/c/Users/shuhe/repo/ai-monitor/.claude/worktrees/poc-epic-issue-link-link-methods}"
PREFIX="poc-link-verify"
STATE=".state"

git -C "$WT" fetch -q origin master

tree=$(git -C "$WT" rev-parse origin/master^{tree})
base=$(git -C "$WT" rev-parse origin/master)

# HEAD を動かさずに空 commit を積む（この worktree は PoC PR のブランチを載せているため）
c_epic=$(git -C "$WT" commit-tree "$tree" -p "$base"   -m "poc-link: epic layer")
c_story=$(git -C "$WT" commit-tree "$tree" -p "$c_epic"  -m "poc-link: story layer")
c_work=$(git -C "$WT" commit-tree "$tree" -p "$c_story" -m "poc-link: deliverable")
c_poc=$(git -C "$WT" commit-tree "$tree" -p "$c_epic"   -m "poc-link: poc")

git -C "$WT" branch -f "$PREFIX-epic"  "$c_epic"
git -C "$WT" branch -f "$PREFIX-story" "$c_story"
git -C "$WT" branch -f "$PREFIX-work"  "$c_work"
git -C "$WT" branch -f "$PREFIX-poc"   "$c_poc"
git -C "$WT" push -q -f origin \
  "$PREFIX-epic" "$PREFIX-story" "$PREFIX-work" "$PREFIX-poc"

issue=$(gh issue create --repo "$REPO" \
  --title "[poc-link-verify] 起点 Issue（検証用・検証後に削除）" \
  --body "PoC #190 の検証用。3 候補の紐付けを実測するために作成した。検証後に close する。" \
  | grep -oE '[0-9]+$')

new_pr() { # $1=head $2=base $3=title
  gh pr create --repo "$REPO" --draft --head "$1" --base "$2" \
    --title "$3" --body "PoC #190 の検証用。検証後に close する。" | grep -oE '[0-9]+$'
}

pr_epic=$(new_pr "$PREFIX-epic"  master           "[poc-link-verify] epic レイヤー PR")
pr_story=$(new_pr "$PREFIX-story" "$PREFIX-epic"  "[poc-link-verify] story レイヤー PR")
pr_work=$(new_pr "$PREFIX-work"  "$PREFIX-story"  "[poc-link-verify] 成果物 PR")
pr_poc=$(new_pr "$PREFIX-poc"    "$PREFIX-epic"   "[poc-link-verify] PoC PR")

cat > "$STATE" <<EOF
REPO=$REPO
PREFIX=$PREFIX
ISSUE=$issue
PR_EPIC=$pr_epic
PR_STORY=$pr_story
PR_WORK=$pr_work
PR_POC=$pr_poc
EOF

cat "$STATE"

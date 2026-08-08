#!/usr/bin/env bash
# 運用で起きる状態変化（PoC PR の close / 成果物 PR の squash マージ + ブランチ削除）の後も
# 集合の列挙と base による親子復元が保つかを見る。
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck disable=SC1091
source .state

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

dump() { # $1=見出し
  echo
  echo "== $1 =="
  gh api graphql -f owner="$OWNER" -f name="$NAME" -F num="$ISSUE" -f query='
  query($owner:String!,$name:String!,$num:Int!){
    rateLimit{ cost }
    repository(owner:$owner,name:$name){
      issue(number:$num){
        milestone{
          pullRequests(first:100){ nodes{ number state baseRefName headRefName } }
        }
      }
    }
  }' --jq '.data.repository.issue.milestone.pullRequests.nodes[]
    | "#\(.number) \(.state) base=\(.baseRefName) head=\(.headRefName)"'
}

echo "== PR 作成時にマイルストーンを同時指定できるか（REST の PR 作成 body に milestone を入れる）=="
WT="${WT:-/mnt/c/Users/shuhe/repo/ai-monitor/.claude/worktrees/poc-epic-issue-link-link-methods}"
tree=$(git -C "$WT" rev-parse "origin/$PREFIX-epic^{tree}")
head=$(git -C "$WT" rev-parse "origin/$PREFIX-epic")
c_extra=$(git -C "$WT" commit-tree "$tree" -p "$head" -m "poc-link: extra")
git -C "$WT" branch -f "$PREFIX-extra" "$c_extra"
git -C "$WT" push -q -f origin "$PREFIX-extra"

ms=$(cat .state.milestone)
gh api --method POST "repos/$REPO/pulls" \
  -f title="[poc-link-verify] milestone 同時指定の確認" -f head="$PREFIX-extra" -f base="$PREFIX-epic" \
  -F milestone="$ms" -f body="検証用" --jq '.number' > .state.extra_pr
extra=$(cat .state.extra_pr)
echo "作成した PR: #$extra"
gh api "repos/$REPO/issues/$extra" --jq '"milestone=\(.milestone.number // "null")（PR 作成 API で指定した値が乗ったか）"'

dump "初期状態"

echo
echo "== PoC PR #$PR_POC を close =="
gh pr close "$PR_POC" --repo "$REPO" >/dev/null
dump "close 後"

echo
echo "== 成果物 PR #$PR_WORK を squash マージ + ブランチ削除 =="
gh pr ready "$PR_WORK" --repo "$REPO" >/dev/null
gh pr merge "$PR_WORK" --repo "$REPO" --squash --delete-branch >/dev/null
sleep 3
dump "マージ + ブランチ削除 後"

echo
echo "== ブランチ削除後も親子を復元できるか =="
gh api graphql -f owner="$OWNER" -f name="$NAME" -F num="$ISSUE" -f query='
query($owner:String!,$name:String!,$num:Int!){
  rateLimit{ cost }
  repository(owner:$owner,name:$name){
    issue(number:$num){
      milestone{
        number
        issues(first:100){ nodes{ number state } }
        pullRequests(first:100){ nodes{ number title state isDraft baseRefName headRefName } }
      }
    }
  }
}' | PR_EPIC="$PR_EPIC" PR_STORY="$PR_STORY" PR_WORK="$PR_WORK" PR_POC="$PR_POC" python3 05_parse.py

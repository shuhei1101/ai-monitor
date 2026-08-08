#!/usr/bin/env bash
# 候補 1: Milestone。作成 → 起点 Issue と PR 4 本へ付与 → 1 クエリで配下を列挙。
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck disable=SC1091
source .state

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

echo "== 作成 =="
ms=$(gh api "repos/$REPO/milestones" -f title="poc-link-verify" \
  -f description="PoC #190 の検証用" --jq '.number')
echo "milestone=$ms"

echo
echo "== 付与（Issue / PR とも同じ REST エンドポイント）=="
for n in "$ISSUE" "$PR_EPIC" "$PR_STORY" "$PR_WORK" "$PR_POC"; do
  got=$(gh api --method PATCH "repos/$REPO/issues/$n" -F milestone="$ms" --jq '.milestone.number')
  echo "#$n -> milestone $got"
done

echo
echo "== 列挙（GraphQL 1 リクエスト）=="
gh api graphql -f owner="$OWNER" -f name="$NAME" -F num="$ms" -f query='
query($owner:String!,$name:String!,$num:Int!){
  rateLimit{ cost remaining }
  repository(owner:$owner,name:$name){
    milestone(number:$num){
      title
      issues(first:100){ nodes{ number title } }
      pullRequests(first:100){ nodes{ number title baseRefName headRefName } }
    }
  }
}'

echo
echo "== 階層を表すフィールドの有無 =="
gh api "repos/$REPO/milestones/$ms" --jq 'keys'

echo "$ms" > .state.milestone

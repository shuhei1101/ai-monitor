#!/usr/bin/env bash
# 本命構成: 起点 Issue の番号だけを入力に、GraphQL 1 リクエストで配下 PR を列挙し、
# 同じ応答の baseRefName / headRefName から PR 同士の親子を復元する。
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck disable=SC1091
source .state

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

echo "== 起点 Issue #$ISSUE から 1 リクエストで取得 =="
resp=$(gh api graphql -f owner="$OWNER" -f name="$NAME" -F num="$ISSUE" -f query='
query($owner:String!,$name:String!,$num:Int!){
  rateLimit{ cost remaining }
  repository(owner:$owner,name:$name){
    issue(number:$num){
      number
      milestone{
        number title
        issues(first:100){ nodes{ number state } }
        pullRequests(first:100){ nodes{ number title state isDraft baseRefName headRefName } }
      }
    }
  }
}')
echo "$resp" | PR_EPIC="$PR_EPIC" PR_STORY="$PR_STORY" PR_WORK="$PR_WORK" PR_POC="$PR_POC" \
  python3 05_parse.py

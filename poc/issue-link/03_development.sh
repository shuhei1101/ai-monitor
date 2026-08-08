#!/usr/bin/env bash
# 候補 2: Development リンク。API から任意の Issue へ PR をぶら下げられるかを見る。
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck disable=SC1091
source .state

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

echo "== link 系 mutation の有無（introspection）=="
gh api graphql -f query='query{ __schema{ mutationType{ fields{ name } } } }' \
  --jq '.data.__schema.mutationType.fields[].name' | grep -iE 'link|closingissue' || echo "(該当なし)"

echo
echo "== PR 本文のキーワードでリンクを張る =="
gh pr edit "$PR_WORK" --repo "$REPO" \
  --body "PoC #190 の検証用。検証後に close する。

Closes #$ISSUE" >/dev/null
sleep 3

echo
echo "== PR → Issue（closingIssuesReferences）=="
gh api graphql -f owner="$OWNER" -f name="$NAME" -F pr="$PR_WORK" -f query='
query($owner:String!,$name:String!,$pr:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$pr){
      number
      closingIssuesReferences(first:10){ nodes{ number title } }
    }
  }
}' --jq '.data.repository.pullRequest'

echo
echo "== Issue → PR（closedByPullRequestsReferences / linkedBranches）=="
gh api graphql -f owner="$OWNER" -f name="$NAME" -F num="$ISSUE" -f query='
query($owner:String!,$name:String!,$num:Int!){
  rateLimit{ cost }
  repository(owner:$owner,name:$name){
    issue(number:$num){
      number
      closedByPullRequestsReferences(first:20, includeClosedPrs:true){ nodes{ number title baseRefName headRefName } }
      linkedBranches(first:20){ nodes{ ref{ name } } }
    }
  }
}'

echo
echo "== base=master の PR なら張れるか（#PR_EPIC）=="
gh pr edit "$PR_EPIC" --repo "$REPO" \
  --body "PoC #190 の検証用。検証後に close する。

Closes #$ISSUE" >/dev/null
sleep 3
gh api graphql -f owner="$OWNER" -f name="$NAME" -F pr="$PR_EPIC" -f query='
query($owner:String!,$name:String!,$pr:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$pr){
      number baseRefName
      closingIssuesReferences(first:10){ nodes{ number title } }
    }
  }
}' --jq '.data.repository.pullRequest'

echo
echo "== createLinkedBranch で既存ブランチを Issue にぶら下げられるか =="
issue_id=$(gh api graphql -f owner="$OWNER" -f name="$NAME" -F num="$ISSUE" -f query='
query($owner:String!,$name:String!,$num:Int!){ repository(owner:$owner,name:$name){ issue(number:$num){ id } } }' \
  --jq '.data.repository.issue.id')
head_oid=$(gh api "repos/$REPO/git/ref/heads/$PREFIX-work" --jq '.object.sha')
gh api graphql -f issueId="$issue_id" -f oid="$head_oid" -f branch="$PREFIX-work" -f query='
mutation($issueId:ID!,$oid:GitObjectID!,$branch:String!){
  createLinkedBranch(input:{issueId:$issueId, oid:$oid, name:$branch}){
    linkedBranch{ id ref{ name } }
  }
}' 2>&1 | head -5

echo
echo "== PR 同士を張れるか（PR を対象に closingIssuesReferences を作れるか）=="
gh pr edit "$PR_STORY" --repo "$REPO" \
  --body "PoC #190 の検証用。検証後に close する。

Closes #$PR_EPIC" >/dev/null
sleep 3
gh api graphql -f owner="$OWNER" -f name="$NAME" -F pr="$PR_STORY" -f query='
query($owner:String!,$name:String!,$pr:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$pr){
      number
      closingIssuesReferences(first:10){ nodes{ number title } }
    }
  }
}' --jq '.data.repository.pullRequest'

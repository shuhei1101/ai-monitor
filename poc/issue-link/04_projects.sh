#!/usr/bin/env bash
# 候補 3: Projects v2。作成 → Issue / PR の追加 → text フィールドへ親 PR 番号 → 1 クエリで取得。
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck disable=SC1091
source .state

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

gql() { gh api graphql "$@"; }

echo "== 作成 =="
owner_id=$(gql -f login="$OWNER" -f query='query($login:String!){ user(login:$login){ id } }' --jq '.data.user.id')
proj=$(gql -f ownerId="$owner_id" -f title="poc-link-verify" -f query='
mutation($ownerId:ID!,$title:String!){
  createProjectV2(input:{ownerId:$ownerId,title:$title}){ projectV2{ id number } }
}' --jq '.data.createProjectV2.projectV2 | "\(.id) \(.number)"')
proj_id=${proj% *}; proj_num=${proj#* }
echo "project=$proj_num id=$proj_id"

echo
echo "== text フィールド parent_pr を作る =="
field_id=$(gql -f pid="$proj_id" -f query='
mutation($pid:ID!){
  createProjectV2Field(input:{projectId:$pid, dataType:TEXT, name:"parent_pr"}){
    projectV2Field{ ... on ProjectV2Field { id name } }
  }
}' --jq '.data.createProjectV2Field.projectV2Field.id')
echo "field=$field_id"

echo
echo "== 追加 + 親 PR の書き込み（1 面あたりの呼び出し回数を数える）=="
node_id() { gh api "repos/$REPO/issues/$1" --jq '.node_id'; }
add() { # $1=番号 $2=親 PR 番号（空なら書き込みなし）
  local nid item
  nid=$(node_id "$1")
  item=$(gql -f pid="$proj_id" -f cid="$nid" -f query='
    mutation($pid:ID!,$cid:ID!){ addProjectV2ItemById(input:{projectId:$pid, contentId:$cid}){ item{ id } } }' \
    --jq '.data.addProjectV2ItemById.item.id')
  if [ -n "${2:-}" ]; then
    gql -f pid="$proj_id" -f iid="$item" -f fid="$field_id" -f val="$2" -f query='
      mutation($pid:ID!,$iid:ID!,$fid:ID!,$val:String!){
        updateProjectV2ItemFieldValue(input:{projectId:$pid,itemId:$iid,fieldId:$fid,value:{text:$val}}){
          projectV2Item{ id }
        }
      }' >/dev/null
    echo "#$1 追加 + parent_pr=$2（API 3 回: node_id 取得 / 追加 / 更新）"
  else
    echo "#$1 追加（API 2 回: node_id 取得 / 追加）"
  fi
}
add "$ISSUE"   ""
add "$PR_EPIC" ""
add "$PR_STORY" "$PR_EPIC"
add "$PR_WORK"  "$PR_STORY"
add "$PR_POC"   "$PR_EPIC"

echo
echo "== 列挙（GraphQL 1 リクエスト）=="
gql -f login="$OWNER" -F num="$proj_num" -f query='
query($login:String!,$num:Int!){
  rateLimit{ cost remaining }
  user(login:$login){
    projectV2(number:$num){
      title
      items(first:100){
        nodes{
          content{
            ... on Issue { number title }
            ... on PullRequest { number title baseRefName headRefName }
          }
          fieldValues(first:20){
            nodes{ ... on ProjectV2ItemFieldTextValue { text field{ ... on ProjectV2Field { name } } } }
          }
        }
      }
    }
  }
}'

echo "$proj_id" > .state.project

---
name: gh-kit:issue-create
description: GitHub Issue を 1 件起票する。確認:issue-reviewer ラベルを強制付与し、AI レビューフローに確実に乗せる。code-scanner や手動呼び出しの両方から使える。
---

# issue-create

このスキルは Issue 起票の責務を一か所に集約するために作られた。

**なぜ `確認:issue-reviewer` を強制付与するのか？**
Issue 起票後に AI レビューフロー（`/gh-kit:issue-review-auto`）が確実に対象を拾うには、`確認:issue-reviewer` ラベルが必須。呼び出し側（code-scanner 等）がラベルを付け忘れると AI レビューが走らなくなるため、このスキル内部で構造的に保証する。

## 入力

| 引数 | 必須 | 内容 |
| --- | --- | --- |
| `title` | 必須 | Issue タイトル |
| `body` | 必須 | Issue 本文（`イシュードキュメント.j2` テンプレを呼び出し側が展開済み） |
| `type` | 必須 | Issue タイプラベル（例: `bug`, `enhancement`, `refactor`） |
| `priority` | 必須 | 優先度ラベル（例: `優先度:急ぎ`, `優先度:いつでも`） |
| `needs_user_review` | 任意 | `true` の場合 `gh issue edit --add-assignee` でユーザーをアサイン（既定: `false`） |
| `extra_labels` | 任意 | 追加ラベルのカンマ区切り文字列（既定: なし） |

## 動作フロー

1. 必要ラベルを `gh label create` で冪等に用意する（既存ならスキップ）
2. `確認:issue-reviewer` を含むラベル文字列を組み立てる
3. `gh issue create` で起票する
4. `issue_number` / `issue_url` を戻り値として返す

## 呼び出し元

- `code-scanner` エージェント（ステップ 7 から移管）
- ユーザーが `/gh-kit:issue-create` を直接呼び出す場合

## ステップ 1: ラベルを冪等に用意する

```bash
gh label list | grep -q "^${GH_KIT_LABEL_CONFIRM_ISSUE_REVIEW}" || \
  gh label create "$GH_KIT_LABEL_CONFIRM_ISSUE_REVIEW" --color "$GH_KIT_LABEL_COLOR_CONFIRM_ISSUE_REVIEW" --description "issue-reviewer エージェントによるレビュー必要"

gh label list | grep -qF "${GH_KIT_LABEL_PRIORITY_URGENT}" || \
  gh label create "${GH_KIT_LABEL_PRIORITY_URGENT}" \
    --color "${GH_KIT_LABEL_COLOR_PRIORITY_URGENT}" \
    --description "早急に対応が必要なもの"

gh label list | grep -qF "${GH_KIT_LABEL_PRIORITY_LOW}" || \
  gh label create "${GH_KIT_LABEL_PRIORITY_LOW}" \
    --color "${GH_KIT_LABEL_COLOR_PRIORITY_LOW}" \
    --description "時期を問わず対応可能なもの"
```

> **新ラベルを優先利用:** `優先度:急ぎ` / `優先度:いつでも` を使うこと。旧ラベル (`priority:high` / `priority:medium` / `priority:low`) は既存 Issue/PR を尊重するため削除しない。

## ステップ 2: ラベル文字列を組み立てる

```bash
# 確認:issue-reviewer は呼び出し側が指定しなくても必ず付与する（構造的保証）
# ai-code-scan ラベルは code-scanner 経由起票時のみ extra_labels で渡す（出自タグのため）
LABELS="${GH_KIT_LABEL_CONFIRM_ISSUE_REVIEW},{type},{priority}"

GH_LOGIN=$(gh api user --jq '.login')
ASSIGNEE_OPT=""
if [ "{needs_user_review}" = "true" ]; then
  ASSIGNEE_OPT="--assignee ${GH_LOGIN}"
fi

if [ -n "{extra_labels}" ]; then
  LABELS="${LABELS},{extra_labels}"
fi
```

## ステップ 3: gh issue create で起票する

```bash
ISSUE_URL=$(gh issue create \
  --title "{title}" \
  --body-file <(cat <<'EOF'
{body}
EOF
) \
  --label "$LABELS")
ISSUE_NUMBER=$(echo "$ISSUE_URL" | grep -o '[0-9]*$')
```

起票に成功したら、`needs_user_review` が `true` の場合は assignee を追加する:

```bash
if [ -n "$ASSIGNEE_OPT" ]; then
  gh issue edit "$ISSUE_NUMBER" $ASSIGNEE_OPT
fi
```

## 戻り値

```json
{
  "issue_number": 42,
  "issue_url": "https://github.com/owner/repo/issues/42",
  "title": "Issue タイトル",
  "needs_user_review": false
}
```

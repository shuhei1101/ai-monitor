---
name: gh-kit:pr-implement
description: "wip Draft PR を 1 件実装する: worktree 復帰 → fetch/reset → 実装 → テスト実行 → コミット → push → gh pr ready。pr-implementer エージェントから呼ばれる。"
---

# pr-implement

既存 Draft PR の中身を実装し、Ready for review にする。
新規ブランチ・新規 PR の作成は行わない。

## 入力

| 引数 | 必須 | 内容 |
| --- | --- | --- |
| PR 番号 | 必須 | 例: 42 |
| branch | 必須 | 例: `feat/issue-42-router` |
| base ブランチ | 必須 | 通常 `master` |
| Issue 番号 | 必須 | 紐づく Issue 番号 |
| 採用方針 | 必須 | Issue コメントの `issue-reviewer` 結果から抽出 |
| 分割スコープ | 任意 | この PR で扱うスコープ（1 Issue 複数 PR 時） |

## ステップ 1: ユーザー確認要否判定基準を読み込む

!`curl -fsSL "https://raw.githubusercontent.com/wiki/$(gh repo view --json nameWithOwner --jq '.nameWithOwner')/ユーザー確認要否判定.md" 2>/dev/null || echo "[WARN] ユーザー確認要否判定 Wiki ページを取得できませんでした"`

ステップ 7 で参照する。

## ステップ 2: ワークツリー復帰 + remote 同期

```bash
WT=".claude/worktrees/$(echo {branch} | tr '/' '-')"
if [ ! -d "$WT" ]; then
  echo "worktree missing, please call gh-kit-tools worktree_create MCP for branch={branch}" >&2
  exit 1
fi
git -C "$WT" fetch origin
git -C "$WT" reset --hard origin/{branch}
```

## ステップ 2.5: PR 本文・コメントを読み込む

```bash
gh pr view {PR_NUMBER} --json number,title,body,comments
```

取得した情報（PR 本文のタスクリスト・実装方針・注意事項、コメントのユーザー追記・レビュー指示）を
ステップ 3 の実装コンテキストとして参照する。

## ステップ 3: 実装

採用方針・分割スコープ・ステップ 2.5 で読み込んだ PR 本文/コメントに従ってコード変更する。コミットは細かく刻んでよい。

| No | 動作 |
| --- | --- |
| 1 | 採用方針の通りにコード変更（`pr-test-creator` が作成したテストが通るよう実装する） |
| 2 | 実装コードに合わせてテストコードを微調整する（大幅な書き直しは `pr-test-creator` の役割逸脱なので最小限に） |

## ステップ 4: テストを実行する

プロジェクトのテストを実行し、全テスト成功を確認する。

```bash
# 例: Python / pytest の場合
cd "$WT" && uv run pytest tests/ --ignore=tests/smoke/ -v
# 例: Node.js の場合
cd "$WT" && npm test
```

テストが失敗した場合は、実装コードを修正してから再実行する。
スモークテスト（外部サービスへの実接続）は実行しない。
全テスト成功を確認してからステップ 5 へ進む。

## ステップ 5: テスト実行結果を PR コメントとして投稿する

全テスト成功後、`テスト実行結果` Wiki ページのテンプレートを取得して実値で埋め、PR にコメントを投稿する。

```bash
# Wiki からテンプレートを取得
curl -fsSL "https://raw.githubusercontent.com/wiki/$(gh repo view --json nameWithOwner --jq '.nameWithOwner')/テスト実行結果.md"
```

テンプレートを実値（テスト種別・ファイル・件数・実行コマンド・サマリ出力）で埋めて PR コメントを投稿する。

```bash
gh pr comment {PR_NUMBER} --body "$(cat <<'EOF'
{テスト実行結果テンプレートを実値で埋めた内容}
EOF
)"
```

## ステップ 6: push

```bash
git -C "$WT" push origin {branch}
```

## ステップ 7: ユーザー確認要否を再判定

ステップ 1 で読み込んだ基準に照らし、実装結果（実コード変更内容）から
`needs_user_review: true|false` を決める。
Issue 起票時の判断と変わる可能性あり（例: refactor 想定だったが仕様に踏み込んだ場合は true）。

## ステップ 7.5: PR 本文チェックリストを完了状況に合わせて更新（スキップ禁止）

**このステップは必須実行。スキップ・省略は禁止。**

実装が完了したタスクについて、PR 本文の `- [ ]` を `- [x]` に置換し `gh pr edit` で更新する。
未実装タスクは `- [ ]` のまま残す（全件チェックではなく実際の完了状況に合わせる）。

```bash
# 1. 現在の PR 本文を取得
gh pr view {PR_NUMBER} --json body --jq '.body'
```

2. AI が取得した本文を読み、**この PR で実際に実装が完了したタスクのみ** `- [ ]` → `- [x]` に書き換えた新本文を作成する。
   - 一括 sed 置換は禁止。AI が各タスクの完了状況を判断して選択的に書き換えること。
   - 未実装タスクは `- [ ]` のまま残す。

3. 作成した新本文で PR 本文を更新する:

```bash
gh pr edit {PR_NUMBER} --body-file <(cat <<'EOF'
{新本文をここに貼り付ける}
EOF
)
```

未実装タスクが残っている場合（`- [ ]` が残る場合）は、その理由と残タスクを PR コメントに記載する。

```bash
# 未実装タスクが残っている場合は以下のコメントを投稿
# ※ {未実装タスク一覧} と {未実装理由} は AI が実際の内容で置換してから投稿すること
gh pr comment {PR_NUMBER} --body "$(cat <<'EOF'
## 未実装タスク（PR レビュー前に要対応）

以下のタスクは未実装のため、`- [ ]` のまま残しています。
PR 本文の `- [ ]` が残っている場合、`pr-review` スキルが `needs-fix` で差し戻します。

未実装タスク:
{未実装タスク一覧}

理由:
{未実装理由}
EOF
)"
```

## ステップ 8: PR を Ready 化

```bash
gh pr ready {PR_NUMBER}
gh pr comment {PR_NUMBER} --body "実装完了。レビュー待ち。{変更サマリ}"
```

`$GH_KIT_LABEL_CONFIRM_PR_REVIEW`（`確認:pr-reviewer`）ラベル付与と assignees 追加（`needs_user_review: true` の場合）は呼び出し側（`/gh-kit:pr-implement-auto`）の責務。

## ステップ 9: 戻り値

```json
{
  "branch": "feat/issue-42-router",
  "pr_number": 42,
  "status": "ready",
  "needs_user_review": true,
  "commits_added": 5,
  "message": "詳細メッセージ"
}
```

## 制約

| No | 禁止 |
| --- | --- |
| 1 | 新規ブランチ・新規 PR は作成しない |
| 2 | マージはしない |
| 3 | コンフリクトが出たら親に報告して停止（`-X ours/theirs` 禁止） |
| 4 | `git push --force` は使わない |
| 5 | スモークテスト（外部サービスへの実接続）は実行しない |

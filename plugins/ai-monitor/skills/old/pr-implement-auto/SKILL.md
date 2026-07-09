---
name: ai-monitor:pr-implement-auto
description: 確認:pr-implementer（AI_MONITOR_LABEL_CONFIRM_PR_IMPLEMENT）ラベル付き PR を N 件並列で実装し、Ready 化 → そのまま pr-review-auto に連鎖
disable-model-invocation: false
---

# pr-implement-auto

`確認:pr-implementer` ラベル付き PR を拾い、中身を実装して Ready for review に切り替える。

## 環境変数

| 変数 | 既定 | 用途 |
| --- | --- | --- |
| `AI_MONITOR_PR_IMPLEMENT_PARALLEL` | `5` | 並列起動上限 |

## 入力

| 引数 | 必須 | 内容 |
| --- | --- | --- |
| PR 番号 | 任意 | 指定時はその 1 件のみ |

## ループ継続制約（厳守）

- Monitorは何があっても絶対に止めない。
- ステップ 4 完了後（キューが空になった場合も含む）は**即座にステップ 0（Monitor）へ戻る。**
- **途中結果報告は禁止。** 「N 件実装しました」などのユーザー向け報告はステップ 5（TaskStop 後）にのみ行う。
- ステップ 5 はキューが空になった後に TaskStop を受信したときにのみ実行する。

## タスク

### ステップ 0: Monitor でイベント待機

対象 PR が既に存在する場合はそのままステップ 1 へ進む。
存在しない場合は Monitor ツールで以下のポーリングスクリプトを実行し、対象が出現したらステップ 1 へ進む。

対象条件: `確認:pr-implementer`（`$AI_MONITOR_LABEL_CONFIRM_PR_IMPLEMENT`）ラベル付きの PR（Draft・Ready 問わず）。`処理中:` で始まるラベル付きは除外。

**ステップ 4 完了後（キューが空の場合も含む）はこのステップに戻り、Monitor を再起動してポーリングを継続する。**

```bash
# Monitor に渡すポーリングスクリプト
while true; do
  AVAILABLE=$(gh pr list --state open --label "$AI_MONITOR_LABEL_CONFIRM_PR_IMPLEMENT" \
    --json number,labels \
    --jq "[.[] | select(.labels | map(.name) | (map(startswith(\"処理中:\")) | any | not))] | length" 2>/dev/null || echo 0)
  if [ "$AVAILABLE" -gt 0 ]; then
    echo "TRIGGER:pr-implement-auto:count=$AVAILABLE"
    break
  fi
  sleep 30
done
```

Monitor の stdout に `TRIGGER:pr-implement-auto` が来たらステップ 1 へ進む。
手動停止は TaskStop で行う。

### ステップ 1: 対象 PR を収集

`確認:pr-implementer`（`$AI_MONITOR_LABEL_CONFIRM_PR_IMPLEMENT`）ラベル付きの PR を収集する（Draft・Ready 問わず）。

```bash
# 指定なしのとき
gh pr list --state open --label "$AI_MONITOR_LABEL_CONFIRM_PR_IMPLEMENT" \
  --json number,title,headRefName,baseRefName,body,labels,isDraft --limit 50
# 指定ありのとき
gh pr view {N} --json number,title,headRefName,baseRefName,body,labels,isDraft
```

`処理中:` で始まるラベル（`処理中:pr-impl`・`処理中:pr-arch`・`処理中:pr-impl-review`・`処理中:pr-merge` 等）付きは除外。0 件なら停止。

> **注記:** `$AI_MONITOR_LABEL_CONFIRM_PR_IMPLEMENT`（= `確認:pr-implementer`）は実装待ち専用ラベル（旧 `AI_MONITOR_LABEL_NEEDS_FIX` の後継）。Issue レビュー用の `確認:issue-reviewer`（`$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW`）とは別物。

収集後、`優先度:急ぎ` ラベルが付いている PR を先頭に並べ、次に `優先度:いつでも` 付き、それ以外の順（番号昇順）で処理する:

```bash
# jq でラベル名に優先度:急ぎ を含むものを先頭に、次に優先度:いつでも、残りは番号昇順
# 注: 優先度ラベルは処理順序のみを制御する。ユーザー確認スキップ・自動マージのトリガーにはならない。
jq --arg urgent "$AI_MONITOR_LABEL_PRIORITY_URGENT" --arg low "$AI_MONITOR_LABEL_PRIORITY_LOW" 'sort_by(
  if (.labels | map(.name) | index($urgent)) then 0
  elif (.labels | map(.name) | index($low)) then 1
  else 2
  end, .number
)'
```

上記ソート後、上位 **N** 件を対象とする。

### ステップ 2: 排他制御

`確認:pr-implementer` を除去して `処理中:pr-implementer` を付与する。

```bash
gh pr edit {N} --add-label "$AI_MONITOR_LABEL_PROCESSING_PR_IMPLEMENTER" \
  --remove-label "$AI_MONITOR_LABEL_CONFIRM_PR_IMPLEMENT"
```

### ステップ 3: pr-test-creator を先行起動（テストタスクがある場合）

起動前に、紐づく Issue に `処理中:pr-implementer` を付与する。

```bash
# PR 本文から Issue 番号を抽出して付与
ISSUE_N=$(gh pr view {N} --json body --jq '.body' | grep -oP '(?:Refs|Closes|Fixes) #\K[0-9]+' | head -1)
if [ -n "$ISSUE_N" ]; then
  gh issue edit "$ISSUE_N" --add-label "$AI_MONITOR_LABEL_PROCESSING_PR_IMPLEMENTER"
fi
```

PR 本文の「実装予定タスク」に「自動テスト作成/変更」チェックボックスが含まれ、かつ未完了（`- [ ] 自動テスト作成`）の場合は、`pr-test-creator` を先行起動してテストコードを作成させる。

```bash
# テストタスクの存在確認
gh pr view {N} --json body --jq '.body' | grep -q "- \[ \] 自動テスト作成" && HAS_TEST_TASK=true || HAS_TEST_TASK=false
```

`HAS_TEST_TASK=true` の場合: `pr-test-creator` サブエージェントを起動し、完了を待ってから `pr-implementer` を起動する（直列）。
`HAS_TEST_TASK=false` の場合: `pr-implementer` を直接起動する。

### ステップ 3a: pr-implementer をバックグラウンドで並列起動（完了を待たない・通知駆動）

**原則: 完了を待たない。** `run_in_background: true` でサブエージェントを起動したら即座に Monitor 監視に戻る。
完了通知（`<task-notification>`）を受けたら後処理（ステップ 4）を実行する。

`pr-test-creator` の完了後（またはテストタスクなしの場合はステップ 3 完了後）に `pr-implementer` を `run_in_background: true` で起動する:
- 起動上限 **N**（`AI_MONITOR_PR_IMPLEMENT_PARALLEL`）に達している場合は新規起動をキューイングし、1 体完了通知を受けたら次を起動する
- 起動後は即座に Monitor に制御を戻す

### ステップ 4: 通知ハンドラ（サブエージェント完了時に実行）

`pr-implementer` からの完了通知（`<task-notification>`）を受信したら以下を実行する:
（戻り値: `{branch, pr_number, status, needs_user_review, commits_added}` を通知から取得）

```bash
# 成功
# AI_MONITOR_LABEL_CONFIRM_PR_REVIEW（= 確認:pr-reviewer）を付与して pr-review-auto に引き渡す
gh pr edit {N} --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_IMPLEMENTER" --add-label "$AI_MONITOR_LABEL_CONFIRM_PR_REVIEW"
if [ "{needs_user_review}" = "true" ]; then
  GH_LOGIN="$(gh api user --jq '.login')"
  gh pr edit {N} --add-assignee "$GH_LOGIN"
fi
# Issue の 処理中:pr-implementer を除去
ISSUE_N=$(gh pr view {N} --json body --jq '.body' | grep -oP '(?:Refs|Closes|Fixes) #\K[0-9]+' | head -1)
if [ -n "$ISSUE_N" ]; then
  gh issue edit "$ISSUE_N" --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_IMPLEMENTER"
fi

# 失敗（実装エラー・ビルド失敗等の場合は pr-reviewer にエスカレーション）
gh pr edit {N} --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_IMPLEMENTER" --add-label "$AI_MONITOR_LABEL_CONFIRM_PR_REVIEW"
gh pr comment {N} --body "{失敗理由}"
ISSUE_N=$(gh pr view {N} --json body --jq '.body' | grep -oP '(?:Refs|Closes|Fixes) #\K[0-9]+' | head -1)
if [ -n "$ISSUE_N" ]; then
  gh issue edit "$ISSUE_N" --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_IMPLEMENTER"
fi
```

後処理完了後、キューに積まれた次の PR があれば `pr-implementer` を起動する。
キューが空になったらステップ 0（Monitor）へ戻り、次のイベントを待機する。

### ステップ 5: pr-review-auto を連鎖実行

ステップ 4 で 1 件以上 `確認:pr-reviewer`（`$AI_MONITOR_LABEL_CONFIRM_PR_REVIEW`）を付与した PR が存在すれば、続けて
`/ai-monitor:pr-review-auto` を呼び出して直列レビュー → マージへ進める。

## 厳守事項

| No | 禁止 |
| --- | --- |
| 1 | マージしてはならない（マージは `pr-review-auto` の責務） |
| 2 | `処理中:pr-implementer` 付き PR を別セッションが触ってはならない |
| 3 | 新規ブランチ・新規 PR を作成しない |

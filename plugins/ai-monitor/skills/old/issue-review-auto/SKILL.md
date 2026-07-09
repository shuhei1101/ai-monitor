---
name: ai-monitor:issue-review-auto
description: 確認:issue-reviewer（AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW）ラベルの Issue を並列で AI レビューし、コメント投稿する
disable-model-invocation: false
---

# issue-review-auto

`確認:issue-reviewer`（`$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW`）付きの Issue を `issue-reviewer` に並列で渡す。

## 環境変数

| 変数 | 既定 | 用途 |
| --- | --- | --- |
| `AI_MONITOR_ISSUE_REVIEW_PARALLEL` | `5` | 並列起動上限 |

## 入力

| 引数 | 必須 | 内容 |
| --- | --- | --- |
| Issue 番号 | 任意 | 省略時は `確認:issue-reviewer`（`$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW`）付きを全件巡回 |

## フロー概要

```
確認:issue-reviewer（$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW）付き Issue 収集
  → issue-reviewer に渡す（初回レビュー or 再レビュー）
    → re_review_needed: false → 確認:issue-reviewer 除去 → assignee にユーザーを追加
    → re_review_needed: true  → 確認:issue-reviewer 除去 → assignee にユーザーを追加
    → status: waiting         → ラベル変更なし（ユーザー返答待ち）
```

**注意:** pr-planner の自動起動は廃止。レビュー完了後は常に assignee にユーザーを追加する。ユーザーが確認後に手動で `確認:pr-planner` を付与して次工程を進める。

**ユーザーが再レビューを要求する場合:** ユーザーが Issue にコメントを追記した後、手動で `確認:issue-reviewer`（`$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW`）を再付与すると、次回の `issue-review-auto` 実行時に `issue-reviewer` が再レビューモードで動作する。

## ループ継続制約（厳守）

- Monitorは何があっても絶対に止めない。
- サブエージェント完了後は後処理のみ行い、**即座にステップ 0（Monitor）へ戻る。**
- **途中結果報告は禁止。** 「N 件処理しました」などのユーザー向け報告はステップ 5（全処理終了後）にのみ行う。
- ステップ 4 が完了したら報告せず次のポーリングサイクルへ。

## タスク

### ステップ 0: Monitor でイベント待機

対象 Issue が既に存在する場合はそのままステップ 1 へ進む。
存在しない場合は Monitor ツールで以下のポーリングスクリプトを実行し、対象が出現したらステップ 1 へ進む。

**ステップ 4 完了後もこのステップに戻り、Monitor を再起動してポーリングを継続する。**

```bash
# Monitor に渡すポーリングスクリプト（TRIGGER 後はステップ 1 へ進み、処理完了後に再びこのスクリプトを Monitor で実行する）
while true; do
  COUNT=$(gh issue list --state open --label "$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW" \
    --json number --jq 'length' 2>/dev/null || echo 0)
  # 処理中:* ラベル付きを除いたカウント（処理中: で始まるラベルがひとつでもあれば除外）
  AVAILABLE=$(gh issue list --state open --label "$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW" \
    --json number,labels \
    --jq "[.[] | select(.labels | map(.name) | (map(startswith(\"処理中:\")) | any | not))] | length" 2>/dev/null || echo 0)
  if [ "$AVAILABLE" -gt 0 ]; then
    echo "TRIGGER:issue-review-auto:count=$AVAILABLE"
    break
  fi
  sleep 30
done
```

Monitor の stdout に `TRIGGER:issue-review-auto` が来たらステップ 1 へ進む。
手動停止は TaskStop で行う。

### ステップ 1: 対象 Issue を収集

```bash
# 指定なしのとき
gh issue list --state open --label "$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW" --json number,title,labels --limit 100
# 指定ありのとき
gh issue view {N} --json number,title,body,labels,comments
```

`処理中:` で始まるラベル付きは除外（他セッションが処理中）。0 件なら停止。

収集後、`優先度:急ぎ` ラベルが付いている Issue を先頭に並べ、次に `優先度:いつでも` 付き、それ以外の順で処理する:

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

### ステップ 2: 排他制御

```bash
# 自身に依頼された確認ラベルを除去し、処理中ラベルを付与する
gh issue edit {N} \
  --remove-label "$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW" \
  --add-label "$AI_MONITOR_LABEL_PROCESSING_ISSUE_REVIEWER"
```

### ステップ 3: issue-reviewer をバックグラウンドで並列起動（完了を待たない・通知駆動）

**原則: 完了を待たない。** `run_in_background: true` でサブエージェントを起動したら即座に Monitor 監視に戻る。
完了通知（`<task-notification>`）を受けたら後処理（ステップ 4）を実行する。

上位 N 件（`AI_MONITOR_ISSUE_REVIEW_PARALLEL`）を `run_in_background: true` で並列起動する:
- 起動上限に達している場合は新規起動をキューイングし、1 体完了通知を受けたら次を起動する
- 起動後は即座に Monitor に制御を戻す

### ステップ 4: 通知ハンドラ（サブエージェント完了時に実行）

`issue-reviewer` からの完了通知（`<task-notification>`）を受信したら以下を実行する:
（戻り値: `{issue_number, re_review_needed, status}` を通知から取得 — エージェントが gh CLI でコメント投稿を完結させる）

**後処理完了後は結果報告せずに即座にステップ 0（Monitor）へ戻る。**

戻り値の `status` と `re_review_needed` に応じてラベルを操作する。

**status が `ok` の場合（通常レビュー完了）:**

```bash
# status: waiting の場合 — ユーザー返答待ちのため 処理中:issue-reviewer と 確認:issue-reviewer を除去
# ユーザーが返答後に再レビューが必要な場合は手動で 確認:issue-reviewer を再付与すること
if [ "{status}" = "waiting" ]; then
  gh issue edit {N} \
    --remove-label "$AI_MONITOR_LABEL_PROCESSING_ISSUE_REVIEWER" \
    --remove-label "$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW"
  return
fi

# status: ok の場合 — 処理中:issue-reviewer と 確認:issue-reviewer を除去
ARGS=(--remove-label "$AI_MONITOR_LABEL_PROCESSING_ISSUE_REVIEWER" --remove-label "$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW")
gh issue edit {N} "${ARGS[@]}"

# レビュー完了後は needs_user_review の値に関わらず、常に assignee にユーザーを追加する（スキップ禁止）
GH_LOGIN="$(gh api user --jq '.login')"
gh issue edit {N} --add-assignee "$GH_LOGIN"

# 次工程（pr-planner 起動など）はユーザーが手動で 確認:pr-planner ラベルを付与して進める
```

**注意:** `needs-user-review` ラベルは使用しない。ユーザー確認が必要な場合は assignee を追加する。ユーザーが AI の追加質問に返答した後、再度 AI レビューが必要と判断した場合は手動で `確認:issue-reviewer` を付け直す。

**status が `duplicate_merged` または `duplicate_closed` の場合（重複検出・クローズ済み）:**

Issue はすでにクローズされているため、ラベル付け替えは不要。
`処理中:issue-reviewer` ラベルのみ除去する（クローズ済み Issue には add-label が効かないため remove のみ）:

```bash
gh issue edit {N} --remove-label "$AI_MONITOR_LABEL_PROCESSING_ISSUE_REVIEWER" --remove-label "$AI_MONITOR_LABEL_CONFIRM_ISSUE_REVIEW" 2>/dev/null || true
```

### ステップ 5: 結果報告（TaskStop 受信後のみ実行）

**このステップは TaskStop を受け取った場合にのみ実行する。途中経過の報告は禁止。**

| 項目 | 内容 |
| --- | --- |
| レビュー件数 | 番号一覧 |
| ユーザー確認要 | assignee 追加/非追加の内訳 |
| re_review_needed | true/false の内訳 |
| waiting | 返答待ちで未処理の件数 |
| 重複検出 | `duplicate_merged` / `duplicate_closed` になった Issue 番号と移行先 Issue 番号 |

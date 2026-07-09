---
name: ai-monitor:pr-merger-auto
description: 確認:pr-merger ラベル付き PR を 1 件ずつ直列でマージする（Draft・Ready 問わずラベルのみで判断）
disable-model-invocation: false
---

# pr-merger-auto

`確認:pr-merger` ラベル付き PR をキューとして 1 件ずつ消化する（Draft・Ready 問わず）。
**並列実行は絶対にしない**（master 取り込みとマージが競合してバグるため）。

assignees が設定されている PR はスキップする（ユーザー確認待ち）。

## ループ継続制約（厳守）

- Monitorは何があっても絶対に止めない。
- ステップ 4 完了後（キューが空になった場合も含む）は**即座にステップ 0（Monitor）へ戻る。**
- **途中結果報告は禁止。** ステップ 4 の後処理が終わったら報告せず次のポーリングサイクルへ。
- ステップ 5 は TaskStop を受信したときにのみ実行する。

## タスク

### ステップ 0: Monitor でイベント待機

対象 PR が既に存在する場合はそのままステップ 1 へ進む。
存在しない場合は Monitor ツールで以下のポーリングスクリプトを実行し、対象が出現したらステップ 1 へ進む。

対象条件: `確認:pr-merger` ラベル付きの PR（Draft・Ready 問わず、`処理中:` で始まるラベル付きは除外）。

**ステップ 4 完了後（キューが空の場合も含む）はこのステップに戻り、Monitor を再起動してポーリングを継続する。**

```bash
# Monitor に渡すポーリングスクリプト
while true; do
  AVAILABLE=$(gh pr list --state open --label "$AI_MONITOR_LABEL_CONFIRM_PR_MERGER" \
    --json number,labels,assignees \
    --jq "[.[] | select(
      (.assignees | length) == 0 and
      (.labels | map(.name) | (map(startswith(\"処理中:\")) | any | not))
    )] | length" 2>/dev/null || echo 0)
  if [ "$AVAILABLE" -gt 0 ]; then
    echo "TRIGGER:pr-merger-auto:count=$AVAILABLE"
    break
  fi
  sleep 30
done
```

Monitor の stdout に `TRIGGER:pr-merger-auto` が来たらステップ 1 へ進む。
手動停止は TaskStop で行う。

### ステップ 1: マージ対象 PR を収集

```bash
gh pr list --state open --label "$AI_MONITOR_LABEL_CONFIRM_PR_MERGER" \
  --json number,title,headRefName,baseRefName,statusCheckRollup,labels,assignees --limit 50
```

`処理中:` で始まるラベル付きは除外。assignees が設定されている PR は除外（ユーザー確認待ち）。Draft/Ready は問わない。
`優先度:急ぎ` 付き PR を先頭に、次に `優先度:いつでも` 付き、それ以外は番号昇順でキューを形成する:

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

### ステップ 2: 上から 1 件取り出す

```bash
# 自身に依頼された確認ラベルを除去し、処理中ラベルを付与する
gh pr edit {N} \
  --remove-label "$AI_MONITOR_LABEL_CONFIRM_PR_MERGER" \
  --add-label "$AI_MONITOR_LABEL_PROCESSING_PR_MERGER"
# 紐づく Issue に 処理中:pr-merger を付与
ISSUE_N=$(gh pr view {N} --json body --jq '.body' | grep -oP '(?:Refs|Closes|Fixes) #\K[0-9]+' | head -1)
if [ -n "$ISSUE_N" ]; then
  gh issue edit "$ISSUE_N" --add-label "$AI_MONITOR_LABEL_PROCESSING_PR_MERGER"
fi
```

CI が failure なら failed へ。

### ステップ 3: pr-merger に委譲

[サブエージェントで実行・完了を待つ]
（戻り値: `{verdict, pr_number, branch, message}`）

入力:
- PR 番号 / タイトル / base / head
- リポジトリ root

### ステップ 4: 後処理

```bash
# 全 verdict 共通: Issue の 処理中:pr-merger を除去
ISSUE_N=$(gh pr view {N} --json body --jq '.body' | grep -oP '(?:Refs|Closes|Fixes) #\K[0-9]+' | head -1)
```

| verdict | 動作 |
| --- | --- |
| merged | `gh pr edit {N} --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_MERGER"`（マージは pr-merger が実施済み。PR は Close 済み）+ `gh issue edit "$ISSUE_N" --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_MERGER"` + Issue クローズ: `gh issue close "$ISSUE_N" --comment "PR #{N} のマージにより完了"` |
| conflict / failed | `GH_LOGIN="$(gh api user --jq '.login')" && gh pr edit {N} --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_MERGER" --add-label "$AI_MONITOR_LABEL_CONFIRM_PR_IMPLEMENT" --add-assignee "$GH_LOGIN" && gh pr comment {N} --body "{詳細}"` + `gh issue edit "$ISSUE_N" --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_MERGER"` |

ステップ 2 に戻ってキューが空になるまで繰り返す。
キューが空になったらステップ 0（Monitor）へ戻り、次のイベントを待機する。

### ステップ 5: 完了報告（TaskStop 受信後のみ実行）

**このステップは TaskStop を受け取った場合にのみ実行する。キューが空になっただけでは実行しない。**

| 項目 | 内容 |
| --- | --- |
| 処理 PR 件数 | カテゴリ別（merged / conflict / failed） |
| 残った PR | 各カテゴリの番号一覧 |

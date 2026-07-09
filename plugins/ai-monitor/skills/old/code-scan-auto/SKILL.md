---
name: ai-monitor:code-scan-auto
description: コードベースを観点ごとにスキャンし、見つかった問題を gh issue create で起票する
disable-model-invocation: false
---

# code-scan-auto

メインは観点を選んで `code-scanner` サブエージェントに振り分けるだけ。

## 環境変数

| 変数 | 既定 | 用途 |
| --- | --- | --- |
| `AI_MONITOR_CODE_SCAN_PARALLEL` | `5` | 並列起動するスキャナー数 |

## ループ継続制約（厳守）

- **完了を待たない。** `run_in_background: true` でサブエージェントを起動したら即座に制御を戻す。
- ステップ 4 完了後は**途中結果を報告せず**、次の処理サイクルへ進む。
- TaskStop を受け取った場合のみ最終報告を行う。
- Monitorは何があっても絶対に止めない。

## タスク

### ステップ 1: 既存 Issue を確認

```bash
gh issue list --state all --label "$AI_MONITOR_LABEL_AI_CODE_SCAN" --limit 50
```

直近の起票を取得し、観点の重複を避ける材料にする。

### ステップ 2: スキャン観点を N 件選ぶ

!`curl -fsSL "https://raw.githubusercontent.com/wiki/$(gh repo view --json nameWithOwner --jq '.nameWithOwner')/観点メニュー.md" 2>/dev/null || echo "[WARN] 観点メニュー Wiki ページを取得できませんでした"`

このメニューから既存 Issue とかぶらない観点を **N** 件（`AI_MONITOR_CODE_SCAN_PARALLEL`）選ぶ。

### ステップ 3: code-scanner をバックグラウンドで並列起動（完了を待たない・通知駆動）

**原則: 完了を待たない。** `run_in_background: true` でサブエージェントを起動したら即座に Monitor 監視に戻る。
完了通知（`<task-notification>`）を受けたら後処理（ステップ 4）を実行する。

観点ごとに `code-scanner` を 1 体ずつ `run_in_background: true` で並列起動する:
- 起動上限 **N**（`AI_MONITOR_CODE_SCAN_PARALLEL`）に達している場合は新規起動をキューイングし、1 体完了通知を受けたら次を起動する
- 起動後は即座に Monitor に制御を戻す

各サブエージェントに渡す入力: 観点（メニューから 1 件抜粋）

### ステップ 4: 通知ハンドラ（サブエージェント完了時に実行）

`code-scanner` からの完了通知（`<task-notification>`）を受信したら以下を実行する:
（戻り値: `{issue_number, issue_url, title}` を通知から取得）

全スキャナーの完了後（または最後の通知受信後）、1 件以上 Issue が起票されたら続けて `/ai-monitor:issue-review-auto` を呼び出して
新規 Issue を AI レビューしてしまう（`確認:issue-reviewer` 付きの Issue が対象）。

**完了後はユーザーへの途中報告を行わない。TaskStop を受け取るまで待機する。**

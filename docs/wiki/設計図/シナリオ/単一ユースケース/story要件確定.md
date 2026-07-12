# story要件確定

story-conductor が story Issue の本文（前提条件 / 概要 / 背景 / ユースケース要件）を確定する単一ユースケース。

対応モニター: `story-conductor`（初回呼び出し）

## 正常シナリオ

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | story Issue | `layer:story` + `確認:story-conductor` 付きで存在 | 親 epic と Sub-issue リンク済み・本文は空 |
| 2 | 親 epic Issue | ユースケース一覧 + 横断要件 確定済み | UC 番号との対応を背景に書く元ネタ |
| 3 | assignee | 未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator

  Note over GH: story Issue に 確認:story-conductor 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as story-conductor
  ORC->>MON: tmux セッション作成 + skill 起動
  participant REPO as リポジトリ
  activate MON
  MON->>GH: 親 epic の UC を特定・<br>4 セクション + UC<br>タイプ別観点の要件草案を<br>story Issue 本文に反映
  MON->>GH: story Issue に完了報告 + 確認事項を投稿
  MON->>GH: story Issue に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: story Issue にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: story Issue の本文修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: story Issue の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: story Issue の自分宛コメント一括 Resolve
  MON->>REPO: worktree + story/{slug} ブランチ作成 +<br>空 commit push
  MON->>GH: story Draft PR 作成（base=epic/{親 slug}・<br>本文は 紐づく Issue のみ）
  MON->>GH: story PR に 確認:single-scenario-writer 付与・<br>story Issue の 確認:story-conductor 除去
  deactivate MON
  Note over MON: セッションは story Issue close まで常駐
```

**期待動作:**
- story Issue 本文に `## 前提条件` / `## 概要` / `## 背景` / `## ユースケース要件` が揃っている
- `## 背景` に「親 epic #N の UC No.X「{UC 名}」に対応」の 1 行が含まれる
- 横断要件を参照する要件行の補足に `epic 横断要件 #N に基づく` が明記されている
- story Draft PR（base=epic/{親 slug}・本文は `## 紐づく Issue` のみ）が作成され、`確認:single-scenario-writer` が付与されている

## 異常シナリオ（該当なし）

なし。

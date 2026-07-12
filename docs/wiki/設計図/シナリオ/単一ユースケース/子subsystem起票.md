# 子subsystem起票

story-conductor（復帰呼び出し）が single-scenario-writer の完了報告を確認し、単一シナリオ確定を受けて次フェーズ（子 subsystem 起票）に進むと判断する単一ユースケース。UC の実装に必要な subsystem（FE / BE / 外部連携 等）を洗い出し、それぞれ子 Issue として起票する。

対応モニター: `story-conductor`（single-scenario-writer の完了報告コメントで復帰）

## 正常シナリオ

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | story Issue | `確認:story-conductor` 付与済み + single-scenario-writer の完了報告コメント（自分宛・未解決）あり | - |
| 2 | 単一 UC シナリオ | story ブランチに commit 済み | subsystem 洗い出しの元ネタ |
| 3 | assignee | 未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as orchestrator
  participant MON as story-conductor

  Note over MON: 既存セッションを継続利用
  Note over GH: story Issue に<br>確認:story-conductor 付与済み・<br>未解決の完了報告コメントあり
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: story Issue の完了報告を確認<br>（単一シナリオ確定 →<br>子 subsystem 起票に進むと判断）
  MON->>GH: 実装分担を分解・create_child_issue x M<br>（layer:subsystem +<br>確認:subsystem-conductor 付与）
  MON->>GH: story Issue 本文に<br>子 subsystem リンクを反映（update_body）
  MON->>GH: story Issue の完了報告コメントを Resolve
  MON->>GH: story Issue に起票結果の報告コメント投稿<br>（ユーザー宛・待機なし）
  MON->>GH: story Issue の 確認:story-conductor 除去<br>（役割終了・ユーザー承認なしの自動完了）
  deactivate MON
  Note over MON: セッションは story Issue close まで常駐
```

**期待動作:**
- 実装分担単位（1 subsystem = 1 対象システム）ごとの Issue が story の Sub-issue として存在する
- 各 subsystem Issue に `layer:subsystem` + `確認:subsystem-conductor` が付与されている
- story Issue のラベルが `layer:story` 系のみになっている（`確認:*` は除去、`議論中` 付与なし・assignee 設定なし）

## 異常シナリオ（該当なし）

なし。

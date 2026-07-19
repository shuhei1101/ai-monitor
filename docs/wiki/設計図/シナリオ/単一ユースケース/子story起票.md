# 子story起票

epic-conductor（復帰呼び出し）が complex-scenario-writer の完了報告を確認し、複合シナリオ確定を受けて次フェーズ（子 story 起票）に進むと判断する単一ユースケース。
確定済みユースケース一覧の各 UC に対応する子 story Issue を起票し、対応 story 列にリンクを埋める。

対応エージェント: `epic-conductor`（complex-scenario-writer の完了報告コメントで復帰）

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| epic Issue | `確認:epic-conductor` 付与済み + complex-scenario-writer の完了報告コメント（自分宛・未解決）あり | - |
| ユースケース一覧 | 全行 `対応 story` 列が `未起票` | - |
| assignee | 未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター
  participant MON as epic-conductor

  Note over MON: 既存セッションを継続利用
  Note over GH: epic Issue に 確認:epic-conductor 付与済み・<br>未解決の完了報告コメントあり
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: epic Issue の完了報告を確認<br>（複合シナリオ確定 →<br>子 story 起票に進むと判断）
  MON->>GH: create_child_issue x UC 数<br>（layer:story + 確認:story-conductor 付与）
  MON->>GH: epic Issue 本文の 対応 story 列に<br>#35;番号 反映（update_body）
  MON->>GH: epic Issue の完了報告コメントを Resolve
  MON->>GH: epic Issue に起票結果の報告コメント投稿<br>（ユーザー宛・待機なし）
  MON->>GH: epic Issue の 確認:epic-conductor 除去<br>（役割終了・ユーザー承認なしの自動完了）
  deactivate MON
  Note over MON: セッションは epic Issue close まで常駐
```

### 期待値

- ユースケース一覧の行数と同数の story Issue が epic の Sub-issue として存在する
- 各 story Issue に `layer:story` + `確認:story-conductor` が付与されている
- `対応 story` 列の `未起票` が全て `#番号` に置き換わっている
- epic Issue のラベルが `layer:epic` 系のみになっている（`確認:*` は除去、`議論中` 付与なし・assignee 設定なし）

## 異常シナリオ

なし

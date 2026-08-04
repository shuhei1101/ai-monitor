---
template_version: 2.1.0
---

# 子storyPR作成

epic-conductor（復帰呼び出し）が complex-scenario-writer の完了報告を確認し、複合シナリオ確定を受けて次フェーズ（子 story PR の作成）に進むと判断する単一ユースケース。

対応エージェント: `epic-conductor`（complex-scenario-writer の完了報告コメントで復帰）

- 対応テストファイル: `tests/e2e/単一ユースケース/test_子storyPR作成.py`

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| epic PR | `確認:epic-conductor` 付与済み + complex-scenario-writer の完了報告コメント（自分宛・未解決）あり | - |
| 複合 UC シナリオ | 成果物 PR が epic ブランチへマージ済み | story 分割の元ネタ |
| ユースケース一覧 | 全行 `対応 story` 列が `未作成` | - |
| assignee | 未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター
  participant MON as epic-conductor

  Note over MON: 既存セッションを継続利用
  Note over GH: epic PR に 確認:epic-conductor 付与済み・<br>未解決の完了報告コメントあり
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: epic PR の完了報告を確認<br>（複合シナリオ確定 →<br>子 story PR の作成に進むと判断）
  MON->>GH: UC 数だけブランチを作成<br>（base=epic ブランチ）
  MON->>GH: 各ブランチに Draft PR を作成<br>（layer:story + 親の リバースエンジニアリング<br>ラベル付与・確認ラベルなし）
  MON->>GH: 着手順の依存がある PR を<br>先行 PR の上に積んでスタックに接続<br>（対象が無ければ飛ばす）
  MON->>GH: epic PR 本文の 対応 story 列に<br>#35;番号 反映
  MON->>GH: 全 story PR に 確認:story-conductor 付与
  MON->>GH: epic PR の完了報告コメントを Resolve
  MON->>GH: epic PR の 確認:epic-conductor 除去<br>（役割終了・ユーザー承認なしの自動完了）
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- ユースケース一覧の行数と同数の story ブランチと Draft PR が存在する
- 各 story PR の base が epic ブランチになっている
- 各 story PR に `layer:story` + `確認:story-conductor` が付与されている
- ユースケース一覧に着手順の依存が無い場合、story PR 同士は積まれず、それぞれが epic PR の上に並列で接続されている
- 親 epic PR に `リバースエンジニアリング` ラベルが付いていた場合、全 story PR に引き継がれている（付いていなければ子にも付かない）
- `対応 story` 列の `未作成` が全て `#番号` に置き換わっている
- epic PR のラベルが `layer:epic` 系のみになっている（`確認:*` は除去、`議論中` 付与なし・assignee 設定なし）

## 異常シナリオ

なし

# Issue分解と子起票

ユーザーが起票した Issue を intake-issue-triager が作業単位に分解し、ユーザー承認を経て epic / story / subsystem / chore の Sub-issue を作成する単一ユースケース。

対応エージェント: `intake-issue-triager`

- 対応テストファイル: `tests/e2e/test_Issue分解と子起票.py`

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| intake Issue | ユーザー起票の Issue に `確認:intake-issue-triager` 付与済み | 本文はユーザーが書いたまま |
| assignee | 未設定 | エージェント起動条件 |
| モニター | 対象リポを polling 中 | - |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  U->>GH: Issue 起票 + 確認:intake-issue-triager 付与
  ORC-->>GH: polling（確認ラベルあり + assignee なし を検知）
  create participant MON as intake-issue-triager
  ORC->>MON: tmux セッション作成 + skill 起動
  activate MON
  MON-->>GH: 本文のキーワードで<br>関連 Issue / PR・シナリオ設計書を調査
  MON->>GH: intake Issue の本文を読み<br>作業単位に分解
  MON->>GH: intake Issue に layer:intake + type:* 付与
  MON->>GH: intake Issue にサブ Issue 案コメント +<br>確認事項投稿
  MON->>GH: intake Issue に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: intake Issue にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: intake Issue で案修正の返信 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: intake Issue の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: create_child_issue x 件数分<br>（layer:* + 確認:*-conductor 付与）
  MON->>GH: intake Issue の自分宛コメント一括 Resolve
  MON->>GH: intake Issue の 確認:intake-issue-triager 除去
  deactivate MON
  Note over MON: セッションは intake Issue close<br>（モニター直轄）まで常駐
```

### 期待値

- 承認された案と同数の Sub-issue が親 Issue に紐づいて存在する（`layer:epic` なら `確認:epic-conductor`、chore なら `確認:quick-implementer` が付与）
- intake Issue の本文がユーザー起票時のまま書き換わっていない
- intake Issue に `layer:intake` + `type:*` が残り、`確認:*` は除去済み
- 自分宛コメントが全て Resolve 済み

### 補足

- ユーザーがフィードバックコメント + assignee 外しのみで返した場合は応答ループ（案修正 → 再待機）。
  案はコメント上で管理し本文には書かない
- intake Issue のクローズはこの UC の責務外（全 Sub-issue closed を モニターが検知して close）

## 異常シナリオ

なし

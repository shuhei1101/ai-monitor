# epic要件確定

epic-conductor が epic Issue の本文（前提条件 / 概要 / 背景 / ユースケース一覧 / 横断要件）を確定し、実現可能性 PoC の要否と画面変更（新規作成 / レイアウト変更）の有無を判定する単一ユースケース。

対応エージェント: `epic-conductor`（初回呼び出し）

- 対応テストファイル: `tests/e2e/単一ユースケース/test_epic要件確定.py`

## 正常シナリオ（PoC 不要・画面変更なし）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| epic Issue | `layer:epic` + `確認:epic-conductor` 付きで存在 | 親 intake Issue と Sub-issue リンク済み・本文は空 |
| assignee | 未設定 | エージェント起動条件 |
| モニター | polling 中 | - |
| ユーザー回答 | 応答ループで PoC 不要・画面変更なしと回答する | 分岐を決定的に誘発（テストではユーザー役が固定回答） |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  Note over GH: epic Issue に 確認:epic-conductor 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as epic-conductor
  ORC->>MON: tmux セッション作成 + skill 起動
  participant REPO as リポジトリ
  activate MON
  MON->>GH: 親 intake から範囲抽出・<br>5 セクションの草案を epic Issue 本文に反映
  MON->>GH: epic Issue に完了報告 + 確認事項 +<br>PoC 要否・画面変更有無の質問を投稿
  MON->>GH: epic Issue に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: epic Issue にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: epic Issue の本文修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: epic Issue の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: epic Issue の自分宛コメント一括 Resolve
  MON->>GH: epic Issue の 確認:epic-conductor 除去
  alt PoC 不要・画面変更なし
    MON->>REPO: worktree + epic ブランチ作成<br>（{type}/epic/{ドメイン}）+ 空 commit push
    MON->>GH: epic Draft PR 作成（base=master・<br>本文は 紐づく Issue のみ）
    MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
    MON->>GH: epic PR に 確認:complex-scenario-writer 付与
  else PoC 不要・画面変更あり
    Note over MON: 正常シナリオ<br>（PoC 不要・画面変更あり）参照
  else PoC 必要
    Note over MON: 正常シナリオ<br>（PoC 必要判定）参照
  end
  deactivate MON
  Note over MON: セッションは epic Issue close まで常駐
```

### 期待値

- epic Issue 本文に `## 前提条件` / `## 概要` / `## 背景` / `## ユースケース一覧` / `## 横断要件` が揃っている
- ユースケース一覧の `対応 story` 列が全行 `未起票`
- `確認:epic-conductor` が除去され、epic Draft PR（本文は `## 紐づく Issue` のみ）が作成されて `確認:complex-scenario-writer` が付与されている
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
- 自分宛コメントが全て Resolve 済み

### 補足

- フィードバックループは Issue 側の応答ループ（本文修正 → 再待機）で回す

## 正常シナリオ（PoC 不要・画面変更あり）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 応答ループまで完了 | 5 セクション確定済み・`議論中` 除去済み（正常シナリオ（PoC 不要・画面変更なし）と同一の経過） | - |
| ユーザー回答 | PoC 不要・画面の新規作成 / レイアウト変更ありと回答済み | 分岐を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター
  participant MON as epic-conductor
  participant REPO as リポジトリ

  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: epic Issue の自分宛コメント一括 Resolve
  MON->>GH: epic Issue の 確認:epic-conductor 除去
  MON->>REPO: worktree + epic ブランチ作成<br>（{type}/epic/{ドメイン}）+ 空 commit push
  MON->>GH: epic Draft PR 作成（base=master・<br>本文は 紐づく Issue のみ）
  MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
  MON->>GH: epic PR に 確認:mock-designer 付与 +<br>指示コメント投稿（@mock-designer 宛・<br>画面方針の要点）
  deactivate MON
  Note over MON: セッションは epic Issue close まで常駐
```

### 期待値

- epic Draft PR（base=master・本文は `## 紐づく Issue` のみ）が作成され、`確認:mock-designer` と指示コメント（@mock-designer 宛・未解決）が付与・投稿されている
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている

## 正常シナリオ（PoC 必要判定）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 正常シナリオの応答ループまで完了 | 5 セクション確定済み・`議論中` 除去済み | - |
| PoC 要否 | epic の成立が前例のない技術機構に依存し、ユーザーが PoC 必要と回答済み | 例: 未検証のプロトコル連携・性能が成立条件 |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター
  participant MON as epic-conductor
  participant REPO as リポジトリ

  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: epic Issue の自分宛コメント一括 Resolve
  MON->>GH: epic Issue の 確認:epic-conductor 除去
  MON->>REPO: worktree + PoC ブランチ作成<br>（poc/epic/{ドメイン}/{テーマ}）+<br>空 commit push
  MON->>GH: PoC Draft PR 作成（base=master・<br>タイトル PoC: {検証テーマ}（epic #35;N）・<br>本文は 紐づく Issue のみ）
  MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
  MON->>GH: PoC PR に 確認:epic-poc-runner 付与 +<br>指示コメント投稿（@epic-poc-runner 宛・<br>検証テーマの背景 + 成立条件の想定）
  deactivate MON
  Note over MON: セッションは epic Issue close まで常駐
```

### 期待値

- PoC Draft PR（base=master・タイトル `PoC: {検証テーマ}（epic #N）`・本文は `## 紐づく Issue` のみ）が作成され、`確認:epic-poc-runner` と指示コメント（@epic-poc-runner 宛・未解決）が付与・投稿されている
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
- epic Draft PR は作成されない

## 異常シナリオ

なし

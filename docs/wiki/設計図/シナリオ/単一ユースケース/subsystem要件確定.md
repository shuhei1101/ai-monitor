# subsystem要件確定

subsystem-conductor が subsystem Issue の本文整形 + 現状調査（既存コード・関連テスト・関連 Issue/PR・再現ログ）+ システム要件（機能 / 非機能 / スコープ外）確定を行い、完了時に subsystem Draft PR を作成して architect に設計を引き渡す単一ユースケース。

対応エージェント: `subsystem-conductor`

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| subsystem Issue | `layer:subsystem` + `確認:subsystem-conductor` 付きで存在 | 親 story と Sub-issue リンク済み・本文は空 |
| 親 story Issue | ユースケース要件 + 単一 UC シナリオ確定済み | 担当範囲の元ネタ |
| assignee | 未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  Note over GH: subsystem Issue に<br>確認:subsystem-conductor 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as subsystem-conductor
  ORC->>MON: tmux セッション作成 + skill 起動
  participant REPO as リポジトリ
  activate MON
  MON->>REPO: 設計図 Wiki を起点に既存コードを調査<br>（関連 Issue / PR 収集のみサブエージェント並列）
  MON->>GH: 概要 / 背景 + 現状 セクションを<br>subsystem Issue 本文に反映
  MON->>GH: 機能・非機能要件の観点を洗い出し<br>→システム要件 SA セクションを<br>subsystem Issue 本文に反映
  MON->>GH: subsystem Issue に完了報告 +<br>確認事項を投稿
  MON->>GH: subsystem Issue に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: subsystem Issue にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: subsystem Issue の本文修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: subsystem Issue の 議論中 除去 +<br>assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: subsystem Issue の<br>自分宛コメント一括 Resolve
  MON->>REPO: worktree + subsystem ブランチ作成<br>（{type}/{scope}/{ドメイン}/{UC名}/{変更内容}）+<br>空 commit push
  MON->>GH: subsystem Draft PR 作成<br>（base=親 story ブランチ・<br>紐づく Issue + タスク一覧を記入）
  MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
  MON->>GH: subsystem PR にタスク一覧の確認コメント +<br>議論中 付与 + assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（タスクの修正指示がある間）
    U->>GH: subsystem PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: subsystem PR のタスク一覧を修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: subsystem PR の 議論中 除去 +<br>assignee 外し（タスクの承認）
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: subsystem PR の<br>自分宛コメント一括 Resolve
  MON->>GH: subsystem PR に 確認:architect 付与
  MON->>GH: subsystem Issue の<br>確認:subsystem-conductor 除去
  deactivate MON
  Note over MON: セッションは epic Issue close まで常駐
```

### 期待値

- 本文に `## 現状`（関連実装コード / 関連テスト / 関連 Issue/PR / 関連ドキュメント）と `## システム要件（SA）`（機能要件 / 非機能要件 / スコープ外）が揃っている
- バグ Issue の場合は `### 再現手順` と `### 既存テスト実行結果` も記録されている
- subsystem Draft PR（base=親 story ブランチ）が作成され、本文に `## 紐づく Issue` と `## タスク一覧`（Wiki 修正・実装・テスト実行の To Do）が記入されている
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
- タスク一覧の確認コメントが投稿されている
- subsystem PR に `確認:architect` が付与され、`確認:subsystem-conductor` が除去されている

### 補足

- 関連 Issue / PR の収集は `related-issue-finder` / `related-pr-finder` サブエージェントを並列起動（コードベース調査・要件観点の洗い出しはメインエージェントが直接実施）

## 異常シナリオ

なし

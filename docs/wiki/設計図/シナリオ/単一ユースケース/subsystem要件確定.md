# subsystem要件確定

subsystem-conductor が subsystem Issue の本文整形 + 現状調査（既存コード・関連テスト・関連 Issue/PR・再現ログ）+ システム要件（機能 / 非機能 / スコープ外）確定を行い、完了時に subsystem Draft PR を作成して画面あり / なしで次モニターを振り分ける単一ユースケース。

対応モニター: `subsystem-conductor`

## 正常シナリオ（画面なし判定）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | subsystem Issue | `layer:subsystem` + `確認:subsystem-conductor` 付きで存在 | 親 story と Sub-issue リンク済み・本文は空 |
| 2 | 親 story Issue | ユースケース要件 + 単一 UC シナリオ確定済み | 担当範囲の元ネタ |
| 3 | assignee | 未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator

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
  MON->>REPO: worktree + subsystem/{scope} ブランチ作成 +<br>空 commit push
  MON->>GH: subsystem Draft PR 作成（base=story/{親 slug}・<br>紐づく Issue + タスク一覧を記入）
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
  alt 画面なし
    MON->>GH: subsystem PR に 確認:architect 付与
  else 画面あり
    Note over MON: 正常シナリオ<br>（画面あり判定）参照
  end
  MON->>GH: subsystem Issue の<br>確認:subsystem-conductor 除去
  deactivate MON
  Note over MON: セッションは subsystem Issue close まで常駐
```

**期待動作:**
- 本文に `## 現状`（関連実装コード / 関連テスト / 関連 Issue/PR / 関連ドキュメント）と `## システム要件（SA）`（機能要件 / 非機能要件 / スコープ外）が揃っている
- バグ Issue の場合は `### 再現手順` と `### 既存テスト実行結果` も記録されている
- subsystem Draft PR（base=story/{親 slug}）が作成され、本文に `## 紐づく Issue` と `## タスク一覧`（Wiki 修正・実装・テスト実行の To Do）が記入されている
- タスク一覧の確認コメントが投稿され、ユーザー承認（`議論中` 除去）後に最初の工程の `確認:architect` が付与されている（画面なし判定）

### 補足

- 関連 Issue / PR の収集は `related-issue-finder` / `related-pr-finder` サブエージェントを並列起動（コードベース調査・要件観点の洗い出しはメインエージェントが直接実施）

## 正常シナリオ（画面あり判定）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | タスク一覧の承認まで完了 | 本文確定・PR 作成・タスク一覧承認済み（正常シナリオ（画面なし判定）と同一の経過） | - |
| 2 | 対象 subsystem | 画面実装を含む（FE 担当の実装単位） | 画面あり判定を誘発 |

### 図

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as orchestrator
  participant MON as subsystem-conductor

  Note over MON: 起動〜タスク一覧の承認までは<br>正常シナリオ（画面なし判定）と同一
  activate MON
  MON->>GH: subsystem PR に 確認:ui-designer 付与
  MON->>GH: subsystem Issue の<br>確認:subsystem-conductor 除去
  deactivate MON
  Note over MON: セッションは subsystem Issue close まで常駐
```

**期待動作:**
- subsystem Draft PR に `確認:ui-designer` が付与されている（UI設計 UC を経由してから SS 設計に進む）

## 異常シナリオ（該当なし）

なし。

# PoC結果確認

epic-conductor（復帰呼び出し）が epic-poc-runner の検証結果を確認し、問題なければ epic Draft PR を作成して次フェーズに引き継ぐ単一ユースケース。
PoC を指示した本人が結果を確認してから次へ進める（epic-poc-runner が勝手に次フェーズへ飛ばさない）。

対応モニター: `epic-conductor`（epic-poc-runner の完了報告コメントで復帰）

## 正常シナリオ（画面変更なし）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | PoC 完了 | PoC 結果が epic Issue 本文に記録済み・PoC PR は open | - |
| 2 | epic Issue | `確認:epic-conductor` 付与済み + epic-poc-runner の完了報告コメント（自分宛・未解決）あり | - |
| 3 | ユーザー回答 | 要件確定で画面変更なしと回答済み | 分岐を決定的に誘発 |
| 4 | assignee | 未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as orchestrator
  participant MON as epic-conductor

  Note over MON: 既存セッションを継続利用
  Note over GH: epic Issue に 確認:epic-conductor 付与済み・<br>未解決の完了報告コメントあり
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  participant REPO as リポジトリ
  activate MON
  MON->>GH: epic Issue の PoC 結果（本文）+<br>完了報告コメントを確認

  alt 結果に疑問なし
    MON->>GH: epic Issue の自分宛コメント一括 Resolve<br>（epic-poc-runner の完了報告コメント含む）
    MON->>GH: PoC PR close（マージなし・恒久記録）
    MON->>REPO: PoC ブランチ / worktree 削除
    MON->>REPO: worktree + epic/{slug} ブランチ作成 +<br>空 commit push
    MON->>GH: epic Draft PR 作成（base=master・<br>本文は 紐づく Issue のみ）
    MON->>GH: epic PR に 確認:complex-scenario-writer 付与
    MON->>GH: epic Issue の 確認:epic-conductor 除去
  else 結果に疑問あり
    Note over MON: 異常シナリオ（PoC 結果に疑問あり・<br>続行指示 / 再検証指示）参照
  end
  deactivate MON
  Note over MON: セッションは epic Issue close まで常駐
```

**期待動作:**
- epic Issue の自分宛コメント（epic-poc-runner の完了報告コメント含む）が全て Resolve 済み
- PoC PR（複数あれば全て）が closed（マージなし）、PoC ブランチ / worktree が削除済み
- epic Draft PR（base=master・本文は `## 紐づく Issue` のみ）が作成され、`確認:complex-scenario-writer` が付与されている
- `確認:epic-conductor` が除去されている

### 補足

- 疑問がなければユーザー承認は不要（AI 間のクッション確認として動く）

## 正常シナリオ（画面変更あり）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | 正常シナリオ（画面変更なし）と同一の起動・確認経過 | PoC 完了・完了報告コメントあり・結果に疑問なし | - |
| 2 | ユーザー回答 | 要件確定で画面の新規作成 / レイアウト変更ありと回答済み | 分岐を決定的に誘発 |

### 図

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as orchestrator
  participant MON as epic-conductor
  participant REPO as リポジトリ

  Note over MON: 起動〜PoC PR close・ブランチ削除までは<br>正常シナリオ（画面変更なし）と同一
  MON->>REPO: worktree + epic/{slug} ブランチ作成 +<br>空 commit push
  MON->>GH: epic Draft PR 作成（base=master・<br>本文は 紐づく Issue のみ）
  MON->>GH: epic PR に 確認:mock-designer 付与 +<br>指示コメント投稿（@mock-designer 宛・<br>画面方針の要点）
  MON->>GH: epic Issue の 確認:epic-conductor 除去
  Note over MON: セッションは epic Issue close まで常駐
```

**期待動作:**
- epic Draft PR（base=master・本文は `## 紐づく Issue` のみ）が作成され、`確認:mock-designer` と指示コメント（@mock-designer 宛・未解決）が付与・投稿されている

## 異常シナリオ（PoC 結果に疑問あり・続行指示）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | PoC 完了 | PoC 結果が epic Issue 本文に記録済み・PoC PR は open | - |
| 2 | 完了報告コメント | 本文の `## PoC 結果` と矛盾する内容を仕込む | 例: 実測値が成功条件未達なのに「成立」と結論 |
| 3 | epic Issue | `確認:epic-conductor` 付与済み | - |
| 4 | assignee | 未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator
  participant MON as epic-conductor

  MON->>GH: epic Issue の PoC 結果（本文）+<br>完了報告コメントを確認<br>（矛盾を検知）
  MON->>GH: epic Issue に質問コメント + 議論中 付与 +<br>assignee=ユーザー 設定
  U->>GH: epic Issue に回答コメント +<br>議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  Note over MON: 正常シナリオの完了処理に合流
```

**期待動作:**
- 質問コメントが投稿され、`議論中` + `assignee=ユーザー` で待機する（epic Draft PR はまだ作成されない）
- 続行指示（`議論中` 除去 + assignee 外し）で正常シナリオの完了処理に合流する（epic Draft PR 作成 + `確認:complex-scenario-writer` 付与）

## 異常シナリオ（PoC 結果に疑問あり・再検証指示）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | PoC 完了 | PoC 結果が epic Issue 本文に記録済み・PoC PR は open | - |
| 2 | 完了報告コメント | 本文の `## PoC 結果` と矛盾する内容を仕込む | 例: 実測値が成功条件未達なのに「成立」と結論 |
| 3 | epic Issue | `確認:epic-conductor` 付与済み | - |
| 4 | assignee | 未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator
  participant MON as epic-conductor

  MON->>GH: epic Issue の PoC 結果（本文）+<br>完了報告コメントを確認<br>（矛盾を検知）
  MON->>GH: epic Issue に質問コメント + 議論中 付与 +<br>assignee=ユーザー 設定
  U->>GH: epic Issue に再検証指示コメント +<br>議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  MON->>GH: epic Issue の未解決の<br>再検証指示コメントを確認
  MON->>GH: PoC PR に再検証指示コメント投稿<br>（@epic-poc-runner 宛・ユーザー指示の要約）
  MON->>GH: 同一 PoC PR に 確認:epic-poc-runner 再付与<br>（PR・ブランチは保持したまま差し戻し）
```

**期待動作:**
- 質問コメントが投稿され、`議論中` + `assignee=ユーザー` で待機する（epic Draft PR はまだ作成されない）
- 再検証指示で**同一 PoC PR** に `確認:epic-poc-runner` が再付与され、再検証指示コメント（@epic-poc-runner 宛・未解決）が投稿される（PR 再作成なし・検証履歴が同一 PR に積まれる）
- PoC PR・ブランチは close / 削除されない

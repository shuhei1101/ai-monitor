# 全体UI設計

mock-designer が epic 全体の画面の方向性 — 画面一覧（新規 / 変更の洗い出し）・画面遷移の全体像・新規 / 変更画面のモック — を確定する単一ユースケース。
画面は複数 UC で共有されるため、UC / subsystem に分解する前・複合シナリオを書く前に epic レベルで方向性をユーザーと合意する（設計トップダウンの V 字原則）。いきなりモックは作らず、**方針の合意 → モック作成 → モックの合意** の 2 ゲートで進める。

対応モニター: `mock-designer`（画面の新規作成 / レイアウト変更を含む epic のみ）

## 正常シナリオ

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | epic PR | `確認:mock-designer` 付与済み + epic-conductor の指示コメント（自分宛・未解決）あり | - |
| 2 | epic Issue | ユースケース一覧・横断要件 確定済み | 画面一覧の元ネタ |
| 3 | assignee | PR に未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator

  Note over GH: epic PR に 確認:mock-designer 付与済み・<br>未解決の指示コメントあり
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as mock-designer
  ORC->>MON: tmux セッション作成 + skill 起動
  participant REPO as リポジトリ
  activate MON
  MON->>GH: 親 epic の UC 一覧・横断要件を確認
  MON->>REPO: 既存画面・共通コンポーネント調査
  MON->>GH: epic PR に画面の変更・作成方針<br>（画面一覧 +<br>各画面のラフ構成 + 遷移全体像）を提案コメント +<br>議論中 付与 + assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（方針への修正要望がある間）
    U->>GH: epic PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: epic PR で方針案修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: epic PR の 議論中 除去 +<br>assignee 外し（方針の確定）
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: epic PR の自分宛コメント一括 Resolve
  MON->>REPO: 確定した方針でモック作成 →<br>docs/mock 配下に commit push
  MON->>GH: epic PR に 1 画面 = 1 コメントで<br>モック URL 共有 + 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（モックへの修正要望がある間）
    U->>GH: epic PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>REPO: モック修正 commit push
    MON->>GH: epic PR の assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: epic PR の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: UI 設計（画面一覧 / 画面遷移 / モック）を<br>epic PR 本文に反映
  MON->>GH: epic PR の自分宛コメント一括 Resolve<br>（指示コメント含む）
  MON->>GH: epic PR の 確認:mock-designer 除去
  MON->>GH: 親 epic Issue に 確認:epic-conductor 付与 +<br>完了報告コメント投稿（@epic-conductor 宛・<br>確認後の Resolve 依頼付き）
  deactivate MON
  Note over MON: セッションは epic PR close / merge まで常駐
```

**期待動作:**
- epic PR 本文に `## UI 設計`（`### 画面一覧` / `### 画面遷移` / `### モック`）が記録されている
- モックが `docs/mock/pages/{画面名}/issues/{epic番号}/{案名}/` に commit され、コメントに URL が共有されている
- `確認:mock-designer` が除去され、親 epic Issue に `確認:epic-conductor` + 完了報告コメント（@epic-conductor 宛・未解決）が付与・投稿されている
- epic PR の自分宛コメント（指示コメント含む）が全て Resolve 済み

### 補足

- モックの配置・配信は `規約/モック画面構成.md` 準拠（epic ブランチに push し、raw.githack.com の URL で共有）

## 異常シナリオ（該当なし）

なし。方針・モックへの修正要望は応答ループで処理する。

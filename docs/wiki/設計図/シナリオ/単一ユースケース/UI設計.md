# UI設計

ui-designer が、epic の全体UI設計で確定した画面の方向性を前提に、担当 UC の組み込み詳細を FE 設計 Wiki（フロントエンド結合 → モジュール構成）としてタスク一覧の上流順に 1 ページずつ作成し、応答ループでユーザーと確定させる単一ユースケース。画面ありの subsystem のみ通る。

対応モニター: `ui-designer`

## 正常シナリオ

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | subsystem Draft PR | `確認:ui-designer` 付与済み・`## タスク一覧` 承認済み | 画面あり判定済み |
| 2 | subsystem Issue | SA（機能 / 非機能要件）確定済み | 画面要素の元ネタ |
| 3 | 画面の方向性 | 新規作成 / レイアウト変更がある場合は epic の全体UI設計で確定済み | モックも epic 側で作成済み |
| 4 | assignee | PR に未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator

  Note over GH: subsystem PR に 確認:ui-designer 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as ui-designer
  ORC->>MON: tmux セッション作成 + skill 起動
  participant REPO as リポジトリ
  activate MON
  MON->>GH: 紐づく Issue の SA<br>（機能 / 非機能要件）を確認
  MON->>GH: epic の UI 設計<br>（画面一覧 / 遷移 / モック）を確認
  MON->>REPO: 既存画面・共通コンポーネント調査

  loop タスク一覧の設計 Wiki ごと<br>（フロントエンド結合 →<br>モジュール構成 の上流順）
    MON->>REPO: 対象 Wiki を作成 / 更新して commit push
    MON->>GH: subsystem PR に画面構成 / 遷移の提案コメント +<br>議論中 付与 + assignee=ユーザー 設定
    deactivate MON

  loop 応答ループ（構成への修正要望がある間）
    U->>GH: subsystem PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: subsystem PR で構成案修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: subsystem PR の 議論中 除去 +<br>assignee 外し（UI 案の承認）
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: subsystem PR の<br>自分宛コメント一括 Resolve
  MON->>REPO: 合意した画面構成 / 遷移で<br>FE 設計 Wiki を commit push<br>（フロントエンド結合 / モジュール構成）
  MON->>GH: subsystem PR に Wiki 更新の報告コメント +<br>議論中 付与 + assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（Wiki への修正指示がある間）
    U->>GH: subsystem PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>REPO: Wiki 修正 commit push
    MON->>GH: subsystem PR の<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: subsystem PR の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: subsystem PR の<br>自分宛コメント一括 Resolve
  MON->>GH: subsystem PR の 確認:ui-designer 除去
  MON->>GH: 親 subsystem Issue に<br>確認:subsystem-conductor 付与 +<br>完了報告コメント投稿<br>（@subsystem-conductor 宛・<br>確認後の Resolve 依頼付き）
  deactivate MON
  Note over MON: セッションは subsystem PR close / merge まで常駐
```

**期待動作:**
- FE 設計 Wiki（`設計図/フロントエンド結合/{論理名}.md` / `設計図/モジュール構成/{分類}.md`）が合意した画面構成 / 遷移で subsystem ブランチに commit されている
- 親 subsystem Issue に `確認:subsystem-conductor` + 完了報告コメント（@subsystem-conductor 宛・未解決）が付与・投稿されている
- 自分宛コメントが全て Resolve 済み

## 異常シナリオ

なし。

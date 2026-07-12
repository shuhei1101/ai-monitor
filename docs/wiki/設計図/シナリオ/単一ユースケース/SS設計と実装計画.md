# SS設計と実装計画

architect が BE 設計 Wiki（ER図 → バックエンド結合 → モジュール構成）をタスク一覧の上流順に 1 ページずつ作成し、応答ループでユーザーと確定させる単一ユースケース。ライブラリ選定で必要なら PoC（カテゴリ A〜E）も本 UC 内で実施する。

対応モニター: `architect`

## 正常シナリオ

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | subsystem Draft PR | `確認:architect` 付与済み・`## タスク一覧` 承認済み | 画面ありの場合は FE 設計 Wiki 確定済み |
| 2 | subsystem Issue | SA 確定済み | 設計の元ネタ |
| 3 | assignee | PR に未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator

  Note over GH: subsystem PR に 確認:architect 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as architect
  ORC->>MON: tmux セッション作成 + skill 起動
  participant REPO as リポジトリ
  activate MON
  MON->>GH: 紐づく Issue の SA<br>（機能 / 非機能要件）を確認
  MON->>REPO: 領域別アーキ調査<br>（ライブラリ調査のみサブエージェント並列）

  loop タスク一覧の設計 Wiki ごと（ER図 →<br>バックエンド結合 → モジュール構成 の上流順）
    MON->>REPO: 対象 Wiki を作成 / 更新して commit push
    MON->>GH: subsystem PR に設計の提案コメント<br>（割れる論点は複数案比較 + 推奨）+<br>議論中 付与 + assignee=ユーザー 設定
    deactivate MON

    loop 応答ループ（修正指示がある間）
      U->>GH: subsystem PR にフィードバックコメント +<br>assignee 外し
      ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
      ORC->>MON: 既存セッションへ送信
      activate MON
      MON->>REPO: Wiki 修正 commit push
      alt ライブラリ選定論点あり
        Note over MON: 正常シナリオ<br>（ライブラリ PoC あり）参照
      end
      MON->>GH: subsystem PR の<br>assignee=ユーザー 再設定
      deactivate MON
    end

    U->>GH: subsystem PR の 議論中 除去 +<br>assignee 外し（当該 Wiki の確定）
    ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: subsystem PR の<br>自分宛コメント一括 Resolve
  end

  MON->>GH: subsystem PR の 確認:architect 除去
  MON->>GH: 親 subsystem Issue に<br>確認:subsystem-conductor 付与 +<br>完了報告コメント投稿<br>（@subsystem-conductor 宛・<br>確認後の Resolve 依頼付き）
  deactivate MON
  Note over MON: セッションは subsystem PR close / merge まで常駐
```

**期待動作:**
- タスク一覧の担当分の BE 設計 Wiki（`設計図/ER図/{分類}.md` / `設計図/バックエンド結合/{論理名}.md` / `設計図/モジュール構成/{分類}.md`）が上流順に 1 ページずつ確定され、subsystem ブランチに commit されている
- ライブラリ PoC を実施した場合は PoC PR が closed（マージなし）で残り、PoC worktree / ブランチが削除済み
- 親 subsystem Issue に `確認:subsystem-conductor` + 完了報告コメント（@subsystem-conductor 宛・未解決）が付与・投稿されている
- 自分宛コメントが全て Resolve 済み

## 正常シナリオ（タスク一覧に ER図 なし）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | subsystem Draft PR | `確認:architect` 付与済み・`## タスク一覧` 承認済み | - |
| 2 | タスク一覧 | 設計タスクが バックエンド結合・モジュール構成 のみ | DB 変更を伴わない subsystem。分岐を決定的に誘発 |
| 3 | assignee | PR に未設定 | モニター起動条件 |

### 図

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as orchestrator
  participant MON as architect

  Note over MON: 起動〜領域別アーキ調査までは<br>正常シナリオと同一
  activate MON
  MON->>GH: subsystem PR の タスク一覧 を読み<br>担当分（バックエンド結合・<br>モジュール構成の 2 件）を把握

  loop タスク一覧の設計 Wiki ごと<br>（バックエンド結合 →<br>モジュール構成 の 2 周のみ）
    Note over MON: 作成〜確定の手順は<br>正常シナリオと同一
  end

  MON->>GH: subsystem PR の 確認:architect 除去
  MON->>GH: 親 subsystem Issue に<br>確認:subsystem-conductor 付与 +<br>完了報告コメント投稿<br>（@subsystem-conductor 宛・<br>確認後の Resolve 依頼付き）
  deactivate MON
```

**期待動作:**
- バックエンド結合 → モジュール構成 の 2 ページだけが確定・commit されている
- `設計図/ER図/` 配下への commit が存在しない（タスク一覧にない Wiki は作成されない）
- 親 subsystem Issue に `確認:subsystem-conductor` + 完了報告コメントが付与・投稿されている

## 正常シナリオ（ライブラリ PoC あり）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | 設計の応答ループ中 | バックエンド結合 または モジュール構成 の応答ループ中にライブラリ選定論点が発生 | 例: LLM クライアントの採用 |
| 2 | 採用候補 | 未経験のライブラリで PoC 要否判定カテゴリ（A〜E）に該当 | PoC を誘発 |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator
  participant MON as architect
  participant REPO as リポジトリ

  Note over MON: 設計の応答ループ中に<br>ライブラリ選定論点が発生
  activate MON
  MON->>MON: 候補列挙 + 候補ごとの調査<br>（library-finder / library-researcher 並列）
  MON->>GH: subsystem PR に候補比較 +<br>検証観点の提案コメント +<br>assignee=ユーザー 設定
  deactivate MON

  U->>GH: 候補・検証観点に合意コメント +<br>assignee 外し
  ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>REPO: 候補ごとに PoC worktree 作成<br>（poc/{issue#35;}-{lib}・リモート push なし）
  MON->>REPO: 最小 PoC コードで動作検証<br>（1 候補 = 1 サブエージェント並列）
  MON->>GH: subsystem PR に候補ごとの<br>動作結果・所感コメント +<br>assignee=ユーザー 設定
  deactivate MON

  U->>GH: 採用ライブラリの決定コメント +<br>assignee 外し
  ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>REPO: 外部ライブラリ/README.md に行追加 +<br>外部ライブラリ/{lib名}.md 作成 commit push
  MON->>REPO: PoC worktree と<br>ローカルブランチを全て削除
  MON->>GH: subsystem PR の<br>assignee=ユーザー 再設定
  deactivate MON
  Note over MON: 設計の応答ループに合流
```

**期待動作:**
- `外部ライブラリ/README.md` の行と `外部ライブラリ/{lib名}.md` が subsystem ブランチに commit されている
- PoC worktree・ローカルブランチが全て削除済み（リモートに PoC ブランチは作られない）
- 候補比較・検証結果・採用判断の経緯がコメントに残っている


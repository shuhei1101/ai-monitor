# SS設計

architect が設計 Wiki（インターフェース → ER図 → 画面構成 → バックエンド結合 / フロントエンド結合（フロー）→ モジュール構成）をタスク一覧の上流順に 1 ページずつ作成し、応答ループでユーザーと確定させる単一ユースケース。
BE / FE の設計 Wiki とも architect が担当する（画面ありの subsystem は epic の全体UI設計で確定した画面方向性を前提にフロントエンド結合を書く）。
後続 subsystem が本 subsystem のインターフェースに依存する場合は、インターフェース確定時に subsystem-conductor へインターフェース確定報告を投稿する（待機なし・設計は継続）。
ライブラリ選定で必要なら PoC（カテゴリ A〜E）も本 UC 内で実施する。
全 Wiki 確定後は内部パイプラインの指揮役として tester にタスクを割り当てる。
配下 worker（tester / implementer）から設計の差し戻しを受けた場合も本 UC で設計 Wiki を修正して差し戻し元に返す。

対応エージェント: `architect`

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| subsystem Draft PR | `確認:architect` 付与済み・`## タスク一覧` 承認済み | - |
| subsystem Issue | SA 確定済み | 設計の元ネタ |
| assignee | PR に未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  Note over GH: subsystem PR に 確認:architect 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as architect
  ORC->>MON: tmux セッション作成 + skill 起動
  participant REPO as リポジトリ
  activate MON
  MON->>GH: 紐づく Issue の SA<br>（機能 / 非機能要件）を確認
  MON->>REPO: 領域別アーキ調査<br>（ライブラリ調査のみサブエージェント並列）

  loop タスク一覧の設計 Wiki ごと<br>（インターフェース → ER図 → 画面構成 →<br>バックエンド結合 / フロントエンド結合 →<br>モジュール構成 の上流順）
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
        Note over MON: ライブラリ選定を実施<br>（採用決定後にループへ合流）
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

  MON->>GH: タスク一覧の設計タスクに<br>チェックを入れる
  MON->>GH: subsystem PR の 確認:architect 除去
  MON->>GH: subsystem PR に 確認:tester 付与<br>（テスト作成タスクの割り当て）
  deactivate MON
  Note over MON: セッションは epic Issue close まで常駐
```

### 期待値

- タスク一覧の担当分の設計 Wiki（`設計図/ER図/{分類}.md` / `設計図/画面構成/{画面名}.md` / `設計図/バックエンド結合/{論理名}.md` / `設計図/フロントエンド結合/{論理名}.md` / `設計図/モジュール構成/{サブシステム}/{分類}.md`）が上流順に 1 ページずつ確定され、subsystem ブランチに commit されている
- `## タスク一覧` の設計タスクがチェック済み
- subsystem PR に `確認:tester` が付与され、`確認:architect` が除去されている
- 自分宛コメントが全て Resolve 済み

## 正常シナリオ（後続 subsystem へのインターフェース確定報告）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| subsystem Draft PR | `確認:architect` 付与済み・`## タスク一覧` 承認済み | 先行 subsystem（例: BE） |
| 親 story Issue | 本文の依存順に `未起票` の後続 subsystem（例: FE）あり | 報告を誘発 |
| assignee | PR に未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター
  participant MON as architect

  Note over MON: 起動〜インターフェースの設計・<br>応答ループは正常シナリオと同一
  U->>GH: subsystem PR の 議論中 除去 +<br>assignee 外し（インターフェースの確定）
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: subsystem PR の<br>自分宛コメント一括 Resolve
  MON->>GH: subsystem PR に<br>確認:subsystem-conductor 付与 +<br>インターフェース確定報告コメント投稿<br>（@subsystem-conductor 宛・待機なし）
  Note over MON: 以降（ER図 → 結合フロー →<br>モジュール構成）は正常シナリオと同一<br>（設計を継続）
  deactivate MON
```

### 期待値

- `設計図/バックエンド結合/{論理名}.md` の `## インターフェース` が確定され、subsystem ブランチに commit されている
- subsystem PR に `確認:subsystem-conductor` + インターフェース確定報告コメント（@subsystem-conductor 宛・未解決）が付与・投稿されている
- subsystem PR の `確認:architect` は保持されている（設計続行中）

## 正常シナリオ（タスク一覧に ER図 なし）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| subsystem Draft PR | `確認:architect` 付与済み・`## タスク一覧` 承認済み | - |
| タスク一覧 | 設計タスクが バックエンド結合・モジュール構成 のみ | DB 変更を伴わない subsystem。分岐を決定的に誘発 |
| assignee | PR に未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター
  participant MON as architect

  Note over MON: 起動〜領域別アーキ調査までは<br>正常シナリオと同一
  activate MON
  MON->>GH: subsystem PR の タスク一覧 を読み<br>担当分（バックエンド結合・<br>モジュール構成の 2 件）を把握

  loop タスク一覧の設計 Wiki ごと<br>（インターフェース →<br>バックエンド結合（フロー）→<br>モジュール構成）
    Note over MON: 作成〜確定の手順は<br>正常シナリオと同一
  end

  MON->>GH: タスク一覧の設計タスクに<br>チェックを入れる
  MON->>GH: subsystem PR の 確認:architect 除去
  MON->>GH: subsystem PR に 確認:tester 付与<br>（テスト作成タスクの割り当て）
  deactivate MON
```

### 期待値

- バックエンド結合（インターフェース + フロー）→ モジュール構成 の 2 ページだけが確定・commit されている
- `設計図/ER図/` 配下への commit が存在しない（タスク一覧にない Wiki は作成されない）
- subsystem PR に `確認:tester` が付与され、`確認:architect` が除去されている

## 正常シナリオ（差し戻しからの設計修正）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| subsystem PR | `確認:architect` 付与済み + tester / implementer の差し戻し報告コメント（設計の見直し・自分宛・未解決）あり | - |
| assignee | PR に未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター
  participant MON as architect
  participant REPO as リポジトリ

  Note over MON: 既存セッションを継続利用
  Note over GH: subsystem PR に 確認:architect 付与済み・<br>未解決の差し戻し報告コメントあり
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（設計修正）
  activate MON
  MON->>REPO: 設計 Wiki を修正して commit push
  MON->>GH: 差し戻し報告コメントに修正内容を返信追記<br>（修正 commit の ID + ユーザーへの確認依頼）+<br>議論中 付与 + assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: subsystem PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>REPO: Wiki 修正 commit push
    MON->>GH: 同スレッドに修正内容を返信追記 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: subsystem PR の 議論中 除去 +<br>assignee 外し（修正の確定）
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: 差し戻し報告コメントに再開指示を返信追記<br>（@{差し戻し元} 宛・修正 commit を参照）
  MON->>GH: subsystem PR の 確認:architect 除去
  MON->>GH: subsystem PR に<br>確認:{差し戻し元 worker} を再付与
  deactivate MON
```

### 期待値

- 設計 Wiki の修正 commit が subsystem ブランチに積まれている（修正はユーザー承認済み）
- 差し戻し報告コメントのスレッドに修正内容（修正 commit の ID）と再開指示（@{差し戻し元} 宛）が返信追記されている（スレッドは未解決のまま = 差し戻し元 worker が処理時に Resolve する）
- subsystem PR に `確認:{差し戻し元 worker}`（例: `確認:tester`）が付与され、`確認:architect` が除去されている

## 異常シナリオ

なし

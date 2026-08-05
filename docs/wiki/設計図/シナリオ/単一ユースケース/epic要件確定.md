---
template_version: 2.1.0
---

# epic要件確定

epic-conductor が epic PR の本文（概要 / 背景 / ユースケース一覧 / 横断要件）を確定し、実現可能性 PoC の要否と画面変更（新規作成 / レイアウト変更）の有無を判定する単一ユースケース。

対応エージェント: `epic-conductor`（初回呼び出し）

- 対応テストファイル: `tests/e2e/単一ユースケース/test_epic要件確定.py`

## 正常シナリオ（PoC 不要・画面変更なし）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| epic PR | `layer:epic` + `確認:epic-conductor` 付きの Draft PR が存在 | ブランチと PR は intake-issue-triager が作成済み・本文は `## 紐づく Issue` のみ |
| assignee | 未設定 | エージェント起動条件 |
| モニター | polling 中 | - |
| ユーザー回答 | 応答ループで PoC 不要・画面変更なしと回答する | 分岐を決定的に誘発（テストではユーザー役が固定回答） |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  Note over GH: epic PR に 確認:epic-conductor 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as epic-conductor
  ORC->>MON: tmux セッション作成 +<br>フェーズドキュメント注入
  participant REPO as リポジトリ
  activate MON
  MON-->>GH: 紐づく Issue から intake の本文を読み<br>対象範囲を抽出
  MON->>GH: 要件 4 セクションの草案を<br>epic PR 本文に反映
  MON->>GH: epic PR に確認事項コメント<br>（本文から一意に定まらない論点のみ）を投稿
  MON->>GH: epic PR に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: epic PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: epic PR の本文修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: epic PR の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: epic PR の自分宛コメント一括 Resolve
  MON->>GH: epic PR 本文に タスク一覧 を追記
  alt PoC 不要・画面変更なし
    MON->>REPO: 複合UCシナリオの成果物ブランチ作成<br>（docs/epic/{ドメイン}/scenario・<br>base=epic ブランチ）+ 空 commit push
    MON->>GH: 成果物 Draft PR 作成<br>（base=epic ブランチ・本文は 紐づく Issue）
    MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
    MON->>GH: 成果物 PR に 確認:complex-scenario-writer 付与
    MON->>GH: epic PR の 確認:epic-conductor 除去
  else PoC 不要・画面変更あり
    Note over MON: 正常シナリオ<br>（PoC 不要・画面変更あり）参照
  else PoC 必要
    Note over MON: 正常シナリオ<br>（PoC 必要判定）参照
  end
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- epic PR 本文に `## 概要` / `## 背景` / `## ユースケース一覧` / `## 横断要件` が揃っている
- ユースケース一覧の `対応 story` 列が全行 `未作成`
- ユースケース一覧の `変更種別` 列が全行 `新規` / `変更` / `削除` のいずれかで埋まっている（未記入の行がない）
- epic PR 本文の `## タスク一覧` に複合 UC シナリオの作成 / 修正・シナリオ索引の更新・複合 UC E2E テストの実行が列挙され、全行が未チェック（チェックは各行を担当した作業者が入れる）
- 複合UCシナリオの成果物ブランチと Draft PR が作成され、base が epic ブランチになっている
- 成果物 PR に `確認:complex-scenario-writer` が付与され、epic PR からは `確認:epic-conductor` が除去されている
- 成果物 PR 本文の `## 紐づく Issue` に起点の intake Issue の番号が入っている
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
- 自分宛コメントが全て Resolve 済み

## 正常シナリオ（確認事項なし）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| epic PR | `layer:epic` + `確認:epic-conductor` 付きの Draft PR が存在 | 本文は `## 紐づく Issue` のみ |
| 起点の intake Issue | 対象範囲・PoC 要否・画面変更の有無・複合 UC への影響が本文から一意に読み取れる内容で書かれている | 確認事項が 0 件になる状況を決定的に誘発 |
| 起点の intake Issue の対象範囲 | 記述が 1 操作に閉じており、導かれるユースケースが 1 件になる | 横断要件が定型の `なし（理由）` になる状況を決定的に誘発 |
| 既存の設計書 | 対象の複合 UC シナリオが epic ブランチに存在する | 修正箇所の有無を判定する材料 |
| assignee | 未設定 | エージェント起動条件 |
| モニター | polling 中 | - |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター
  participant REPO as リポジトリ

  Note over GH: epic PR に 確認:epic-conductor 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as epic-conductor
  ORC->>MON: tmux セッション作成 +<br>フェーズドキュメント注入
  activate MON
  MON-->>GH: 紐づく Issue から範囲抽出
  MON->>GH: 要件 4 セクションの草案を<br>epic PR 本文に反映
  MON-->>REPO: 既存の複合 UC シナリオと<br>照合して修正箇所の有無を判定
  MON->>MON: 判断が分かれる論点が無く<br>複合 UC の修正も不要と確定
  MON->>GH: epic PR に確認事項コメントを投稿<br>（質問せずに置いた前提を明示・議論中 は付けない）
  deactivate MON

  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（子storyPR作成）
  activate MON
  MON->>REPO: UC 数だけ story ブランチ作成<br>（base=epic ブランチ）
  MON->>GH: 各ブランチに Draft PR 作成 +<br>確認:story-conductor 付与
  MON->>GH: epic PR の 確認:epic-conductor 除去
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- 確認事項コメントが 1 件も投稿されていない（本文から一意に定まる論点を質問していない）
- `## ユースケース一覧` が 1 行（起点の intake の対象範囲が 1 操作に閉じているため）
- `## 横断要件` が定型の `なし（本 epic のユースケースは 1 件のため、ユースケース間を横断する要件は発生しない）` になっている（要件の表を書いていない）
- `議論中` が付与されず assignee も設定されていない（ユーザーを止めずに通り抜けている）
- 確認事項コメントに、質問せずに前提として置いた判断とその根拠が書かれている
- 複合UCシナリオの成果物ブランチと PR が作られていない（epic ブランチ上で作業する担当が居ないため）
- epic PR 本文に `## タスク一覧` が無い
- story ブランチと Draft PR が作成され `確認:story-conductor` が付与されている
- epic PR から `確認:epic-conductor` が除去されている

## 正常シナリオ（PoC 不要・画面変更あり）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 応答ループまで完了 | 要件 4 セクション確定済み・`議論中` 除去済み（正常シナリオ（PoC 不要・画面変更なし）と同一の経過） | - |
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
  MON->>GH: epic PR の自分宛コメント一括 Resolve
  MON->>GH: epic PR 本文に タスク一覧 を追記
  MON->>REPO: モックの成果物ブランチ作成<br>（docs/epic/{ドメイン}/mock・<br>base=epic ブランチ）+ 空 commit push
  MON->>GH: 成果物 Draft PR 作成<br>（base=epic ブランチ・本文は 紐づく Issue）
  MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
  MON->>GH: 成果物 PR に 指示コメント投稿（@mock-designer 宛・<br>画面方針の要点） +<br>確認:mock-designer 付与
  MON->>GH: epic PR の 確認:epic-conductor 除去
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- モックの成果物ブランチと Draft PR（base=epic ブランチ）が作成され、`確認:mock-designer` と指示コメント（@mock-designer 宛・未解決）が付与・投稿されている
- epic PR 本文の `## タスク一覧` の先頭にモック作成が並び、続けて複合 UC シナリオの作成 / 修正・シナリオ索引の更新・複合 UC E2E テストの実行が列挙されている
- 複合UCシナリオの成果物ブランチはまだ作られていない（モック完了後に作る）
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている

## 正常シナリオ（PoC 必要判定）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 正常シナリオの応答ループまで完了 | 要件 4 セクション確定済み・`議論中` 除去済み | - |
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
  MON->>GH: epic PR の自分宛コメント一括 Resolve
  MON->>REPO: PoC ブランチ作成<br>（poc/epic/{ドメイン}/{テーマ}・<br>base=epic ブランチ）+ 空 commit push
  MON->>GH: PoC Draft PR 作成（base=epic ブランチ・<br>タイトル PoC: {検証テーマ}（epic #35;N）・<br>本文は 紐づく Issue のみ）
  MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
  MON->>GH: PoC PR に 指示コメント投稿（@epic-poc-runner 宛・<br>検証テーマの背景 + 成立条件の想定） +<br>確認:epic-poc-runner 付与
  MON->>GH: epic PR の 確認:epic-conductor 除去
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- PoC Draft PR（base=epic ブランチ・タイトル `PoC: {検証テーマ}（epic #N）`・本文は `## 紐づく Issue` のみ）が作成され、`確認:epic-poc-runner` と指示コメント（@epic-poc-runner 宛・未解決）が付与・投稿されている
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
- モックと複合UCシナリオの成果物ブランチはまだ作られていない（PoC の結果を待つため）
- epic PR 本文に `## タスク一覧` がまだ無い

## 正常シナリオ（リバースエンジニアリング）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| `リバースエンジニアリング` ラベル | 対象の PR に付与済み | 本経路を選ぶ判定材料。ユーザーが立ち上げ Issue に付け、子 PR へ引き継がれる |
| epic PR | `layer:epic` + `type:docs` + `確認:epic-conductor` 付きで存在 | 本文の `## ユースケース一覧` は作成時に記入済み |
| エピック一覧 | 親 system PR の `## エピック一覧` に当該 epic の所属 UC と着手順が確定済み | [システム構成確定](./システム構成確定.md) の成果物 |
| assignee | 未設定 | エージェント起動条件 |
| 現状の設計書 | 現状モックと現状の複合 UC シナリオが epic ブランチに存在 | RE PR がマージ済みであることが前提 |
| モニター | polling 中 | - |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  Note over GH: リバースエンジニアリング起動:<br>正常シナリオ 2 本を先に実行済み<br>（epic ブランチに現状モックと現状シナリオが入っている）
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as epic-conductor
  ORC->>MON: 既存セッションへ送信
  participant REPO as リポジトリ
  activate MON
  MON-->>GH: 親 system PR の エピック一覧から<br>当該 epic の範囲と所属 UC を読む
  MON-->>REPO: epic ブランチの現状モックと現状シナリオから<br>現在の振る舞いを把握
  MON->>GH: 概要 / 背景 / 横断要件を現状の設計書から逆算して<br>epic PR 本文に反映
  MON->>GH: epic PR に確認事項コメント<br>（実装と要件が乖離している箇所・<br>あるべき姿に直す範囲）を投稿
  MON->>GH: epic PR に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: epic PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: epic PR の本文修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: epic PR の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: epic PR の自分宛コメント一括 Resolve
  MON->>GH: epic PR 本文に タスク一覧 を追記
  MON->>REPO: モックの成果物ブランチ作成<br>（docs/epic/{ドメイン}/mock・<br>base=epic ブランチ）+ 空 commit push
  MON->>GH: 成果物 Draft PR 作成 +<br>確認:mock-designer + 指示コメントを付与
  MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
  MON->>GH: epic PR の 確認:epic-conductor 除去
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- epic PR 本文の要件 4 セクションが揃い、`## 概要` / `## 背景` / `## 横断要件` が現状の設計書から書かれている
- epic-conductor が実装コードを読み出した記録がない（入力は親 system PR のエピック一覧と epic ブランチの現状の設計書に閉じる）
- ユースケース一覧の `対応 story` 列が全行 `未作成`
- ユースケース一覧の `変更種別` 列が全行埋まっており、現状の設計書に対応する UC は `新規` ではない（既にある振る舞いを起こしたものなので `変更` / `削除`）
- 現状の設計書と要件が乖離している箇所が確認事項コメントに挙がり、ユーザー判断が本文に反映されている
- モックの成果物ブランチと Draft PR が作成され `確認:mock-designer` が付与され、epic PR からは `確認:epic-conductor` が除去されている
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
- 自分宛コメントが全て Resolve 済み

## 異常シナリオ

なし

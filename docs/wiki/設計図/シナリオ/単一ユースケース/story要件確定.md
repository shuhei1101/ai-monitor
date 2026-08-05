---
template_version: 2.1.0
---

# story要件確定

story-conductor が story PR の本文（概要 / 背景 / ユースケース要件）を確定する単一ユースケース。

対応エージェント: `story-conductor`（初回呼び出し）

- 対応テストファイル: `tests/e2e/単一ユースケース/test_story要件確定.py`

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| story PR | `layer:story` + `確認:story-conductor` 付きの Draft PR が存在 | ブランチと PR は epic-conductor が作成済み・本文は `## 紐づく Issue` のみ |
| 親 epic PR | ユースケース一覧 + 横断要件 確定済み | UC 番号との対応を背景に書く元ネタ |
| assignee | 未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  Note over GH: story PR に 確認:story-conductor 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as story-conductor
  ORC->>MON: tmux セッション作成 +<br>フェーズドキュメント注入
  participant REPO as リポジトリ
  activate MON
  MON-->>GH: base を辿って親 epic PR の<br>UC 一覧から担当 UC を特定
  MON->>GH: 要件 3 セクション + UC<br>タイプ別観点の要件草案を<br>story PR 本文に反映
  MON->>GH: story PR に確認事項コメントを投稿
  MON->>GH: story PR に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: story PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: story PR の本文修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: story PR の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: story PR の自分宛コメント一括 Resolve
  MON->>GH: story PR 本文に タスク一覧 を追記
  MON->>REPO: 単一UCシナリオの成果物ブランチ作成<br>（docs/story/{ドメイン}/{UC名}/scenario・<br>base=story ブランチ）+ 空 commit push
  MON->>GH: 成果物 Draft PR 作成 +<br>親のスタックへ接続
  MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
  MON->>GH: 成果物 PR に 確認:single-scenario-writer 付与・<br>story PR の 確認:story-conductor 除去
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- story PR 本文に `## 概要` / `## 背景` / `## ユースケース要件` が揃っている
- `## 背景` に「親 epic #N の UC「{UC 名}」に対応」の 1 行が含まれる
- `## 背景` に親 epic の ユースケース一覧 から読んだ担当 UC の `変更種別` が書き写されている（下位レイヤーが現状の設計書を調べる要否を判断する材料）
- 横断要件を参照する要件行の補足に `epic 横断要件「{要件の要旨}」に基づく` が明記されている
- RE PR が先に作られてマージされ、story ブランチに現状のシナリオが入っている
- 単一UCシナリオの成果物ブランチと Draft PR（base=story ブランチ）が作成され、`確認:single-scenario-writer` が付与されている
- story PR 本文の `## タスク一覧` に単一 UC シナリオの作成 / 修正・シナリオ索引の更新・単一 UC E2E テストの実行が列挙され、全行が未チェック（チェックは各行を担当した作業者が入れる）
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている

## 正常シナリオ（確認事項なし・単一 UC 影響なし）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| story PR | `layer:story` + `確認:story-conductor` 付きの Draft PR が存在 | 本文は `## 紐づく Issue` のみ |
| 親 epic PR | ユースケース一覧に複合 UC への影響なしと記録済み | 上位が素通しで降ろしてきた状態。担当 UC の `変更種別` は `変更` |
| 既存の設計書 | 対象の単一 UC シナリオが story ブランチに存在する | 修正箇所の有無を判定する材料 |
| assignee | 未設定 | エージェント起動条件 |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター
  participant REPO as リポジトリ

  Note over GH: story PR に 確認:story-conductor 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as story-conductor
  ORC->>MON: tmux セッション作成 +<br>フェーズドキュメント注入
  activate MON
  MON->>GH: 親 epic の UC を特定・<br>要件草案を story PR 本文に反映
  MON-->>REPO: 既存の単一 UC シナリオと<br>照合して修正箇所の有無を判定
  MON->>MON: 判断が分かれる論点が無く<br>単一 UC の修正も不要と確定
  MON->>GH: story PR に確認事項コメントを投稿<br>（質問せずに置いた前提を明示・議論中 は付けない）
  deactivate MON

  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（子subsystemPR作成）
  activate MON
  MON->>REPO: 先頭グループの subsystem ブランチ作成<br>（base=story ブランチ）
  MON->>GH: 各ブランチに Draft PR 作成 +<br>確認:subsystem-conductor 付与
  MON->>GH: story PR の 確認:story-conductor 除去
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- 確認事項コメントが 1 件も投稿されていない
- 担当 UC の `変更種別` が `変更` のため、既存の単一 UC シナリオと照合したうえで修正不要と判断している
- `議論中` が付与されず assignee も設定されていない（ユーザーを止めずに通り抜けている）
- 確認事項コメントに、質問せずに前提として置いた判断とその根拠が書かれている
- 単一UCシナリオの成果物ブランチと PR が作られていない（story ブランチ上で作業する担当が居ないため）
- story PR の本文に `## タスク一覧` が無い
- subsystem ブランチと Draft PR が作成され `確認:subsystem-conductor` が付与されている
- story PR から `確認:story-conductor` が除去されている

## 正常シナリオ（リバースエンジニアリング）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| `リバースエンジニアリング` ラベル | 対象の PR に付与済み | 本経路を選ぶ判定材料。ユーザーが立ち上げ Issue に付け、子 PR へ引き継がれる |
| story PR | `layer:story` + `type:docs` + `確認:story-conductor` 付きで存在 | 本文は `## 紐づく Issue` のみ |
| 親 epic PR | `type:docs` でユースケース一覧 + 横断要件 確定済み | 担当 UC の特定元 |
| 複合ユースケースシナリオ | epic ブランチへマージ済み | UC の位置づけの参照元 |
| assignee | 未設定 | エージェント起動条件 |
| 現状のシナリオ | 当該 UC のシナリオが現状の内容で story ブランチに存在 | RE PR がマージ済みであることが前提 |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  Note over GH: story PR に 確認:story-conductor 付与済み
  Note over GH: リバースエンジニアリング起動:<br>正常シナリオ 2 本を先に実行済み<br>（story ブランチに現状のシナリオが入っている）
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as story-conductor
  ORC->>MON: 既存セッションへ送信
  participant REPO as リポジトリ
  activate MON
  MON-->>GH: 親 epic の UC 一覧から担当 UC を特定し<br>複合シナリオ上の位置づけを読む
  MON-->>REPO: story ブランチの現状のシナリオから<br>現在の振る舞いを把握
  MON->>GH: 要件 3 セクション + UC タイプ別観点の要件を<br>現状のシナリオから逆算して story PR 本文に反映
  MON->>GH: story PR に確認事項コメント<br>（実装にある挙動のうち意図が不明なもの・<br>あるべき姿との差分）を投稿
  MON->>GH: story PR に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: story PR にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: story PR の本文修正 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: story PR の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: story PR の自分宛コメント一括 Resolve
  MON->>GH: story PR 本文に タスク一覧 を追記
  MON->>REPO: 単一UCシナリオの成果物ブランチ作成<br>（docs/story/{ドメイン}/{UC名}/scenario・<br>base=story ブランチ）+ 空 commit push
  MON->>GH: 成果物 Draft PR 作成 +<br>親のスタックへ接続
  MON->>ORC: 作成した PR の番号を<br>自セッションの監視面として台帳に登録
  MON->>GH: 成果物 PR に 確認:single-scenario-writer 付与・<br>story PR の 確認:story-conductor 除去
  deactivate MON
  Note over MON: セッションは epic PR マージまで常駐
```

### 期待値

- story PR 本文に `## 概要` / `## 背景` / `## ユースケース要件` が揃っている
- `## 背景` に「親 epic #N の UC「{UC 名}」に対応」の 1 行が含まれる
- `## 背景` に親 epic の ユースケース一覧 から読んだ担当 UC の `変更種別` が書き写されている（下位レイヤーが現状の設計書を調べる要否を判断する材料）
- `## ユースケース要件` の各行が現状のシナリオの振る舞い、またはユーザーが承認したあるべき姿になっている
- story-conductor が実装コードを読み出した記録がない（入力は親 epic の UC 一覧と story ブランチのシナリオに閉じる）
- 現状のシナリオから意図が読み取れなかった挙動が確認事項コメントに挙がり、ユーザー判断が本文に反映されている
- 単一UCシナリオの成果物ブランチと Draft PR（base=story ブランチ）が作成され、`確認:single-scenario-writer` が付与されている
- story PR 本文の `## タスク一覧` に単一 UC シナリオの作成 / 修正・シナリオ索引の更新・単一 UC E2E テストの実行が列挙され、全行が未チェック（チェックは各行を担当した作業者が入れる）
- 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている

## 異常シナリオ

なし

---
template_version: 2.1.0
---

# Issue分解と子PR作成

ユーザーまたはエージェントが起票した Issue を intake-issue-triager が受け、既存の作業と重複していなければ作業単位に分解し、ユーザー承認を経て作業単位ごとのブランチと Draft PR を作成する単一ユースケース。

対応エージェント: `intake-issue-triager`

- 対応テストファイル: `tests/e2e/単一ユースケース/test_Issue分解と子PR作成.py`

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| intake Issue | ユーザー起票の Issue に `確認:intake-issue-triager` 付与済み | 本文はユーザーが書いたまま |
| assignee | 未設定 | エージェント起動条件 |
| モニター | 対象リポを polling 中 | - |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as モニター

  U->>GH: Issue 起票 + 確認:intake-issue-triager 付与
  ORC-->>GH: polling（確認ラベルあり + assignee なし を検知）
  create participant MON as intake-issue-triager
  ORC->>MON: tmux セッション作成 +<br>フェーズドキュメント注入
  activate MON
  MON-->>GH: 本文のキーワードで<br>関連 Issue / PR・シナリオ設計書を調査
  MON->>GH: intake Issue の本文を読み<br>作業単位に分解
  MON->>GH: intake Issue に layer:intake + type:* 付与
  MON->>GH: intake Issue に分解案コメントを投稿し、<br>該当する確認事項があれば追加で投稿
  MON->>GH: intake Issue に 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 応答ループ（修正指示がある間）
    U->>GH: intake Issue にフィードバックコメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: intake Issue で案修正の返信 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: intake Issue の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: 作業単位ごとに<br>ブランチを作成（base=master）
  MON->>GH: 各ブランチに Draft PR を作成<br>（layer:epic 付与・確認ラベルなし・<br>本文は 紐づく Issue のみ）
  MON->>GH: 全 PR に 確認:epic-conductor 付与
  MON->>GH: intake Issue の自分宛コメント一括 Resolve
  MON->>GH: intake Issue の 確認:intake-issue-triager 除去
  deactivate MON
  Note over MON: セッションは intake Issue close<br>（モニター直轄）まで常駐
```

### 期待値

- 承認された案と同数のブランチと Draft PR が存在する（`layer:epic` + `確認:epic-conductor` が付与）
- 各 PR の base が `master` になっている
- 各 PR 本文の `## 紐づく Issue` に intake Issue の番号が入っている
- 着手順の依存がある場合、確認ラベルは先頭の PR 1 本にだけ付いている（依存が無ければ全 PR に付く）
- 確認ラベルが付いていない PR に着手の痕跡が無い（`議論中` 未付与・assignee 未設定・epic-conductor の投稿コメントなし）
- intake Issue の本文がユーザー起票時のまま書き換わっていない
- intake Issue に `layer:intake` + `type:*` が残り、`確認:*` は除去済み
- 自分宛コメントが全て Resolve 済み

## 正常シナリオ（既存 PR と重複）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 既存 PR | 同じ目的の PR が open で存在し、担当エージェントの `確認:*` が付いている | 統合先 |
| intake Issue | 応答ループ中の依頼から起票された Issue に `確認:intake-issue-triager` 付与済み | 本文は既存 PR と同じ目的の内容 |
| assignee | 未設定 | エージェント起動条件 |
| モニター | 対象リポを polling 中 | - |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター

  ORC-->>GH: polling（確認ラベルあり + assignee なし を検知）
  create participant MON as intake-issue-triager
  ORC->>MON: tmux セッション作成 +<br>フェーズドキュメント注入
  activate MON
  MON-->>GH: 本文のキーワードで<br>関連 Issue / PR を調査
  MON->>MON: 既存 PR と目的が重複し<br>本 Issue にしかない内容もあると判定
  MON->>GH: 既存 PR に、intake Issue 固有の内容を<br>転記するコメントを投稿
  MON->>GH: intake Issue に統合先へのリンクを残して<br>クローズ（reason: not_planned）
  deactivate MON
```

### 期待値

- ブランチと Draft PR が 1 件も作られていない
- 既存 PR に、統合した intake Issue の固有内容と出典（intake Issue 番号）が転記されている
- intake Issue が closed になり、クローズ理由が `not_planned` として記録されている
- intake Issue に統合先へのリンクが残っている
- intake Issue に `議論中` と `assignee` が設定されていない（ユーザーの確認を挟まずに統合する）
- 既存 PR のラベル・担当は変わっていない（進行中の作業を止めない）

## 正常シナリオ（既存 Issue と重複）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 既存のルール改修 Issue | 同じルールページの同じ記述箇所を指摘する Issue が open で存在 | 統合先。`AI不具合報告` ラベル付き・確認ラベルなし |
| 対象 Issue | 別セッションが同じ記述箇所について起票したルール改修 Issue に `確認:intake-issue-triager` 付与済み | `## 対象ルール` の引用箇所と `## 指摘の内容` が既存 Issue と一致し、報告元だけが違う。追加情報なしの分岐を決定的に誘発 |
| assignee | 未設定 | エージェント起動条件 |
| モニター | 対象リポを polling 中 | - |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター

  ORC-->>GH: polling（確認ラベルあり + assignee なし を検知）
  create participant MON as intake-issue-triager
  ORC->>MON: tmux セッション作成 +<br>フェーズドキュメント注入
  activate MON
  MON-->>GH: 対象 Issue と同じ AI不具合報告 ラベルの<br>open Issue を検索
  MON-->>GH: 見つかった Issue の<br>対象ルール と 指摘の内容 を読む
  MON->>MON: 対象ルールのページと引用箇所が同じで<br>報告元しか違わないと判定
  MON->>GH: 対象 Issue に統合先へのリンクを残して<br>クローズ（reason: not_planned）
  deactivate MON
```

### 期待値

- ブランチと Draft PR が 1 件も作られていない
- 既存 Issue にコメントが投稿されていない（転記する内容が無いため）
- 対象 Issue が closed になり、クローズ理由が `not_planned` として記録されている
- 対象 Issue に統合先の Issue 番号へのリンクが残っている
- 対象 Issue に `議論中` と `assignee` が設定されていない（ユーザーの確認を挟まずにクローズする）
- 既存 Issue のラベル・assignee は変わっていない

## 正常シナリオ（既存 Issue と重複・追加情報あり）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 既存の不具合 Issue | 同じ手順書ページの同じ事象を報告する Issue が open で存在 | 統合先。`AI不具合報告` ラベル付き・`## 回避策` は `なし` |
| 対象 Issue | 別のエージェントが同じ事象を報告した不具合 Issue に `確認:intake-issue-triager` 付与済み | `## 回避策` に既存 Issue が持たない回避策が入っている。追加情報ありの分岐を決定的に誘発 |
| assignee | 未設定 | エージェント起動条件 |
| モニター | 対象リポを polling 中 | - |

### フロー

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant ORC as モニター

  ORC-->>GH: polling（確認ラベルあり + assignee なし を検知）
  create participant MON as intake-issue-triager
  ORC->>MON: tmux セッション作成 +<br>フェーズドキュメント注入
  activate MON
  MON-->>GH: 対象 Issue と同じ AI不具合報告 ラベルの<br>open Issue を検索
  MON-->>GH: 見つかった Issue の<br>該当ページ と 事象 と 回避策 を読む
  MON->>MON: 該当ページと事象は同じだが<br>対象 Issue にしかない回避策があると判定
  MON->>GH: 既存 Issue に回避策と<br>出典（対象 Issue の番号）を追記
  MON->>GH: 対象 Issue に統合先へのリンクを残して<br>クローズ（reason: not_planned）
  deactivate MON
```

### 期待値

- ブランチと Draft PR が 1 件も作られていない
- 既存 Issue に、対象 Issue にしかない回避策と出典（対象 Issue の番号）が追記されている
- 対象 Issue が closed になり、クローズ理由が `not_planned` として記録されている
- 対象 Issue に統合先の Issue 番号へのリンクが残っている
- 対象 Issue に `議論中` と `assignee` が設定されていない
- 既存 Issue のラベル・assignee は変わっていない

## 異常シナリオ

なし

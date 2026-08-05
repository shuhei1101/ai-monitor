---
template_version: 2.1.0
---

# ルール改修Issue起票（モニター）

MCP ツール: `create_monitor_rule_issue`

ai-monitor のワークフロー定義（手順書・規約・テンプレート）に起因する指摘を、ai-monitor 自身のリポジトリへルール改修 Issue として起票する。

- 対応テストファイル: `tests/integration/mcp/test_ルール改修Issue起票（モニター）.py`

## インターフェース

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `title` | str | ✅ | - | ルール改修の要約 | - | 1 行で「どのルールをどう直したいか」が分かるもの |
| `body` | str | ✅ | - | 指摘内容と指摘に至った経緯 | - | Markdown 可。定型セクションは本ツールが組み立てる |
| `rule_page` | str | ✅ | - | 対象ルールのページパス | 起票先リポジトリ内の相対パス | 起票先で該当箇所を開くために使う |
| `rule_excerpt` | str | ✅ | - | 指摘の元になったルールの記述 | - | 記述が無いことが問題の場合は、無いと分かる書き方にする |
| `agent_name` | str | ✅ | - | 報告元のエージェント名 | - | `@` は不要 |
| `number` | int | ✅ | - | 報告元の Issue / PR 番号 | - | 担当プロジェクト側の番号 |

リクエスト例:

```json
{
  "title": "PR 本文テンプレート（エピック）に変更種別の記入例が無い",
  "body": "テンプレート「PR本文/エピック」のユースケース一覧に従って表を作ったところ、変更種別の列を足すよう指摘を受けました。テンプレートに記入例が無く、列の要否を読み取れませんでした。\n",
  "rule_page": "docs/wiki/テンプレート/PR本文/エピック.md",
  "rule_excerpt": "（`## ユースケース一覧` の記述例に変更種別の列が無い）",
  "agent_name": "epic-conductor",
  "number": 90
}
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `issue_number` | int | 作成した Issue 番号 | - | ai-monitor のリポジトリでの番号 |
| `url` | str | Issue の html URL | - | 報告元へリンクを残すときに使う |

レスポンス例:

```json
{
  "issue_number": 214,
  "url": "https://github.com/{owner}/ai-monitor/issues/214"
}
```

本文例（作成される Issue の本文）:

```markdown
## 報告元

| 項目 | 値 |
| --- | --- |
| プロジェクト | sandbox |
| エージェント | epic-conductor |
| 対象 | shuhei1101/ai-monitor-e2e#90 |

## 対象ルール

- `docs/wiki/テンプレート/PR本文/エピック.md`

> （`## ユースケース一覧` の記述例に変更種別の列が無い）

## 指摘の内容

テンプレート「PR本文/エピック」のユースケース一覧に従って表を作ったところ、変更種別の列を足すよう指摘を受けました。テンプレートに記入例が無く、列の要否を読み取れませんでした。
```

## 制約

| 項目 | 制約 | 補足 |
| --- | --- | --- |
| タイムアウト | 制限なし | - |
| 起票先 | 設定の `ai_monitor_repo`（`owner/name`） | 呼び出し元セッションのプロジェクトではない。未設定なら起票せずエラー |
| 起票の粒度 | 1 回の呼び出しで 1 Issue | 同じルールへの報告が重なっても本ツールでは束ねない（重複の整理は intake-issue-triager が担う） |
| 付与ラベル | `AI不具合報告` のみ | 確認ラベルは付けないので、ユーザーが承認するまで改修フローに乗らない |
| assignee | 認証ユーザー 1 名で固定 | 呼び出し側が選べない |
| 呼び出し元への影響 | 起票の成否にかかわらず、呼び出し元の作業は続行できる | 本ツールは報告だけを行い、待機・ラベル操作をしない |

## フロー一覧

| 分類 | フロー名 | 概要 | 補足 |
| --- | --- | --- | --- |
| 正常 | 正常系 | 定型本文の組み立て → Issue 作成 → 番号と URL の返却 | - |
| 異常 | 異常系（起票先が未設定） | 設定に `ai_monitor_repo` が無く起票できない | - |
| 異常 | 異常系（API エラー） | 認証切れ / ネットワーク断 | - |

## 正常系

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API を差し替え（正常応答を返す） | - |
| 設定 | `ai_monitor_repo` を指す設定あり | 起票先の解決に使う |
| 呼び出し元 | 担当プロジェクト（ai-monitor 以外）のセッション | 起票先が呼び出し元と別であることを確認するため |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール create_monitor_rule_issue
  participant GH as GitHub（ai-monitor）

  A->>T: title, body, rule_page,<br>rule_excerpt, agent_name, number
  T-->>GH: 認証ユーザーのログイン名を取得
  T->>T: 報告元・対象ルール・指摘の内容を<br>定型セクションに組み立て
  T->>GH: Issue を作成<br>（assignee = 認証ユーザー・AI不具合報告）
  T-->>A: issue_number, url
```

### 期待値

- `ai_monitor_repo` のリポジトリに Issue が作成されている（呼び出し元セッションのプロジェクトではない）
- 本文に報告元（プロジェクト名・エージェント名・対象番号）・対象ルールのページパスと記述・指摘の内容が入っている
- assignee が認証ユーザーになっている
- ラベルが `AI不具合報告` の 1 つだけで、確認ラベルが付いていない
- 戻り値の `issue_number` / `url` が作成した Issue を指している

## 異常系（起票先が未設定）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API を差し替え（呼ばれないことを確認する） | - |
| 設定 | `ai_monitor_repo` が未設定 | 異常を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール create_monitor_rule_issue

  A->>T: title, body, rule_page,<br>rule_excerpt, agent_name, number
  T->>T: 起票先が解決できないと判定
  T-->>A: 例外
```

### 期待値

- 例外が送出される
- GitHub への呼び出しが行われていない

## 異常系（API エラー）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API が Issue 作成で 4xx / 5xx を返す | 異常を決定的に誘発 |
| 設定 | `ai_monitor_repo` を指す設定あり | - |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール create_monitor_rule_issue
  participant GH as GitHub（ai-monitor）

  A->>T: title, body, rule_page,<br>rule_excerpt, agent_name, number
  T-->>GH: 認証ユーザーのログイン名を取得
  T->>GH: Issue を作成
  GH-->>T: 4xx / 5xx
  T-->>A: 例外
```

### 期待値

- 例外が送出される
- 呼び出し元のターンは中断されず、報告なしで本来の作業を続けられる

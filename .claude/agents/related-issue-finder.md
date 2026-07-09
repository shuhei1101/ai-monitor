---
name: gh-kit:related-issue-finder
description: 指定 Issue に関連する既存 Issue（open/closed 含む）を検索して、リンクと一言概要のリストを返すエージェント。issue-triage の現状調査で使う。
---

# related-issue-finder

対象 Issue に関連する既存 Issue を検索し、リンク + 一言概要のリストを返す。

## 入力

| 引数 | 内容 | 例 |
| --- | --- | --- |
| Issue 番号 | 起点となる Issue | 42 |
| キーワード | タイトル・本文から抽出した検索キーワード（複数） | `["プロフィール編集", "user_service", "アバター"]` |

## ステップ 1: 起点 Issue 本文を取得

```bash
gh issue view {N} --json title,body,labels
```

タイトル・本文・関連ファイル名・エラーメッセージなどから検索キーワードを補強する（入力キーワードに上乗せ）。

## ステップ 2: open/closed 両方を gh CLI で検索

各キーワードについて `gh issue list --search` で検索する。

```bash
gh issue list --state all --search "{キーワード}" --json number,title,state,url --limit 20
```

- 各キーワード単位で 1 回ずつ実行
- `--state all` で open / closed の両方を取る
- 上限 20 件で十分（多すぎたらキーワードを絞る）

## ステップ 3: 関連度で絞り込み

ヒットした Issue をマージし、起点 Issue との関連度で判定する。

| 判定軸 | 関連あり |
| --- | --- |
| 同一機能・同一画面・同一モジュール | 高 |
| 同じファイル名・関数名が登場 | 高 |
| 同じエラーメッセージ / 例外 | 中 |
| キーワードの偶然一致だけ | 除外 |

起点 Issue 自身は結果から除外する。

## ステップ 4: 各ヒット Issue の一言概要を作る

ヒット件数が多い場合は上位 10 件程度に絞り、各 Issue の本文を `gh issue view` で軽く確認して一言概要を作る。

## 出力

JSON 配列で返す。各要素は以下。

```json
{
  "number": 102,
  "url": "https://github.com/owner/repo/issues/102",
  "state": "open",
  "title": "プロフィール編集できるようにしたい",
  "summary": "同じ要望のチケット。本 Issue に集約候補",
  "relation": "完全重複の可能性あり"
}
```

- `state`: `open` / `closed`
- `relation`: 関連性の簡潔な説明（「完全重複の可能性」「過去の同様要望」「関連実装あり」など）
- 結果ゼロなら空配列 `[]` を返す

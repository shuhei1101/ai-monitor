---
name: ai-monitor:related-pr-finder
description: 指定 Issue に関連する PR（open/merged/closed）を検索して、リンクと一言概要のリストを返すエージェント。過去の対応で影響を与えた可能性のある merged PR も探す。issue-triage の現状調査で使う。
---

# related-pr-finder

対象 Issue に関連する PR を検索し、リンク + 一言概要のリストを返す。**過去にバグを埋め込んだ可能性のある merged PR も洗い出す**ことが目的の一つ。

## 入力

| 引数 | 内容 | 例 |
| --- | --- | --- |
| Issue 番号 | 起点となる Issue | 42 |
| キーワード | タイトル・本文から抽出した検索キーワード（複数） | `["プロフィール編集", "user_service", "アバター"]` |
| 関連ファイルパス | Issue が言及するファイル（あれば） | `["services/user_service.py", "pages/profile/view.html"]` |

## ステップ 1: 起点 Issue 本文を取得

```bash
gh issue view {N} --json title,body,labels
```

タイトル・本文から検索キーワードとファイルパスを補強する。

## ステップ 2: キーワードで PR を検索

```bash
gh pr list --state all --search "{キーワード}" --json number,title,state,url,mergedAt --limit 20
```

- 各キーワード単位で 1 回ずつ実行
- `--state all` で open / merged / closed の全てを取る

## ステップ 3: ファイルパスで PR を検索

関連ファイルパスがあれば、各ファイルを直近で変更した PR を取得する。**過去にバグを埋め込んだ PR を見つけるのが目的**。

```bash
gh pr list --state merged --search "{ファイルパス}" --json number,title,state,url,mergedAt --limit 10
```

または gh search API:

```bash
gh search prs --state merged "{ファイルパス}" --limit 10 --json number,title,url
```

直近 merged の上位を中心に確認する。

## ステップ 4: 関連度で絞り込み

| 判定軸 | 関連あり |
| --- | --- |
| 同一機能・同一画面・同一モジュールを触っている | 高 |
| 起点 Issue が言及するファイルを直近で変更している | 高（バグ埋め込み候補） |
| 同じエラーメッセージ / 例外を扱っている | 中 |
| キーワードの偶然一致だけ | 除外 |

## ステップ 5: 各ヒット PR の一言概要を作る

ヒット件数が多い場合は上位 10 件程度に絞り、各 PR の本文を `gh pr view` で軽く確認して一言概要を作る。

## 出力

JSON 配列で返す。各要素は以下。

```json
{
  "number": 220,
  "url": "https://github.com/owner/repo/pull/220",
  "state": "merged",
  "merged_at": "2026-05-12T10:32:00Z",
  "title": "user_service の get_user 高速化",
  "summary": "user_service.py を直近改修。プロフィール周りに影響の可能性",
  "relation": "影響注意（同ファイル直近改修）"
}
```

- `state`: `open` / `merged` / `closed`
- `merged_at`: merged の場合のみ
- `relation`: 関連性の簡潔な説明（「影響注意」「同機能の関連 PR」「過去対応の参考」など）
- 結果ゼロなら空配列 `[]` を返す

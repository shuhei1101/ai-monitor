---
name: ai-monitor:wiki-create
description: GitHub Wiki に新規ページを 1 件作成して push する。「Wiki に書いて」「Wiki ページ作って」と言われたら起動。
---

# wiki-create

1 対象 = 1 Wiki ページの「現在の仕様スナップショット」を作成する。
ローカルクローン済みの Wiki リポジトリへファイルを書き出し、commit + push まで実施する。

## 環境変数

| 変数 | 必須 | 用途 |
| --- | --- | --- |
| `AI_MONITOR_WIKI_PATH` | 必須 | Wiki ローカルリポジトリ絶対パス（例: `/path/to/repo.wiki`）。Session Start フックで自動 pull される |

未設定時は停止。`.claude/settings.local.json` で設定する想定。
未クローンなら以下で clone する:
```bash
gh repo clone $(gh repo view --json nameWithOwner --jq '.nameWithOwner').wiki "${AI_MONITOR_WIKI_PATH}"
```

## カテゴリ・Sidebar/Home 自動更新

`_Sidebar.md` / `Home.md` への自動追加は **常に実行される**（`--category` 指定の有無に関わらず）:

| 動作 |
| --- |
| `_Sidebar.md` の該当カテゴリセクション末尾にリンク行を挿入する |
| カテゴリが存在しない場合は `_Sidebar.md` 末尾に新規セクションを追加する |
| カテゴリ階層は `##`（レベル2）・`###`（レベル3）の 2 段階まで |
| `Home.md` を `_Sidebar.md` の内容から自動再生成する |

`--category` を省略した場合は **「未分類」** カテゴリとして `_Sidebar.md` / `Home.md` に自動追加される。

## ページ名規約

| 項目 | 規約 |
| --- | --- |
| ファイル名 | 日本語可。`{カテゴリ}-{対象名}.md` 形式（例: `プラグイン-ai-monitor.md`） |
| H1 タイトル | `# {対象名} — {一行サマリ}` |
| カテゴリ | 既存 Wiki の Sidebar に既出のカテゴリと整合させる |

## ページ本文テンプレート

リモート Wiki の `Wikiページ` ページからテンプレートを取得する。

```bash
curl -fsSL "https://raw.githubusercontent.com/wiki/$(gh repo view --json nameWithOwner --jq '.nameWithOwner')/Wikiページ.md"
```

テンプレートのポリシー: 1 対象 = 1 ページ。書くのは「今どうなっているか」だけ。履歴・経緯・却下案は書かない。

## タスク

### ステップ 1: 既存 Wiki ページを確認

`${AI_MONITOR_WIKI_PATH}` 配下を `ls` し、同名・類似名の既存ページがないか確認する。
ある場合は新規作成せずユーザーに「既存ページを更新するか / 別名で新規作成するか」を聞く。

### ステップ 2: ページ本文を生成

上記の curl コマンドで `Wikiページ` テンプレートを取得し、対象の現在仕様を埋めて下書きする。
履歴・「なぜこうなったか」「以前は〜だった」は書かない。

### ステップ 3: 作成スクリプトを実行

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/wiki-create.sh" \
  --page-name "{カテゴリ}-{対象名}.md" \
  --body-file "{tmpファイルパス}" \
  --category "{カテゴリ名}" \
  --category-level 2
```

`--category` はオプション。省略時は「未分類」カテゴリとして `_Sidebar.md` / `Home.md` に自動追加される。
`--category-level` は `2`（`##`）または `3`（`###`）を指定。デフォルトは `2`。

スクリプトが以下を行う:

| 動作 |
| --- |
| `${AI_MONITOR_WIKI_PATH}/{page-name}` に本文を書き込む（既存なら上書き拒否で停止） |
| `_Sidebar.md` の該当カテゴリにリンクを挿入（カテゴリ未存在なら新規追加）。`--category` 省略時は「未分類」カテゴリ |
| `Home.md` を `_Sidebar.md` の内容から自動再生成 |
| Wiki リポで `git add` + `git commit` + `git push`（差分なしならスキップ） |

### ステップ 4: 結果報告

| 項目 | 内容 |
| --- | --- |
| 作成ページ | `{page-name}` |
| Wiki URL | `gh repo view --json url -q .url` の URL に `/wiki/{ページ名拡張子なし}` を付けたもの |

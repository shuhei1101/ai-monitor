---
template_version: 1.1.0
---

# モジュール構成: 注入 / URLドキュメント

`URLドキュメント` ドメイン（注入側）に属する構成要素詳細。
SKILL.md の動的コンテキスト注入から呼ばれ、指定 URL の本文を標準出力に展開する。

本ドメインの関数はプラグイン配下に置き、モニターと注入 CLI の両方から使う。
CLI はプラグインのインストール先から起動されて `src/` を参照できないため、共有できる位置がプラグイン配下になる。
モニター側は [Wiki参照](../MCP/Wiki参照.py.md) の MCP ツールが `sys.path` 経由で読み込む。

## 一覧

| ユースケース | 役割 | コンテナ | 種別 | 名前 | 概要 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| URLドキュメント注入 | URL 取得 | `inject/fetch.py` | 関数 | [`fetch_url`](#url-取得) | URL からテキストを取得する | エージェントドキュメント注入・[Wiki参照](../MCP/Wiki参照.py.md)と共有 |
| URLドキュメント注入 | ドキュメント読み取り型 | `inject/fetch.py` | 関数型 | [`ReadDoc`](#ドキュメント読み取り型) | 場所を受けて本文を返す関数のシグネチャ | 取得手段の差し替え口 |
| URLドキュメント注入 | ローカル取得 | `inject/fetch.py` | 関数 | [`read_local`](#ローカル取得) | ローカルファイルからテキストを読む | [`ReadDoc`](#ドキュメント読み取り型) の実装 |
| URLドキュメント注入 | ソース読み取り選択 | `inject/fetch.py` | 関数 | [`select_reader`](#ソース読み取り選択) | ベースの形から [`ReadDoc`](#ドキュメント読み取り型) の実装を選ぶ | 判定はここ 1 箇所に集約する |
| URLドキュメント注入 | URL 正規化 | `inject/read_urls.py` | 関数 | [`normalize_github_url`](#url-正規化) | GitHub blob URL を raw URL に変換する | - |
| URLドキュメント注入 | front matter 除去 | `inject/read_urls.py` | 関数 | [`strip_frontmatter`](#front-matter-除去) | 本文先頭の YAML front matter を除去する | - |
| URLドキュメント注入 | CLI | `inject/read_urls.py` | 関数 | [`main`](#cli) | URL 一覧を受けて本文一式を出力する | - |

## ディレクトリ構成

```
plugins/ai-monitor/inject/
├── fetch.py         # fetch_url（エージェントドキュメント注入・Wiki参照と共有）
└── read_urls.py     # normalize_github_url / strip_frontmatter（Wiki参照と共有）/ main
```

## 構成図

```mermaid
classDiagram
  CLI ..> URL正規化 : blob URL の変換
  CLI ..> URL取得 : ドキュメント取得
  CLI ..> frontmatter除去 : 本文の整形

  class CLI {
    <<function>>
    +CLI() int
  }
  class URL正規化 {
    <<function>>
    +URL正規化(URL) str
  }
  class frontmatter除去 {
    <<function>>
    +frontmatter除去(本文) str
  }
  class URL取得 {
    <<function>>
    +URL取得(URL) str
  }

  click CLI href "#cli"
  click URL正規化 href "#url-正規化"
  click frontmatter除去 href "#front-matter-除去"
  click URL取得 href "#url-取得"
```

## `inject/fetch.py`
> 種別: ファイル

注入 CLI 共通の URL 取得ヘルパー。

---

### URL 取得
> 物理名: `fetch_url`<br>
> 種別: 関数

URL からテキストを取得する。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| URL | `url` | `str` | ✅ | - | 取得対象 URL | パスに日本語を含んでよい |

引数例:

```python
fetch_url("https://raw.githubusercontent.com/o/r/master/docs/wiki/規約/コメント.md")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `str` | 取得した本文 | UTF-8 デコード済み |

戻り値例:

```python
"# 規約: コメント\n..."
```

#### 処理

1. URL のパス部分の非 ASCII 文字を quote する
2. GET して本文を UTF-8 で返す

#### 例外

| 例外名 | 発生条件 | メッセージ | 補足 |
| --- | --- | --- | --- |
| `URLError` | 接続不可 / HTTP エラー（404 等） | urllib のエラー内容 | 呼び出し元へそのまま伝播（フォールバックしない） |

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_fetch_url` | 正常 | 非 ASCII パスの quote と取得 | 日本語パスを含む URL | urllib | quote 済み URL でリクエストされ、本文が返る | - |

---

### ローカル取得
> 物理名: `read_local`<br>
> 種別: 関数<br>
> 継承元: [`ReadDoc`](#ドキュメント読み取り型)

ローカルファイルからテキストを読む。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| 場所 | `location` | `str` | ✅ | - | 読み取り対象の絶対パス | - |

引数例:

```python
read_local("/home/user/repo/ai-monitor/docs/wiki/規約/コメント.md")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `str` | 読み取った本文 | UTF-8 デコード済み |

戻り値例:

```python
"# 規約: コメント\n..."
```

#### 処理

1. パスのファイルを UTF-8 で読んで返す

#### 例外

| 例外名 | 発生条件 | メッセージ | 補足 |
| --- | --- | --- | --- |
| `FileNotFoundError` | ファイルが存在しない | パス | 呼び出し元へそのまま伝播（フォールバックしない） |

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_read_local` | 正常 | ファイルの読み取り | 一時ファイルを作成 | なし | 本文が返る | - |
| `test_read_local_when_missing` | 異常 | ファイル不在 | 実在しないパス | なし | `FileNotFoundError` | 例外表「ファイルが存在しない」に対応 |

---

### ソース読み取り選択
> 物理名: `select_reader`<br>
> 種別: 関数

ベースの形から [`ReadDoc`](#ドキュメント読み取り型) の実装を選ぶ。
ローカルかネットワークかの判定を本関数 1 箇所に集約し、呼び出し側は選ばれた関数を使うだけにする。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| ベース | `base` | `str` | ✅ | - | Wiki ルートの raw URL またはローカル絶対パス | 設定の `wiki_base` / `ai_monitor_wiki_base` の値 |

引数例:

```python
select_reader("/home/user/repo/ai-monitor/docs/wiki")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| [`ReadDoc`](#ドキュメント読み取り型) | 場所から本文を読む関数 | - |

戻り値例:

```python
read_local
```

#### 処理

1. `base` が `http://` または `https://` で始まる場合、[URL 取得](#url-取得)を返す
2. それ以外の場合、[ローカル取得](#ローカル取得)を返す

#### 例外

なし

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_select_reader_when_https` | 正常 | リモートの選択 | `https://` で始まるベース | なし | [URL 取得](#url-取得)が返る | - |
| `test_select_reader_when_local_path` | 正常 | ローカルの選択 | 絶対パスのベース | なし | [ローカル取得](#ローカル取得)が返る | - |

---

### ドキュメント読み取り型
> 物理名: `ReadDoc`<br>
> 種別: 関数型

場所（URL / ローカルパス）から本文を返す関数のシグネチャ。
呼び出し側はキーワード引数 `read` でこの型を受け取り、取得手段を知らずに本文を得る。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| 場所 | `location` | `str` | ✅ | - | 読み取り対象の URL またはローカル絶対パス | ベースと相対パスを連結した完全な場所 |

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `str` | 読み取った本文 | UTF-8 デコード済み |

#### 実装

| 実装 | 補足 |
| --- | --- |
| [URL 取得](#url-取得) | ベースが `http://` / `https://` で始まるとき |
| [ローカル取得](#ローカル取得) | ベースがそれ以外（絶対パス）のとき |

## `inject/read_urls.py`
> 種別: ファイル

指定 URL の本文一式を標準出力に展開する CLI スクリプト。

---

### URL 正規化
> 物理名: `normalize_github_url`<br>
> 種別: 関数

GitHub blob URL を raw URL に変換する。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| URL | `url` | `str` | ✅ | - | 変換対象 URL | - |

引数例:

```python
normalize_github_url("https://github.com/o/r/blob/master/docs/wiki/規約/コメント.md")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `str` | 変換後の URL | blob 形式以外はそのまま返す |

戻り値例:

```python
"https://raw.githubusercontent.com/o/r/master/docs/wiki/規約/コメント.md"
```

#### 処理

1. `github.com/{owner}/{repo}/blob/{パス}` 形式か判定する
2. 一致する場合、`raw.githubusercontent.com/{owner}/{repo}/{パス}` に変換して返す
3. 一致しない場合、そのまま返す

#### 例外

なし

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_normalize_github_url` | 正常 | blob URL の raw 変換 | `github.com/{owner}/{repo}/blob/...` 形式の URL | なし | `raw.githubusercontent.com` の URL が返る | - |
| `test_normalize_github_url_when_not_blob` | 正常 | blob 形式以外はそのまま | raw URL | なし | 入力がそのまま返る | - |

---

### front matter 除去
> 物理名: `strip_frontmatter`<br>
> 種別: 関数

本文先頭の YAML front matter を除去する。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| 本文 | `text` | `str` | ✅ | - | 取得したページ本文 | - |

引数例:

```python
strip_frontmatter("---\ntitle: x\n---\n# 本文\n")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `str` | front matter を除いた本文 | 先頭に front matter が無ければそのまま返す |

戻り値例:

```python
"# 本文\n"
```

#### 処理

1. 先頭の `---` 行で囲まれた YAML front matter を 1 ブロックだけ除去して返す

#### 例外

なし

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_strip_frontmatter` | 正常 | front matter の除去 | 先頭に YAML front matter が付いた本文 | なし | front matter を除いた本文が返る | - |
| `test_strip_frontmatter_when_no_frontmatter` | 正常 | front matter なしはそのまま | front matter の無い本文 | なし | 入力がそのまま返る | - |

---

### CLI
> 物理名: `main`<br>
> 種別: 関数

URL 一覧を受けて、本文一式をラベル行 + md コードブロックで標準出力に展開する。

#### 引数

なし（コマンドライン引数 `urls` を読む）

引数例:

```python
main()
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `int` | 終了コード | `0` = 正常 / `1` = 引数不足・取得失敗 |

戻り値例:

```python
0
```

#### 処理

1. コマンドライン引数 `urls`（1 個以上）をパースする（不足なら stderr に使い方を出して `1` を返す）
2. 各 URL を raw URL に正規化する（[URL 正規化](#url-正規化)）
3. URL を順に取得し（[URL 取得](#url-取得)）、front matter を除去して（[front matter 除去](#front-matter-除去)）`**{取得元 URL}:**` のラベル行 + 5 連バッククォートの md コードブロックで標準出力に出す
   - ラベル行の URL は正規化後の取得 URL にする
4. 取得に失敗した場合、stderr に対象 URL を出して `1` を返す
5. 全件出力したら `0` を返す

#### 例外

なし

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_main_when_no_args` | 異常 | 引数不足 | 引数なしで実行 | urllib | stderr に使い方 + 戻り値 `1`・HTTP は呼ばれない | - |
| `test_main_when_fetch_failed` | 異常 | 取得失敗 | 存在しないページの URL で実行 | urllib | stderr に対象 URL + 戻り値 `1` | - |

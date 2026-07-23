# モジュール構成: 注入 / Wiki索引

`Wiki索引` ドメイン（注入側）に属する構成要素詳細。
SKILL.md の動的コンテキスト注入から呼ばれ、監視対象プロジェクトの Wiki を再帰的に辿って README `## 目次` 表から作った「ページ（raw URL）/ 概要」の 2 列表を標準出力に展開する。

## 一覧

| ユースケース | 役割 | コンテナ | 種別 | 名前 | 概要 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| Wiki索引注入 | URL 取得 | `inject/fetch.py` | 関数 | [`fetch_url`](./URLドキュメント.py.md#url-取得) | URL からテキストを取得する | URLドキュメント / エージェントドキュメント注入と共有 |
| Wiki索引注入 | Wiki ページ DTO | `inject/build_wiki_index.py` | データモデル | [`WikiPage`](#wiki-ページ) | 索引 1 件（raw URL + 概要） | Pydantic `BaseModel`（`frozen=True`）。[メイン](#メイン) 出力の各行に対応 |
| Wiki索引注入 | 目次表解析 | `inject/build_wiki_index.py` | 関数 | [`parse_index_table`](#目次表解析) | README 本文の `## 目次` 表を解析し、各リンクを raw URL 化した [`WikiPage`](#wiki-ページ) 配列を返す | raw URL ベースは環境変数 `WIKI_BASE` から取得。サブディレクトリのリンクは `README.md` に補完 |
| Wiki索引注入 | Wiki 再帰探索 | `inject/build_wiki_index.py` | 関数 | [`walk_wiki`](#wiki-再帰探索) | ルート README から目次表を辿って全 md ページを平坦化する | サブディレクトリ判定は [`WikiPage.raw_url`](#wiki-ページ) 末尾で行う |
| Wiki索引注入 | メイン | `inject/build_wiki_index.py` | 関数 | [`main`](#メイン) | プロジェクト Wiki の全 md ページを 2 列表で標準出力に展開する | - |

## ディレクトリ構成

```
plugins/ai-monitor/inject/
└── build_wiki_index.py     # WikiPage / parse_index_table / walk_wiki / main
```

`WikiPage` は Wiki 索引ドメイン専用 DTO のため、独立した `models.py` に切り出さず `build_wiki_index.py` 内に置く（他 CLI と共有しない）。

## 構成図

```mermaid
classDiagram
  メイン ..> Wiki再帰探索 : 全ページの収集
  Wiki再帰探索 ..> 目次表解析 : 行の抽出
  Wiki再帰探索 ..> URL取得 : README 取得
  Wiki再帰探索 ..> 環境変数 : WIKI_BASE 参照
  目次表解析 ..> 環境変数 : WIKI_BASE 参照
  目次表解析 ..> Wikiページ : 生成

  class メイン {
    <<function>>
    +メイン() int
  }
  class Wiki再帰探索 {
    <<function>>
    +Wiki再帰探索(フォルダパス) list~Wikiページ~
  }
  class 目次表解析 {
    <<function>>
    +目次表解析(本文, フォルダパス) list~Wikiページ~
  }
  class 環境変数 {
    <<env>>
    +WIKI_BASE: str
  }
  class URL取得 {
    <<function>>
    +URL取得(URL) str
  }
  class Wikiページ {
    <<pydantic>>
    +raw_url: str
    +summary: str
  }

  click メイン href "#メイン"
  click Wiki再帰探索 href "#wiki-再帰探索"
  click 目次表解析 href "#目次表解析"
  click URL取得 href "./URLドキュメント.py.md#url-取得"
  click Wikiページ href "#wiki-ページ"
```

## `inject/build_wiki_index.py`
> 種別: ファイル

プロジェクト Wiki の README を再帰的に辿ってフラット索引を標準出力に展開する CLI スクリプト。

---

### 目次表解析
> 物理名: `parse_index_table`<br>
> 種別: 関数

README 本文の `## 目次` 表を解析し、各リンクを raw URL 化した [`WikiPage`](#wiki-ページ) 配列で返す。
raw URL ベース（`WIKI_BASE`）は関数内部で環境変数から直接取得する。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| 本文 | `text` | `str` | ✅ | - | README ページの Markdown 本文 | - |
| フォルダパス | `folder_path` | `str` | ✅ | - | 当該 README が置かれているフォルダの Wiki ルートからの相対パス | ルート直下なら `""` |

引数例:

```python
parse_index_table(text, "設計図")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| [`list[WikiPage]`](#wiki-ページ) | 目次表の各行（登場順） | サブディレクトリの行は `raw_url` が `/README.md` で終わる（[`walk_wiki`](#wiki-再帰探索) の再帰判定に使う） |

戻り値例:

```python
[
    WikiPage(raw_url="https://.../docs/wiki/設計図/シナリオ/README.md", summary="シナリオ索引"),
    WikiPage(raw_url="https://.../docs/wiki/設計図/画面構成.md", summary="画面構成の一覧"),
]
```

#### 処理

1. 環境変数 `WIKI_BASE` を読む（末尾スラッシュがあれば落とす）
2. 本文から `## 目次` 見出しの次にある表を抽出する（見出しが無い or 「ページ」「概要」列が無い場合は `ValueError`）
3. ヘッダー行から「ページ」列と「概要」列のインデックスを特定する（他の列があってもよい）
4. 各データ行を先頭から順にループし、各行の [`WikiPage`](#wiki-ページ) を組み立てて戻り値配列に追加する
   1. 「ページ」セルの Markdown リンク `[表示](./xxx)` から URL 部分（ファイル名）を取り出し、先頭の `./` を落とす
   2. 末尾が `/`（サブディレクトリ）なら末尾に `README.md` を補完する
   3. 引数 `folder_path` を前置して Wiki ルート相対のパスを組み立てる（`folder_path` が空なら前置なし）
   4. `{WIKI_BASE}/{Wiki ルート相対パス}` を連結して `raw_url` を作り、「概要」セルを `summary` にした [`WikiPage`](#wiki-ページ) を戻り値配列に追加する
5. 戻り値配列を返す

#### 例外

| 例外名 | 発生条件 | メッセージ | 補足 |
| --- | --- | --- | --- |
| `ValueError` | `## 目次` セクションが無い or 表に「ページ」「概要」列が無い | `目次見出しなし` / `ページ／概要列なし` | 呼び出し元（[`walk_wiki`](#wiki-再帰探索)）で捕捉してそのフォルダ配下をスキップする（意図的な非公開運用） |
| `KeyError` | 環境変数 `WIKI_BASE` が未設定 | `WIKI_BASE` | 呼び出し側（[`main`](#メイン)）で事前に未設定チェックを行う前提。事前チェックを迂回した使い方をした場合の防護 |

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_parse_index_table` | 正常 | サブディレクトリ + md ページの混在 | `WIKI_BASE` 設定 + `folder_path="設計図"` + サブディレクトリと md が混在する目次表 | monkeypatch.setenv | サブディレクトリ行は `raw_url` が `/設計図/xxx/README.md`、md 行は `/設計図/xxx.md`、両方 [`WikiPage`](#wiki-ページ) | - |
| `test_parse_index_table_when_root` | 正常 | ルート直下（folder_path=`""`）の解析 | folder_path=`""` を渡す | monkeypatch.setenv | `raw_url` が `{WIKI_BASE}/xxx` の形（folder_path 前置なし） | - |
| `test_parse_index_table_when_extra_columns` | 正常 | 他の列が混じっていても取れる | ページ / 概要に加えて補足など別列を持つ目次表 | monkeypatch.setenv | ページと概要だけが登場順で取れる（例外なし） | - |
| `test_parse_index_table_when_no_toc_heading` | 異常 | 目次見出しなし | `## 目次` 見出しの無い本文 | monkeypatch.setenv | `ValueError`（`目次見出しなし`） | - |
| `test_parse_index_table_when_missing_columns` | 異常 | 表に必須列がない | 「ページ」or「概要」列を欠いた表 | monkeypatch.setenv | `ValueError`（`ページ／概要列なし`） | - |
| `test_parse_index_table_when_wiki_base_missing` | 異常 | `WIKI_BASE` 未設定 | 環境変数を消して呼び出す | monkeypatch.delenv | `KeyError` | [`main`](#メイン) が事前チェックを迂回した場合の防護 |

---

### Wiki 再帰探索
> 物理名: `walk_wiki`<br>
> 種別: 関数

ルート README から目次表を辿って全 md ページのエントリを平坦化する。
サブディレクトリ判定は [`WikiPage.raw_url`](#wiki-ページ) の末尾が `/README.md` かどうかで行う。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| フォルダパス | `folder_path` | `str` | - | `""` | 現在辿っているフォルダの Wiki ルートからの相対パス | 再帰呼び出しで積み上がる。初回は省略（ルート直下） |

引数例:

```python
walk_wiki()
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| [`list[WikiPage]`](#wiki-ページ) | 索引エントリ（深さ優先・親 → 子の順） | - |

戻り値例:

```python
[
    WikiPage(raw_url="https://.../docs/wiki/設計図/シナリオ/README.md", summary="全シナリオの索引"),
    WikiPage(raw_url="https://.../docs/wiki/設計図/シナリオ/単一ユースケース/実装.md", summary="実装フェーズの正常系 + 異常系"),
]
```

#### 処理

1. 環境変数 `WIKI_BASE` を読む（末尾スラッシュがあれば落とす）
2. `{WIKI_BASE}/{folder_path}/README.md` を取得する（`folder_path` が空ならルート直下・[URL 取得](./URLドキュメント.py.md#url-取得)）
3. [目次表解析](#目次表解析) に本文と `folder_path` を渡して [`WikiPage`](#wiki-ページ) 配列を得る（`ValueError` を捕捉した場合はそのフォルダ配下を空として返す = 意図的な非公開運用）
4. 空の戻り値配列を用意し、得た [`WikiPage`](#wiki-ページ) 配列を先頭から順に**本関数がループ**して分類しながら戻り値配列に追加する
   1. まず [`WikiPage`](#wiki-ページ) をそのまま戻り値配列に追加する
   2. `raw_url` が `/README.md` で終わる場合はサブディレクトリと判定し、`{WIKI_BASE}/` と末尾 `/README.md` を落として `folder_path` を計算し、本関数を再帰的に呼んで返ってきた配列を戻り値配列の末尾に連結する（親 → 子の順）
5. 深さ優先・親 → 子の順に平坦化された戻り値配列を返す

#### 例外

| 例外名 | 発生条件 | メッセージ | 補足 |
| --- | --- | --- | --- |
| `URLError` | README の取得失敗 | urllib のエラー内容 | [`fetch_url`](./URLドキュメント.py.md#url-取得) から伝播（ネットワーク断・404 は明示的に失敗させる） |
| `KeyError` | 環境変数 `WIKI_BASE` が未設定 | `WIKI_BASE` | 呼び出し側（[`main`](#メイン)）で事前に未設定チェックを行う前提 |

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_walk_wiki` | 正常 | 再帰的な平坦化 | ルート → サブディレクトリ 2 階層の README を持つ Wiki | monkeypatch.setenv + urllib | 深さ優先・親 → 子順の [`WikiPage`](#wiki-ページ) 配列（サブディレクトリの README は `raw_url` が `/README.md` で終わる） | - |
| `test_walk_wiki_when_format_violation` | 正常 | 書式違反フォルダのサイレントスキップ | サブディレクトリ README に `## 目次` が無い | monkeypatch.setenv + urllib | そのフォルダ配下だけが結果から抜け、他のフォルダは通常通り含まれる | 意図的な非公開運用 |
| `test_walk_wiki_when_fetch_failed` | 異常 | 途中の README 取得失敗 | サブディレクトリ README が 404 | monkeypatch.setenv + urllib | `URLError` が伝播 | - |

---

### メイン
> 物理名: `main`<br>
> 種別: 関数

プロジェクト Wiki の全 md ページを「ページ / 概要」2 列表で標準出力に展開する。

#### 引数

なし（環境変数 `WIKI_BASE` を読む）

引数例:

```python
main()
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `int` | 終了コード | `0` = 正常 / `1` = 環境変数未設定・取得失敗 |

戻り値例:

```python
0
```

#### 処理

1. 環境変数 `WIKI_BASE` を読む（未設定なら stderr にメッセージを出して `1` を返す）
2. [Wiki 再帰探索](#wiki-再帰探索) を呼んで [`WikiPage`](#wiki-ページ) 配列を得る（`URLError` は stderr に対象 URL + 原因を出して `1` を返す。書式違反は [`walk_wiki`](#wiki-再帰探索) で吸収済み）
3. `**Wiki索引:**` のラベル行 + 空行 + `| ページ | 概要 |` のヘッダー + 区切り行 + 各 [`WikiPage`](#wiki-ページ) の `| {raw_url} | {summary} |` を 1 枚の md テーブルとして標準出力に出して `0` を返す

#### 例外

なし（内部の `URLError` は捕捉して stderr + 戻り値 `1` に変換する）

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_main` | 正常 | 全エントリの表形式出力 | ルート + サブディレクトリの README を持つ Wiki を `WIKI_BASE` に設定して実行 | monkeypatch.setenv + urllib | 標準出力に `**Wiki索引:**` ラベル + 空行 + 「\| ページ \| 概要 \|」の md テーブル 1 枚が出て戻り値 `0` | - |
| `test_main_when_wiki_base_missing` | 異常 | `WIKI_BASE` 未設定 | 環境変数を消して実行 | monkeypatch.delenv | stderr にメッセージ + 戻り値 `1`・HTTP は呼ばれない | - |
| `test_main_when_fetch_failed` | 異常 | 途中の README 取得失敗 | サブディレクトリ README が 404 | monkeypatch.setenv + urllib | stderr に対象 URL + 原因 + 戻り値 `1`・標準出力に部分結果なし | - |

## Wiki ページ
> 物理名: `WikiPage`<br>
> 種別: データモデル<br>
> コンテナ: `inject/build_wiki_index.py`

Wiki 索引 1 件を表す DTO（Pydantic `BaseModel`・`frozen=True`）。
[目次表解析](#目次表解析) が生成し、[Wiki 再帰探索](#wiki-再帰探索) の戻り値要素となる。[メイン](#メイン) が「ページ / 概要」2 列表の各行として出力する。

### プロパティ

| 論理名 | プロパティ名 | 型 | 可視性 | デフォルト | 説明 | 例 | 補足 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| raw URL | `raw_url` | `str` | 公開 | - | ページの raw URL | `"https://raw.githubusercontent.com/o/p/master/docs/wiki/設計図/シナリオ/README.md"` | エージェントが Bash / WebFetch で直接読める形式。末尾が `/README.md` の場合は Wiki のサブディレクトリ索引（[`walk_wiki`](#wiki-再帰探索) の再帰対象）| |
| 概要 | `summary` | `str` | 公開 | - | 目次表「概要」列 | `"シナリオ索引"` | - |

### メソッド

なし

### 単体テスト

なし

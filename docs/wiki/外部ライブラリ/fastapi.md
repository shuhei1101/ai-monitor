# FastAPI

Python の Web API フレームワーク。
モニター本体のアプリ基盤として、MCP からの localhost HTTP の受信とポーリングループの駆動（lifespan）を担う。
起動サーバーには uvicorn を使う。

## 現在のバージョン情報

| 項目 | 内容 |
| --- | --- |
| バージョン | fastapi `0.139.2` / uvicorn `0.51.0` |
| ライセンス | MIT |
| 公式 URL | https://github.com/fastapi/fastapi |
| 公式ドキュメント | https://fastapi.tiangolo.com/ |

## インストール手順

```bash
uv add fastapi uvicorn
```

- テストは `fastapi.testclient.TestClient`（同梱）で実サーバーなしに実行する

## メソッド一覧

| 種別 | 名前 | 用途 | 補足 |
| --- | --- | --- | --- |
| クラス | [`FastAPI`](#fastapi-1) | アプリ本体の生成 | `lifespan` にバックグラウンド処理を配線 |
| デコレータ | [`app.post()` / `app.delete()`](#apppost--appdelete) | エンドポイントの登録 | Pydantic モデルで受信ボディを検証 |
| 例外 | [`HTTPException`](#httpexception) | エラー応答 | `status_code=404` 等 |
| 関数 | [`uvicorn.run()`](#uvicornrun) | サーバー起動 | `host="127.0.0.1"` 固定 |

### `FastAPI`

アプリ本体。
`lifespan` 引数に asynccontextmanager を渡すと、起動時 / 終了時の処理（ポーリングスレッドの起動・停止）を配線できる。

#### パラメータ

| パラメータ | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `lifespan` | asynccontextmanager | 起動 / 終了フック | yield の前が起動時・後が終了時 |

### `app.post()` / `app.delete()`

パスとハンドラ関数を登録するデコレータ。
ハンドラ引数に Pydantic モデルを型注釈すると受信ボディが自動検証される（不正は 422）。

### `HTTPException`

raise すると対応するステータスコードの JSON エラー応答になる。

#### パラメータ

| パラメータ | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `status_code` | int | 応答ステータスコード | `404` 等 |
| `detail` | str | エラー内容 | 応答ボディの `detail` になる |

### `uvicorn.run()`

ASGI サーバーの起動。

#### パラメータ

| パラメータ | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `app` | FastAPI | 起動するアプリ | - |
| `host` | str | バインド先 | `"127.0.0.1"` 固定（localhost のみ待受） |
| `port` | int | 待受ポート | 設定の `port` |

# Wikiページのオンデマンド取得

手順書・索引に出てくる Wiki ページを実行時に読む方法。
索引や本文中のリンクは Wiki 相対パスなので、`WIKI_BASE` と結合した URL で取得する。

## 取得コマンド

```bash
python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/{Wiki 相対パス}"
```

- `{Wiki 相対パス}` は `docs/wiki/` からのパス（例: `設計図/シナリオ/単一ユースケース/実装.md`）
- 複数ページは URL を並べて 1 回で取得できる
- ページ内の相対リンク（`./xxx.md` / `../yyy.md`）は、そのページのフォルダを基準に解決してから `WIKI_BASE` と結合する

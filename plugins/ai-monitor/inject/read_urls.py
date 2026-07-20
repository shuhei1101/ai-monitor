#!/usr/bin/env python3
"""指定 URL の本文一式を標準出力に展開する CLI。"""
from __future__ import annotations

import re
import sys
import urllib.error

from fetch import fetch_url

_BLOB_URL_RE = re.compile(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/blob/(.+)$")
_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)


def normalize_github_url(url: str) -> str:
    """GitHub blob URL を raw URL に変換する。"""
    # github.com/{owner}/{repo}/blob/{パス} 形式か判定する
    m = _BLOB_URL_RE.match(url)
    if not m:
        # blob 形式以外: そのまま返す
        return url
    # raw.githubusercontent.com に変換して返す
    owner, repo, rest = m.groups()
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"


def strip_frontmatter(text: str) -> str:
    """本文先頭の YAML front matter を除去する。"""
    # 先頭の --- 行で囲まれたブロックを 1 個だけ除去して返す
    return _FRONTMATTER_RE.sub("", text, count=1)


def main() -> int:
    """URL 一覧を受けて本文一式をラベル行 + md コードブロックで標準出力に展開する。"""
    # コマンドライン引数 urls をパースする
    if len(sys.argv) < 2:
        print("usage: read_urls.py <url>...", file=sys.stderr)
        return 1
    for arg in sys.argv[1:]:
        # 各 URL を raw URL に正規化する
        url = normalize_github_url(arg)
        # URL を順に取得し、front matter を除去する
        try:
            body = strip_frontmatter(fetch_url(url))
        except urllib.error.URLError as exc:
            # 取得失敗: 対象 URL を stderr に出してエラー終了する
            print(f"取得失敗: {url}: {exc}", file=sys.stderr)
            return 1
        # ラベル行 + 5 連バッククォートの md コードブロックで標準出力に出す
        print(f"**{url}:**")
        print("`````md")
        print(body.rstrip("\n"))
        print("`````")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

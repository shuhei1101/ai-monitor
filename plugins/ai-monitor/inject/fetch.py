"""注入 CLI 共通の URL 取得ヘルパー。"""
from __future__ import annotations

import urllib.parse
import urllib.request


def fetch_url(url: str) -> str:
    """URL からテキストを取得する。"""
    # URL のパス部分の非 ASCII 文字を quote する
    parts = urllib.parse.urlsplit(url)
    quoted = urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, urllib.parse.quote(parts.path), parts.query, parts.fragment)
    )
    # GET して本文を UTF-8 で返す
    with urllib.request.urlopen(quoted) as res:
        return res.read().decode("utf-8")

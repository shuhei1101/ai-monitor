"""注入 CLI 共通のドキュメント取得ヘルパー。"""
from __future__ import annotations

import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

# 場所（URL / ローカルパス）から本文を返す関数のシグネチャ
type ReadDoc = Callable[[str], str]

# ネットワーク経由で読む場所の接頭辞
_REMOTE_SCHEMES = ("http://", "https://")


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


def read_local(location: str) -> str:
    """ローカルファイルからテキストを読む。"""
    # パスのファイルを UTF-8 で読んで返す
    return Path(location).read_text(encoding="utf-8")


def select_reader(location: str) -> ReadDoc:
    """場所の形から ReadDoc の実装を選ぶ。"""
    # http(s) 始まりはネットワーク経由、それ以外はローカルファイルとして読む
    if location.startswith(_REMOTE_SCHEMES):
        return fetch_url
    return read_local

"""`plugins/ai-monitor/inject/fetch.py` の単体テスト。"""
from __future__ import annotations

import fetch

BASE = "https://raw.example.com/owner/repo/master/docs/wiki"


def test_fetch_url(fake_wiki):
    """非 ASCII パスの quote と取得（正常系）。"""
    # 準備
    url = f"{BASE}/規約/コメント.md"
    fake_wiki.pages[url] = "# 規約: コメント\n"
    # 実行
    body = fetch.fetch_url(url)
    # 検証
    quoted = (
        "https://raw.example.com/owner/repo/master/docs/wiki"
        "/%E8%A6%8F%E7%B4%84/%E3%82%B3%E3%83%A1%E3%83%B3%E3%83%88.md"
    )
    assert fake_wiki.calls == [quoted]
    assert body == "# 規約: コメント\n"

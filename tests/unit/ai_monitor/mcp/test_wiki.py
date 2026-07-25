"""`src/ai_monitor/mcp/wiki.py` の単体テスト。"""
from __future__ import annotations

import pytest

import ai_monitor.mcp.wiki as wiki

RAW_BASE = "https://raw.githubusercontent.com/o/r/master/docs/wiki"


# ---- Wikiページ取得 ----


def test_read_wiki_pages(fake_wiki):
    """複数ページの取得を確認する（正常系）。"""
    # 準備
    fake_wiki.pages[f"{RAW_BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    fake_wiki.pages[f"{RAW_BASE}/テンプレート/シナリオ.md"] = "# テンプレート: シナリオ\n"
    # 実行
    result = wiki.read_wiki_pages([f"{RAW_BASE}/規約/コメント.md", f"{RAW_BASE}/テンプレート/シナリオ.md"])
    # 検証
    assert [page.url for page in result.pages] == [
        f"{RAW_BASE}/規約/コメント.md",
        f"{RAW_BASE}/テンプレート/シナリオ.md",
    ]
    assert result.pages[0].body == "# 規約: コメント\n"


def test_read_wiki_pages_when_blob_url(fake_wiki):
    """blob URL の変換を確認する（正常系）。"""
    # 準備
    fake_wiki.pages[f"{RAW_BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    # 実行
    result = wiki.read_wiki_pages(["https://github.com/o/r/blob/master/docs/wiki/規約/コメント.md"])
    # 検証
    assert result.pages[0].url == f"{RAW_BASE}/規約/コメント.md"
    assert "raw.githubusercontent.com" in fake_wiki.calls[0]


def test_read_wiki_pages_when_frontmatter(fake_wiki):
    """front matter の除去を確認する（正常系）。"""
    # 準備
    fake_wiki.pages[f"{RAW_BASE}/テンプレート/シナリオ.md"] = "---\ntemplate_version: 1.0.0\n---\n# 見出し\n"
    # 実行
    result = wiki.read_wiki_pages([f"{RAW_BASE}/テンプレート/シナリオ.md"])
    # 検証
    assert result.pages[0].body == "# 見出し\n"


def test_read_wiki_pages_when_fetch_fails(fake_wiki):
    """取得失敗を確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(wiki.WikiFetchError, match="存在しないページ.md"):
        wiki.read_wiki_pages([f"{RAW_BASE}/存在しないページ.md"])

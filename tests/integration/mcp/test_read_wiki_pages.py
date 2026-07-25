"""「Wikiページ取得」の結合テスト。"""
from __future__ import annotations

import pytest

import ai_monitor.mcp.wiki as wiki

RAW_BASE = "https://raw.githubusercontent.com/shuhei1101/ai-monitor/master/docs/wiki"


def test_normal(api, fake_wiki):
    """複数 URL の取得 → 本文配列で返却の一連を確認する（正常系）。"""
    # 準備
    fake_wiki.pages[f"{RAW_BASE}/テンプレート/シナリオ.md"] = "# ai-monitor テンプレート: シナリオ\n"
    fake_wiki.pages[f"{RAW_BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    # 実行
    result = api.read_wiki_pages([f"{RAW_BASE}/テンプレート/シナリオ.md", f"{RAW_BASE}/規約/コメント.md"])
    # 検証
    assert [page.url for page in result.pages] == [
        f"{RAW_BASE}/テンプレート/シナリオ.md",
        f"{RAW_BASE}/規約/コメント.md",
    ]
    assert result.pages[0].body == "# ai-monitor テンプレート: シナリオ\n"


def test_normal_when_blob_url(api, fake_wiki):
    """blob URL を raw URL に変換して取得することを確認する（正常系・blob URL）。"""
    # 準備
    fake_wiki.pages[f"{RAW_BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    # 実行
    result = api.read_wiki_pages(
        ["https://github.com/shuhei1101/ai-monitor/blob/master/docs/wiki/規約/コメント.md"]
    )
    # 検証
    assert result.pages[0].url == f"{RAW_BASE}/規約/コメント.md"
    assert "raw.githubusercontent.com" in fake_wiki.calls[0]


def test_normal_when_frontmatter(api, fake_wiki):
    """本文先頭の YAML front matter を除去して返すことを確認する（正常系・front matter あり）。"""
    # 準備
    fake_wiki.pages[f"{RAW_BASE}/テンプレート/シナリオ.md"] = "---\ntemplate_version: 1.0.0\n---\n# 見出し\n"
    # 実行
    result = api.read_wiki_pages([f"{RAW_BASE}/テンプレート/シナリオ.md"])
    # 検証
    assert result.pages[0].body == "# 見出し\n"


def test_error_when_fetch_fails(api, fake_wiki):
    """存在しない URL でツールエラーになることを確認する（異常系・取得失敗）。"""
    # 実行・検証
    with pytest.raises(wiki.WikiFetchError, match="存在しないページ.md"):
        api.read_wiki_pages([f"{RAW_BASE}/存在しないページ.md"])

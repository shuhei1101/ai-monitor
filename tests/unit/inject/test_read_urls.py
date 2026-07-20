"""`plugins/ai-monitor/inject/read_urls.py` の単体テスト。"""
from __future__ import annotations

import sys

import read_urls

BASE = "https://raw.example.com/owner/repo/master/docs/wiki"


def test_normalize_github_url():
    """blob URL の raw 変換（正常系）。"""
    # 実行
    url = read_urls.normalize_github_url("https://github.com/o/r/blob/master/docs/wiki/規約/コメント.md")
    # 検証
    assert url == "https://raw.githubusercontent.com/o/r/master/docs/wiki/規約/コメント.md"


def test_normalize_github_url_when_not_blob():
    """blob 形式以外はそのまま（正常系）。"""
    # 準備
    raw = "https://raw.githubusercontent.com/o/r/master/docs/wiki/規約/コメント.md"
    # 実行
    url = read_urls.normalize_github_url(raw)
    # 検証
    assert url == raw


def test_strip_frontmatter():
    """front matter の除去（正常系）。"""
    # 実行
    body = read_urls.strip_frontmatter("---\ntitle: x\n---\n# 本文\n")
    # 検証
    assert body == "# 本文\n"


def test_strip_frontmatter_when_no_frontmatter():
    """front matter なしはそのまま（正常系）。"""
    # 実行
    body = read_urls.strip_frontmatter("# 本文\n")
    # 検証
    assert body == "# 本文\n"


def test_main_when_no_args(fake_wiki, monkeypatch, capsys):
    """引数不足（異常系）。"""
    # 準備
    monkeypatch.setattr(sys, "argv", ["read_urls.py"])
    # 実行
    code = read_urls.main()
    # 検証
    assert code == 1
    assert "usage" in capsys.readouterr().err
    assert fake_wiki.calls == []


def test_main_when_fetch_failed(fake_wiki, monkeypatch, capsys):
    """取得失敗（異常系）。"""
    # 準備
    monkeypatch.setattr(sys, "argv", ["read_urls.py", f"{BASE}/存在しないページ.md"])
    # 実行
    code = read_urls.main()
    # 検証
    assert code == 1
    assert f"{BASE}/存在しないページ.md" in capsys.readouterr().err

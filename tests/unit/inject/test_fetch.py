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


def test_read_local(tmp_path):
    """ファイルの読み取り（正常系）。"""
    # 準備
    path = tmp_path / "コメント.md"
    path.write_text("# 規約: コメント\n", encoding="utf-8")
    # 実行
    body = fetch.read_local(str(path))
    # 検証
    assert body == "# 規約: コメント\n"


def test_read_local_when_missing(tmp_path):
    """ファイル不在（異常系）。"""
    # 実行・検証
    import pytest

    with pytest.raises(FileNotFoundError):
        fetch.read_local(str(tmp_path / "missing.md"))


def test_select_reader_when_https():
    """リモートの選択（正常系）。"""
    # 実行
    reader = fetch.select_reader(f"{BASE}/規約/コメント.md")
    # 検証
    assert reader is fetch.fetch_url


def test_select_reader_when_local_path():
    """ローカルの選択（正常系）。"""
    # 実行
    reader = fetch.select_reader("/home/user/repo/ai-monitor/docs/wiki/規約/コメント.md")
    # 検証
    assert reader is fetch.read_local

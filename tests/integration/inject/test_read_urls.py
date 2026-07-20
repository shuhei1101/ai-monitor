"""「URLドキュメント注入」の結合テスト。"""
from __future__ import annotations

import sys

import read_urls

BASE = "https://raw.example.com/owner/repo/master/docs/wiki"


def test_normal(fake_wiki, monkeypatch, capsys):
    """複数 URL の取得 → md コードブロックで連結出力を確認する（正常系）。"""
    # 準備
    monkeypatch.setattr(sys, "argv", ["read_urls.py", f"{BASE}/規約/コメント.md", f"{BASE}/規約/マージ手順.md"])
    fake_wiki.pages[f"{BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    fake_wiki.pages[f"{BASE}/規約/マージ手順.md"] = "# 規約: マージ手順\n"
    # 実行
    code = read_urls.main()
    # 検証
    assert code == 0
    assert capsys.readouterr().out == (
        f"**{BASE}/規約/コメント.md:**\n"
        "`````md\n"
        "# 規約: コメント\n"
        "`````\n"
        "\n"
        f"**{BASE}/規約/マージ手順.md:**\n"
        "`````md\n"
        "# 規約: マージ手順\n"
        "`````\n"
        "\n"
    )


def test_normal_when_blob_url(fake_wiki, monkeypatch, capsys):
    """GitHub blob URL を raw URL に変換して取得することを確認する（正常系）。"""
    # 準備
    monkeypatch.setattr(sys, "argv", ["read_urls.py", "https://github.com/o/r/blob/master/docs/rules/スタイル.md"])
    raw = "https://raw.githubusercontent.com/o/r/master/docs/rules/スタイル.md"
    fake_wiki.pages[raw] = "# スタイル\n"
    # 実行
    code = read_urls.main()
    # 検証
    assert code == 0
    out = capsys.readouterr().out
    assert out.startswith(f"**{raw}:**\n")
    # raw URL（quote 済み）でリクエストされている
    assert fake_wiki.calls == [
        "https://raw.githubusercontent.com/o/r/master/docs/rules/%E3%82%B9%E3%82%BF%E3%82%A4%E3%83%AB.md"
    ]


def test_normal_when_front_matter(fake_wiki, monkeypatch, capsys):
    """本文先頭の YAML front matter を除去して出力することを確認する（正常系）。"""
    # 準備
    monkeypatch.setattr(sys, "argv", ["read_urls.py", f"{BASE}/規約/コメント.md"])
    fake_wiki.pages[f"{BASE}/規約/コメント.md"] = "---\ntitle: コメント\n---\n# 規約: コメント\n"
    # 実行
    code = read_urls.main()
    # 検証
    assert code == 0
    out = capsys.readouterr().out
    assert "title: コメント" not in out
    assert "# 規約: コメント" in out


def test_error_when_fetch_failed(fake_wiki, monkeypatch, capsys):
    """存在しない URL でエラー終了することを確認する（異常系）。"""
    # 準備
    monkeypatch.setattr(sys, "argv", ["read_urls.py", f"{BASE}/存在しないページ.md"])
    # 実行
    code = read_urls.main()
    # 検証
    assert code == 1
    assert f"{BASE}/存在しないページ.md" in capsys.readouterr().err

"""`plugins/ai-monitor/inject/build_wiki_index.py` の単体テスト。"""
from __future__ import annotations

import sys
import urllib.error

import pytest

import build_wiki_index
from build_wiki_index import WikiPage

BASE = "https://raw.example.com/owner/repo/master/docs/wiki"


# =========================
# parse_index_table
# =========================


def test_parse_index_table(monkeypatch):
    """サブディレクトリ + md ページ混在の目次表を WikiPage 配列に変換する（正常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    text = (
        "# 設計図\n"
        "\n"
        "## 目次\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [シナリオ](./シナリオ/) | シナリオ索引 |\n"
        "| [画面構成](./画面構成.md) | 画面構成の一覧 |\n"
    )
    # 実行
    pages = build_wiki_index.parse_index_table(text, "設計図")
    # 検証: サブディレクトリは README.md 補完 + folder_path 前置 + raw URL 化
    assert pages == [
        WikiPage(raw_url=f"{BASE}/設計図/シナリオ/README.md", summary="シナリオ索引"),
        WikiPage(raw_url=f"{BASE}/設計図/画面構成.md", summary="画面構成の一覧"),
    ]


def test_parse_index_table_when_root(monkeypatch):
    """ルート直下（folder_path=""）で folder_path 前置なしの raw URL を作る（正常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    text = (
        "## 目次\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [設計図](./設計図/) | 設計図配下 |\n"
        "| [規約](./規約.md) | 規約ページ |\n"
    )
    # 実行
    pages = build_wiki_index.parse_index_table(text, "")
    # 検証: folder_path 前置なし
    assert pages == [
        WikiPage(raw_url=f"{BASE}/設計図/README.md", summary="設計図配下"),
        WikiPage(raw_url=f"{BASE}/規約.md", summary="規約ページ"),
    ]


def test_parse_index_table_when_extra_columns(monkeypatch):
    """他の列が混じっていても取れる（正常系）。"""
    # 準備: ページ / 概要 の間・両側に別列を挟む
    monkeypatch.setenv("WIKI_BASE", BASE)
    text = (
        "## 目次\n"
        "\n"
        "| 種別 | ページ | 補足 | 概要 |\n"
        "| --- | --- | --- | --- |\n"
        "| フォルダ | [シナリオ](./シナリオ/) | - | シナリオ索引 |\n"
        "| 単体 | [画面構成](./画面構成.md) | 実装後 | 画面構成の一覧 |\n"
    )
    # 実行
    pages = build_wiki_index.parse_index_table(text, "設計図")
    # 検証
    assert pages == [
        WikiPage(raw_url=f"{BASE}/設計図/シナリオ/README.md", summary="シナリオ索引"),
        WikiPage(raw_url=f"{BASE}/設計図/画面構成.md", summary="画面構成の一覧"),
    ]


def test_parse_index_table_when_no_toc_heading(monkeypatch):
    """目次見出しなし（異常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    text = (
        "# 設計図\n"
        "\n"
        "## 一覧\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [シナリオ](./シナリオ/) | シナリオ索引 |\n"
    )
    # 実行・検証
    with pytest.raises(ValueError, match="目次見出しなし"):
        build_wiki_index.parse_index_table(text, "設計図")


def test_parse_index_table_when_missing_columns(monkeypatch):
    """表に必須列がない（異常系）。"""
    # 準備: 「概要」列を欠いた表
    monkeypatch.setenv("WIKI_BASE", BASE)
    text = (
        "## 目次\n"
        "\n"
        "| ページ | 補足 |\n"
        "| --- | --- |\n"
        "| [シナリオ](./シナリオ/) | - |\n"
    )
    # 実行・検証
    with pytest.raises(ValueError, match="ページ／概要列なし"):
        build_wiki_index.parse_index_table(text, "設計図")


def test_parse_index_table_when_wiki_base_missing(monkeypatch):
    """WIKI_BASE 未設定（異常系）。"""
    # 準備
    monkeypatch.delenv("WIKI_BASE", raising=False)
    text = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [規約](./規約.md) | 規約ページ |\n"
    )
    # 実行・検証
    with pytest.raises(KeyError, match="WIKI_BASE"):
        build_wiki_index.parse_index_table(text, "")


# =========================
# walk_wiki
# =========================


def test_walk_wiki(monkeypatch, fake_wiki):
    """再帰的な平坦化（正常系）。"""
    # 準備: ルート → サブディレクトリ 2 階層
    monkeypatch.setenv("WIKI_BASE", BASE)
    fake_wiki.pages[f"{BASE}/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [設計図](./設計図/) | 設計図配下 |\n"
        "| [規約](./規約.md) | 規約ページ |\n"
    )
    fake_wiki.pages[f"{BASE}/設計図/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [シナリオ](./シナリオ/) | シナリオ索引 |\n"
        "| [画面構成](./画面構成.md) | 画面構成の一覧 |\n"
    )
    fake_wiki.pages[f"{BASE}/設計図/シナリオ/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [実装](./実装.md) | 実装フェーズ |\n"
    )
    # 実行
    entries = build_wiki_index.walk_wiki()
    # 検証: 深さ優先・親 → 子順
    assert entries == [
        WikiPage(raw_url=f"{BASE}/設計図/README.md", summary="設計図配下"),
        WikiPage(raw_url=f"{BASE}/設計図/シナリオ/README.md", summary="シナリオ索引"),
        WikiPage(raw_url=f"{BASE}/設計図/シナリオ/実装.md", summary="実装フェーズ"),
        WikiPage(raw_url=f"{BASE}/設計図/画面構成.md", summary="画面構成の一覧"),
        WikiPage(raw_url=f"{BASE}/規約.md", summary="規約ページ"),
    ]


def test_walk_wiki_when_format_violation(monkeypatch, fake_wiki):
    """書式違反フォルダのサイレントスキップ（正常系）。"""
    # 準備: サブディレクトリ README に `## 目次` がない
    monkeypatch.setenv("WIKI_BASE", BASE)
    fake_wiki.pages[f"{BASE}/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [公開](./公開/) | 公開索引 |\n"
        "| [非公開](./非公開/) | 非公開索引 |\n"
    )
    fake_wiki.pages[f"{BASE}/公開/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [記事](./記事.md) | 公開記事 |\n"
    )
    # 非公開: `## 目次` なし
    fake_wiki.pages[f"{BASE}/非公開/README.md"] = "# 非公開\n\n中身は載せない。\n"
    # 実行
    entries = build_wiki_index.walk_wiki()
    # 検証: 非公開配下だけ抜け、公開は通常通り含まれる
    assert entries == [
        WikiPage(raw_url=f"{BASE}/公開/README.md", summary="公開索引"),
        WikiPage(raw_url=f"{BASE}/公開/記事.md", summary="公開記事"),
        WikiPage(raw_url=f"{BASE}/非公開/README.md", summary="非公開索引"),
    ]


def test_walk_wiki_when_fetch_failed(monkeypatch, fake_wiki):
    """途中の README 取得失敗（異常系）。"""
    # 準備: サブディレクトリ README が 404
    monkeypatch.setenv("WIKI_BASE", BASE)
    fake_wiki.pages[f"{BASE}/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [欠落](./欠落/) | 欠落索引 |\n"
    )
    # `{BASE}/欠落/README.md` は未登録 → fake_wiki は URLError を投げる
    # 実行・検証
    with pytest.raises(urllib.error.URLError):
        build_wiki_index.walk_wiki()


# =========================
# main (CLI)
# =========================


def test_main(monkeypatch, fake_wiki, capsys):
    """全エントリの表形式出力（正常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["build_wiki_index.py"])
    fake_wiki.pages[f"{BASE}/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [規約](./規約.md) | 規約ページ |\n"
    )
    # 実行
    code = build_wiki_index.main()
    # 検証
    assert code == 0
    out = capsys.readouterr().out
    assert out == (
        "**Wiki索引:**\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        f"| {BASE}/規約.md | 規約ページ |\n"
    )


def test_main_when_wiki_base_missing(monkeypatch, fake_wiki, capsys):
    """WIKI_BASE 未設定（異常系）。"""
    # 準備
    monkeypatch.delenv("WIKI_BASE", raising=False)
    monkeypatch.setattr(sys, "argv", ["build_wiki_index.py"])
    # 実行
    code = build_wiki_index.main()
    # 検証
    assert code == 1
    assert "WIKI_BASE" in capsys.readouterr().err
    assert fake_wiki.calls == []


def test_main_when_fetch_failed(monkeypatch, fake_wiki, capsys):
    """途中の README 取得失敗（異常系）。"""
    # 準備: サブディレクトリ README が未登録（404 相当）
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["build_wiki_index.py"])
    fake_wiki.pages[f"{BASE}/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [欠落](./欠落/) | 欠落索引 |\n"
    )
    # 実行
    code = build_wiki_index.main()
    # 検証
    assert code == 1
    err = capsys.readouterr().err
    assert f"{BASE}/欠落/README.md" in err
    # 部分結果を stdout に出さない
    assert capsys.readouterr().out == ""

"""「Wiki索引注入」の結合テスト。"""
from __future__ import annotations

import sys

import build_wiki_index

BASE = "https://raw.example.com/owner/repo/master/docs/wiki"


def _setup_wiki(fake_wiki):
    """ルート + 設計図/ + 設計図/シナリオ/ の 3 階層 README を仕込む。"""
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
    )
    fake_wiki.pages[f"{BASE}/設計図/シナリオ/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [実装](./実装.md) | 実装フェーズ |\n"
    )


def test_normal(fake_wiki, monkeypatch, capsys):
    """全 README を辿って 2 列テーブルを出力する（正常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["build_wiki_index.py"])
    _setup_wiki(fake_wiki)
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
        f"| {BASE}/設計図/README.md | 設計図配下 |\n"
        f"| {BASE}/設計図/シナリオ/README.md | シナリオ索引 |\n"
        f"| {BASE}/設計図/シナリオ/実装.md | 実装フェーズ |\n"
        f"| {BASE}/規約.md | 規約ページ |\n"
    )


def test_normal_when_format_violation(fake_wiki, monkeypatch, capsys):
    """途中の README に `## 目次` が無い → そのフォルダ配下だけスキップ（正常系）。"""
    # 準備: 非公開フォルダは `## 目次` を持たない
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["build_wiki_index.py"])
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
    fake_wiki.pages[f"{BASE}/非公開/README.md"] = "# 非公開\n\n中身は載せない。\n"
    # 実行
    code = build_wiki_index.main()
    # 検証: 非公開配下は出ないが、非公開/README 行と公開系は出る
    assert code == 0
    out = capsys.readouterr().out
    assert f"{BASE}/公開/README.md" in out
    assert f"{BASE}/公開/記事.md" in out
    assert f"{BASE}/非公開/README.md" in out
    # 非公開の中身（架空のページ）は出ていない
    assert "非公開の記事" not in out


def test_error_when_wiki_base_missing(fake_wiki, monkeypatch, capsys):
    """`WIKI_BASE` 未設定でエラー終了（異常系）。"""
    # 準備
    monkeypatch.delenv("WIKI_BASE", raising=False)
    monkeypatch.setattr(sys, "argv", ["build_wiki_index.py"])
    # 実行
    code = build_wiki_index.main()
    # 検証
    assert code == 1
    assert "WIKI_BASE" in capsys.readouterr().err
    assert fake_wiki.calls == []


def test_error_when_fetch_failed(fake_wiki, monkeypatch, capsys):
    """途中の README 取得失敗でエラー終了（異常系）。"""
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

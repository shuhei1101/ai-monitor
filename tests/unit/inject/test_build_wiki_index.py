"""`plugins/ai-monitor/inject/build_wiki_index.py` の単体テスト。"""
from __future__ import annotations

import sys

import pytest

import build_wiki_index
from build_wiki_index import WikiPage
from fetch import fetch_url, read_local

BASE = "https://raw.example.com/owner/repo/master/docs/wiki"


def _write_wiki(root, pages: dict[str, str]) -> str:
    """一時ディレクトリに Wiki を作成し、ベースとなる絶対パスを返す。"""
    for rel, body in pages.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return str(root)


# =========================
# parse_index_table
# =========================


def test_parse_index_table():
    """サブディレクトリ + md ページ混在の目次表を WikiPage 配列に変換する（正常系）。"""
    # 準備
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
    pages = build_wiki_index.parse_index_table(text, "設計図", BASE)
    # 検証: サブディレクトリは README.md 補完 + folder_path 前置 + ベース連結
    assert pages == [
        WikiPage(raw_url=f"{BASE}/設計図/シナリオ/README.md", summary="シナリオ索引"),
        WikiPage(raw_url=f"{BASE}/設計図/画面構成.md", summary="画面構成の一覧"),
    ]


def test_parse_index_table_when_root():
    """ルート直下（folder_path=""）で folder_path 前置なしの場所を作る（正常系）。"""
    # 準備
    text = (
        "## 目次\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [設計図](./設計図/) | 設計図配下 |\n"
        "| [規約](./規約.md) | 規約ページ |\n"
    )
    # 実行
    pages = build_wiki_index.parse_index_table(text, "", BASE)
    # 検証: folder_path 前置なし
    assert pages == [
        WikiPage(raw_url=f"{BASE}/設計図/README.md", summary="設計図配下"),
        WikiPage(raw_url=f"{BASE}/規約.md", summary="規約ページ"),
    ]


def test_parse_index_table_when_local_base():
    """ローカルパスのベース（正常系）。"""
    # 準備
    local_base = "/home/user/repo/ai-monitor-e2e/docs/wiki"
    text = (
        "## 目次\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [規約](./規約.md) | 規約ページ |\n"
    )
    # 実行
    pages = build_wiki_index.parse_index_table(text, "", local_base)
    # 検証: ローカルパスとして連結される
    assert pages == [WikiPage(raw_url=f"{local_base}/規約.md", summary="規約ページ")]


def test_parse_index_table_when_extra_columns():
    """他の列が混じっていても取れる（正常系）。"""
    # 準備: ページ / 概要 の間・両側に別列を挟む
    text = (
        "## 目次\n"
        "\n"
        "| 種別 | ページ | 補足 | 概要 |\n"
        "| --- | --- | --- | --- |\n"
        "| フォルダ | [シナリオ](./シナリオ/) | - | シナリオ索引 |\n"
        "| 単体 | [画面構成](./画面構成.md) | 実装後 | 画面構成の一覧 |\n"
    )
    # 実行
    pages = build_wiki_index.parse_index_table(text, "設計図", BASE)
    # 検証
    assert pages == [
        WikiPage(raw_url=f"{BASE}/設計図/シナリオ/README.md", summary="シナリオ索引"),
        WikiPage(raw_url=f"{BASE}/設計図/画面構成.md", summary="画面構成の一覧"),
    ]


def test_parse_index_table_when_fenced_example():
    """コードブロック内の記述例を無視する（正常系）。"""
    # 準備: 実際の目次表の後ろに、書式の記述例として同じ見出しを含むコードブロックを置く
    text = (
        "## 目次\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [フェーズ](./フェーズ/フェーズ.md) | フェーズページの書式定義 |\n"
        "\n"
        "### 記述例\n"
        "\n"
        "```markdown\n"
        "## 目次\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [初期処理](./フェーズ/初期処理.md) | 最新状態の取得 |\n"
        "```\n"
    )
    # 実行
    pages = build_wiki_index.parse_index_table(text, "エージェント/テンプレート", BASE)
    # 検証: 記述例の行は含まれない
    assert pages == [
        WikiPage(
            raw_url=f"{BASE}/エージェント/テンプレート/フェーズ/フェーズ.md",
            summary="フェーズページの書式定義",
        )
    ]


def test_parse_index_table_when_no_toc_heading():
    """目次見出しなし（異常系）。"""
    # 準備
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
        build_wiki_index.parse_index_table(text, "設計図", BASE)


def test_parse_index_table_when_missing_columns():
    """表に必須列がない（異常系）。"""
    # 準備: 「概要」列を欠いた表
    text = (
        "## 目次\n"
        "\n"
        "| ページ | 補足 |\n"
        "| --- | --- |\n"
        "| [シナリオ](./シナリオ/) | - |\n"
    )
    # 実行・検証
    with pytest.raises(ValueError, match="ページ／概要列なし"):
        build_wiki_index.parse_index_table(text, "設計図", BASE)


# =========================
# walk_wiki
# =========================


def test_walk_wiki(tmp_path):
    """再帰的な平坦化（正常系）。"""
    # 準備: ルート → サブディレクトリ 2 階層
    base = _write_wiki(
        tmp_path,
        {
            "README.md": (
                "## 目次\n\n"
                "| ページ | 概要 |\n"
                "| --- | --- |\n"
                "| [設計図](./設計図/) | 設計図配下 |\n"
                "| [規約](./規約.md) | 規約ページ |\n"
            ),
            "設計図/README.md": (
                "## 目次\n\n"
                "| ページ | 概要 |\n"
                "| --- | --- |\n"
                "| [シナリオ](./シナリオ/) | シナリオ索引 |\n"
                "| [画面構成](./画面構成.md) | 画面構成の一覧 |\n"
            ),
            "設計図/シナリオ/README.md": (
                "## 目次\n\n"
                "| ページ | 概要 |\n"
                "| --- | --- |\n"
                "| [実装](./実装.md) | 実装フェーズ |\n"
            ),
        },
    )
    # 実行
    entries = build_wiki_index.walk_wiki(base, read=read_local)
    # 検証: 深さ優先・親 → 子順
    assert entries == [
        WikiPage(raw_url=f"{base}/設計図/README.md", summary="設計図配下"),
        WikiPage(raw_url=f"{base}/設計図/シナリオ/README.md", summary="シナリオ索引"),
        WikiPage(raw_url=f"{base}/設計図/シナリオ/実装.md", summary="実装フェーズ"),
        WikiPage(raw_url=f"{base}/設計図/画面構成.md", summary="画面構成の一覧"),
        WikiPage(raw_url=f"{base}/規約.md", summary="規約ページ"),
    ]


def test_walk_wiki_when_format_violation(tmp_path):
    """書式違反フォルダのサイレントスキップ（正常系）。"""
    # 準備: サブディレクトリ README に `## 目次` がない
    base = _write_wiki(
        tmp_path,
        {
            "README.md": (
                "## 目次\n\n"
                "| ページ | 概要 |\n"
                "| --- | --- |\n"
                "| [公開](./公開/) | 公開索引 |\n"
                "| [非公開](./非公開/) | 非公開索引 |\n"
            ),
            "公開/README.md": (
                "## 目次\n\n"
                "| ページ | 概要 |\n"
                "| --- | --- |\n"
                "| [記事](./記事.md) | 公開記事 |\n"
            ),
            "非公開/README.md": "# 非公開\n\n中身は載せない。\n",
        },
    )
    # 実行
    entries = build_wiki_index.walk_wiki(base, read=read_local)
    # 検証: 非公開配下だけ抜け、公開は通常通り含まれる
    assert entries == [
        WikiPage(raw_url=f"{base}/公開/README.md", summary="公開索引"),
        WikiPage(raw_url=f"{base}/公開/記事.md", summary="公開記事"),
        WikiPage(raw_url=f"{base}/非公開/README.md", summary="非公開索引"),
    ]


def test_walk_wiki_when_fetch_failed(tmp_path):
    """取得失敗フォルダのサイレントスキップ（正常系）。"""
    # 準備: 欠落配下の README を作らない
    base = _write_wiki(
        tmp_path,
        {
            "README.md": (
                "## 目次\n\n"
                "| ページ | 概要 |\n"
                "| --- | --- |\n"
                "| [公開](./公開/) | 公開索引 |\n"
                "| [欠落](./欠落/) | 欠落索引 |\n"
            ),
            "公開/README.md": (
                "## 目次\n\n"
                "| ページ | 概要 |\n"
                "| --- | --- |\n"
                "| [記事](./記事.md) | 公開記事 |\n"
            ),
        },
    )
    # 実行
    entries = build_wiki_index.walk_wiki(base, read=read_local)
    # 検証: 欠落配下は結果から抜けるが、親目次の欠落/README 行と公開系は含まれる
    assert entries == [
        WikiPage(raw_url=f"{base}/公開/README.md", summary="公開索引"),
        WikiPage(raw_url=f"{base}/公開/記事.md", summary="公開記事"),
        WikiPage(raw_url=f"{base}/欠落/README.md", summary="欠落索引"),
    ]


def test_walk_wiki_when_root_missing(tmp_path):
    """ルート README 取得失敗（正常系）。"""
    # 準備: ルート README を作らない
    base = str(tmp_path)
    # 実行
    entries = build_wiki_index.walk_wiki(base, read=read_local)
    # 検証: 空配列（例外は伝播しない）
    assert entries == []


def test_walk_wiki_when_remote_base(fake_wiki):
    """リモートベースの探索（正常系）。"""
    # 準備
    fake_wiki.pages[f"{BASE}/README.md"] = (
        "## 目次\n\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
        "| [規約](./規約.md) | 規約ページ |\n"
    )
    # 実行
    entries = build_wiki_index.walk_wiki(BASE, read=fetch_url)
    # 検証: HTTP 経由で辿れる
    assert entries == [WikiPage(raw_url=f"{BASE}/規約.md", summary="規約ページ")]
    assert fake_wiki.calls


# =========================
# main (CLI)
# =========================


def test_main(monkeypatch, tmp_path, capsys):
    """全エントリの表形式出力（正常系）。"""
    # 準備
    base = _write_wiki(
        tmp_path,
        {
            "README.md": (
                "## 目次\n\n"
                "| ページ | 概要 |\n"
                "| --- | --- |\n"
                "| [規約](./規約.md) | 規約ページ |\n"
            )
        },
    )
    monkeypatch.setenv("WIKI_BASE", base)
    monkeypatch.setattr(sys, "argv", ["build_wiki_index.py"])
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
        f"| {base}/規約.md | 規約ページ |\n"
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


def test_main_when_root_missing(monkeypatch, tmp_path, capsys):
    """ルート README 取得失敗時の空索引出力（正常系）。"""
    # 準備: ルート README を作らない
    monkeypatch.setenv("WIKI_BASE", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["build_wiki_index.py"])
    # 実行
    code = build_wiki_index.main()
    # 検証: ラベル + ヘッダー行のみの空テーブル
    assert code == 0
    out = capsys.readouterr().out
    assert out == (
        "**Wiki索引:**\n"
        "\n"
        "| ページ | 概要 |\n"
        "| --- | --- |\n"
    )

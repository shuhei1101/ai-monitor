"""`plugins/ai-monitor/inject/read_agent_docs.py` の単体テスト。"""
from __future__ import annotations

import sys
import urllib.parse

import pytest

import read_agent_docs

BASE = "https://raw.example.com/owner/repo/master/docs/wiki"
COMMON_BASE = "https://raw.example.com/owner/ai-monitor/master/docs/wiki"

README = """# Claudeハーネス

## 目次

| ページ | 概要 |
| --- | --- |
| [エージェント参照ドキュメント対応表](./共通対応表/エージェント参照ドキュメント対応表.md) | エージェント × 共通ドキュメントの星取り表 |
| [エージェント言語規約対応表](./対応表/エージェント言語規約対応表.md) | エージェント × dev-kit 言語規約の星取り表 |
| [プロジェクトドキュメント対応表](./対応表/プロジェクトドキュメント対応表.md) | エージェント × プロジェクト固有設計書の星取り表 |
| [環境変数の解決](./共通ルール/環境変数の解決.md) | 環境変数を実値に解決する共通手順 |
| [エージェント一覧](./エージェント一覧.md) | エージェントの一覧 |
"""

README_NO_PAGES = """# Claudeハーネス

## 目次

| ページ | 概要 |
| --- | --- |
| [エージェント一覧](./エージェント一覧.md) | エージェントの一覧 |
"""

MATRIX_COMMON = """# エージェント参照ドキュメント対応表

| ドキュメント | intake-issue-triager | epic-conductor |
| --- | --- | --- |
| [規約/コメント.md](../../規約/コメント.md) | ○ | ○ |
| [判定フローチャート/レイヤー.md](../../判定フローチャート/レイヤー.md) | ○ | - |
"""

MATRIX_PROJECT = """# プロジェクトドキュメント対応表

| ドキュメント | intake-issue-triager | epic-conductor |
| --- | --- | --- |
| [設計図/シナリオ/README.md](../../設計図/シナリオ/README.md) | ○ | ○ |
"""

MATRIX_LANG = """# エージェント言語規約対応表

| ドキュメント | architect |
| --- | --- |
| [python/core/スタイル.md](https://raw.example.com/rules/python/core/スタイル.md) | ○ |
"""

DOCS_MATRIX = """# エージェント参照ドキュメント対応表

| ドキュメント | intake-issue-triager | epic-conductor |
| --- | --- | --- |
| [規約/コメント.md](../規約/コメント.md) | ○ | ○ |
| [規約/マージ手順.md](../規約/マージ手順.md) | - | ○ |
| [判定フローチャート/レイヤー.md](../判定フローチャート/レイヤー.md) | ○ | - |
"""

LANG_MATRIX = """# エージェント言語規約対応表

| ドキュメント | architect |
| --- | --- |
| [python/core/スタイル.md](https://raw.example.com/rules/python/core/スタイル.md) | ○ |
"""


def _readme_calls(fake_wiki):
    return [c for c in fake_wiki.calls if urllib.parse.unquote(c).endswith("Claudeハーネス/README.md")]


def _setup_matrices(fake_wiki, base):
    fake_wiki.pages[f"{base}/Claudeハーネス/README.md"] = README
    fake_wiki.pages[f"{base}/Claudeハーネス/共通対応表/エージェント参照ドキュメント対応表.md"] = MATRIX_COMMON
    fake_wiki.pages[f"{base}/Claudeハーネス/対応表/エージェント言語規約対応表.md"] = MATRIX_LANG
    fake_wiki.pages[f"{base}/Claudeハーネス/対応表/プロジェクトドキュメント対応表.md"] = MATRIX_PROJECT


def _setup_docs(fake_wiki, base):
    fake_wiki.pages[f"{base}/Claudeハーネス/共通ルール/環境変数の解決.md"] = "# 環境変数の解決\n"
    fake_wiki.pages[f"{base}/規約/コメント.md"] = "# 規約: コメント\n"
    fake_wiki.pages[f"{base}/判定フローチャート/レイヤー.md"] = "# レイヤー\n"
    fake_wiki.pages[f"{base}/設計図/シナリオ/README.md"] = "# シナリオ\n"


def test_list_harness_pages(fake_wiki):
    """分類フォルダごとの振り分け（正常系）。"""
    # 準備
    fake_wiki.pages[f"{BASE}/Claudeハーネス/README.md"] = README
    # 実行
    pages = read_agent_docs.list_harness_pages(BASE)
    # 検証
    assert pages == {
        "共通対応表": [
            ("エージェント参照ドキュメント対応表", "Claudeハーネス/共通対応表/エージェント参照ドキュメント対応表.md"),
        ],
        "対応表": [
            ("エージェント言語規約対応表", "Claudeハーネス/対応表/エージェント言語規約対応表.md"),
            ("プロジェクトドキュメント対応表", "Claudeハーネス/対応表/プロジェクトドキュメント対応表.md"),
        ],
        "共通ルール": [
            ("環境変数の解決", "Claudeハーネス/共通ルール/環境変数の解決.md"),
        ],
    }


def test_list_harness_pages_when_empty(fake_wiki):
    """分類フォルダのページなしは空リスト（正常系）。"""
    # 準備
    fake_wiki.pages[f"{BASE}/Claudeハーネス/README.md"] = README_NO_PAGES
    # 実行
    pages = read_agent_docs.list_harness_pages(BASE)
    # 検証
    assert pages == {"共通対応表": [], "対応表": [], "共通ルール": []}


def test_parse_matrix():
    """○ の抽出と相対リンクの解決（正常系）。"""
    # 実行
    matrix = read_agent_docs.parse_matrix(DOCS_MATRIX, BASE)
    # 検証
    assert matrix == {
        "intake-issue-triager": [
            ("規約/コメント.md", f"{BASE}/規約/コメント.md"),
            ("判定フローチャート/レイヤー.md", f"{BASE}/判定フローチャート/レイヤー.md"),
        ],
        "epic-conductor": [
            ("規約/コメント.md", f"{BASE}/規約/コメント.md"),
            ("規約/マージ手順.md", f"{BASE}/規約/マージ手順.md"),
        ],
    }


def test_parse_matrix_when_absolute_url():
    """絶対 URL リンクの解決（正常系）。"""
    # 実行
    matrix = read_agent_docs.parse_matrix(LANG_MATRIX, BASE)
    # 検証
    assert matrix == {
        "architect": [
            ("python/core/スタイル.md", "https://raw.example.com/rules/python/core/スタイル.md"),
        ],
    }


def test_parse_matrix_when_no_table():
    """表なし（異常系）。"""
    # 実行・検証
    with pytest.raises(ValueError):
        read_agent_docs.parse_matrix("# エージェント参照ドキュメント対応表\n\n表のない本文。\n", BASE)


def test_main_when_same_base(fake_wiki, monkeypatch, capsys):
    """ベースが同一の場合の README 使い回し（正常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setenv("AI_MONITOR_WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["read_agent_docs.py", "intake-issue-triager"])
    _setup_matrices(fake_wiki, BASE)
    _setup_docs(fake_wiki, BASE)
    # 実行
    code = read_agent_docs.main()
    # 検証
    out = capsys.readouterr().out
    assert code == 0
    assert len(_readme_calls(fake_wiki)) == 1
    assert "**環境変数の解決:**" in out
    assert "**規約/コメント.md:**" in out
    assert "**設計図/シナリオ/README.md:**" in out


def test_main_when_separate_bases(fake_wiki, monkeypatch, capsys):
    """ベースが異なる場合の 2 README 列挙（正常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setenv("AI_MONITOR_WIKI_BASE", COMMON_BASE)
    monkeypatch.setattr(sys, "argv", ["read_agent_docs.py", "intake-issue-triager"])
    # 共通側: README + 共通対応表 + 共通ルール + 共通対応表のドキュメント
    fake_wiki.pages[f"{COMMON_BASE}/Claudeハーネス/README.md"] = README
    fake_wiki.pages[f"{COMMON_BASE}/Claudeハーネス/共通対応表/エージェント参照ドキュメント対応表.md"] = MATRIX_COMMON
    fake_wiki.pages[f"{COMMON_BASE}/Claudeハーネス/共通ルール/環境変数の解決.md"] = "# 環境変数の解決\n"
    fake_wiki.pages[f"{COMMON_BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    fake_wiki.pages[f"{COMMON_BASE}/判定フローチャート/レイヤー.md"] = "# レイヤー\n"
    # プロジェクト側: README + 対応表 + 対応表のドキュメント
    fake_wiki.pages[f"{BASE}/Claudeハーネス/README.md"] = README
    fake_wiki.pages[f"{BASE}/Claudeハーネス/対応表/エージェント言語規約対応表.md"] = MATRIX_LANG
    fake_wiki.pages[f"{BASE}/Claudeハーネス/対応表/プロジェクトドキュメント対応表.md"] = MATRIX_PROJECT
    fake_wiki.pages[f"{BASE}/設計図/シナリオ/README.md"] = "# シナリオ\n"
    # 実行
    code = read_agent_docs.main()
    # 検証
    out = capsys.readouterr().out
    assert code == 0
    readme_calls = _readme_calls(fake_wiki)
    assert len(readme_calls) == 2
    assert len([c for c in readme_calls if c.startswith(COMMON_BASE)]) == 1
    assert len([c for c in readme_calls if c.startswith(BASE)]) == 1
    assert "**環境変数の解決:**" in out
    assert "**規約/コメント.md:**" in out
    assert "**設計図/シナリオ/README.md:**" in out


def test_main_when_wiki_base_missing(fake_wiki, monkeypatch, capsys):
    """`WIKI_BASE` 未設定（異常系）。"""
    # 準備
    monkeypatch.delenv("WIKI_BASE", raising=False)
    monkeypatch.setenv("AI_MONITOR_WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["read_agent_docs.py", "intake-issue-triager"])
    # 実行
    code = read_agent_docs.main()
    # 検証
    assert code == 1
    assert "WIKI_BASE" in capsys.readouterr().err
    assert fake_wiki.calls == []


def test_main_when_ai_monitor_wiki_base_missing(fake_wiki, monkeypatch, capsys):
    """`AI_MONITOR_WIKI_BASE` 未設定（異常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.delenv("AI_MONITOR_WIKI_BASE", raising=False)
    monkeypatch.setattr(sys, "argv", ["read_agent_docs.py", "intake-issue-triager"])
    # 実行
    code = read_agent_docs.main()
    # 検証
    assert code == 1
    assert "AI_MONITOR_WIKI_BASE" in capsys.readouterr().err
    assert fake_wiki.calls == []


def test_main_when_unknown_agent(fake_wiki, monkeypatch, capsys):
    """未知のエージェント名（異常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setenv("AI_MONITOR_WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["read_agent_docs.py", "unknown-agent"])
    _setup_matrices(fake_wiki, BASE)
    # 実行
    code = read_agent_docs.main()
    # 検証
    err = capsys.readouterr().err
    assert code == 1
    assert "intake-issue-triager" in err
    assert "architect" in err

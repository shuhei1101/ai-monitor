"""「エージェントドキュメント注入」の結合テスト。"""
from __future__ import annotations

import sys

import read_agent_docs

BASE = "https://raw.example.com/owner/repo/master/docs/wiki"

README = """# Claudeハーネス

## 目次

| ページ | 概要 |
| --- | --- |
| [エージェント参照ドキュメント対応表](./共通対応表/エージェント参照ドキュメント対応表.md) | エージェント × 共通ドキュメントの星取り表 |
| [プロジェクトドキュメント対応表](./対応表/プロジェクトドキュメント対応表.md) | エージェント × プロジェクト固有設計書の星取り表 |
| [環境変数の解決](./共通ルール/環境変数の解決.md) | 環境変数を実値に解決する共通手順 |
| [エージェント一覧](./エージェント一覧.md) | エージェントの一覧 |
"""

COMMON_MATRIX = """# エージェント参照ドキュメント対応表

| ドキュメント | intake-issue-triager | epic-conductor |
| --- | --- | --- |
| [規約/コメント.md](../../規約/コメント.md) | ○ | ○ |
"""

PROJECT_MATRIX = """# プロジェクトドキュメント対応表

| ドキュメント | intake-issue-triager | architect |
| --- | --- | --- |
| [設計図/ER図/ユーザー.md](../../設計図/ER図/ユーザー.md) | ○ | ○ |
"""


def _setup_wiki(fake_wiki):
    fake_wiki.pages[f"{BASE}/Claudeハーネス/README.md"] = README
    fake_wiki.pages[f"{BASE}/Claudeハーネス/共通対応表/エージェント参照ドキュメント対応表.md"] = COMMON_MATRIX
    fake_wiki.pages[f"{BASE}/Claudeハーネス/対応表/プロジェクトドキュメント対応表.md"] = PROJECT_MATRIX


def test_normal(fake_wiki, monkeypatch, capsys):
    """対応表の列挙 → 解析 → 共通ルール・○ ドキュメントの取得・連結出力を確認する（正常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setenv("AI_MONITOR_WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["read_agent_docs.py", "intake-issue-triager"])
    _setup_wiki(fake_wiki)
    fake_wiki.pages[f"{BASE}/Claudeハーネス/共通ルール/環境変数の解決.md"] = "# 環境変数の解決\n"
    fake_wiki.pages[f"{BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    fake_wiki.pages[f"{BASE}/設計図/ER図/ユーザー.md"] = "# ユーザー ER 図\n"
    # 実行
    code = read_agent_docs.main()
    # 検証
    assert code == 0
    assert capsys.readouterr().out == (
        "**環境変数の解決:**\n"
        "`````md\n"
        "# 環境変数の解決\n"
        "`````\n"
        "\n"
        "**規約/コメント.md:**\n"
        "`````md\n"
        "# 規約: コメント\n"
        "`````\n"
        "\n"
        "**設計図/ER図/ユーザー.md:**\n"
        "`````md\n"
        "# ユーザー ER 図\n"
        "`````\n"
        "\n"
    )


def test_error_when_wiki_base_missing(fake_wiki, monkeypatch, capsys):
    """環境変数なしでエラー終了することを確認する（異常系）。"""
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


def test_error_when_unknown_agent(fake_wiki, monkeypatch, capsys):
    """対応表に列が無い名前でエラー終了することを確認する（異常系）。"""
    # 準備
    monkeypatch.setenv("WIKI_BASE", BASE)
    monkeypatch.setenv("AI_MONITOR_WIKI_BASE", BASE)
    monkeypatch.setattr(sys, "argv", ["read_agent_docs.py", "unknown-agent"])
    _setup_wiki(fake_wiki)
    # 実行
    code = read_agent_docs.main()
    # 検証
    err = capsys.readouterr().err
    assert code == 1
    assert "intake-issue-triager" in err
    assert "architect" in err
    # README + 対応表 2 本のみで、共通ルール・ドキュメント本体の取得リクエストが発生していない
    assert len(fake_wiki.calls) == 3


"""`src/ai_monitor/setup_labels/github.py` の単体テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

from ai_monitor.setup_labels.github import create_label, list_labels, update_label
from ai_monitor.setup_labels.sync import LabelSpec

REPO = "shuhei1101/ai-monitor"


def _label_ns(name: str, color: str = "0e8a16", description: str | None = "説明"):
    return NS(name=name, color=color, description=description)


# ---- ラベル一覧取得 ----


def test_list_labels(gh_mon, resp):
    """1 ページ分の LabelSpec 変換を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_labels_for_repo.return_value = resp(
        [_label_ns("bug"), _label_ns("layer:epic"), _label_ns("確認:architect")]
    )
    # 実行
    specs = list_labels(REPO)
    # 検証
    assert [s.name for s in specs] == ["bug", "layer:epic", "確認:architect"]
    assert specs[0] == LabelSpec(name="bug", color="0e8a16", description="説明")
    kwargs = gh_mon.rest.issues.list_labels_for_repo.call_args.kwargs
    assert kwargs["owner"] == "shuhei1101" and kwargs["repo"] == "ai-monitor"


def test_list_labels_when_paginated(gh_mon, resp):
    """複数ページの結合を確認する（正常系）。"""
    # 準備
    first = [_label_ns(f"label-{i}") for i in range(100)]
    second = [_label_ns(f"label-{i}") for i in range(100, 120)]
    gh_mon.rest.issues.list_labels_for_repo.side_effect = [resp(first), resp(second)]
    # 実行
    specs = list_labels(REPO)
    # 検証
    assert len(specs) == 120
    assert gh_mon.rest.issues.list_labels_for_repo.call_count == 2


def test_list_labels_when_description_none(gh_mon, resp):
    """説明が未設定のラベルの空文字化を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_labels_for_repo.return_value = resp([_label_ns("bug", description=None)])
    # 実行
    specs = list_labels(REPO)
    # 検証
    assert specs[0].description == ""


# ---- ラベル作成 ----


def test_create_label(gh_mon, resp):
    """作成 API への引数の受け渡しを確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.create_label.return_value = resp(_label_ns("確認:architect"))
    spec = LabelSpec(name="確認:architect", color="0e8a16", description="担当エージェントの作業待ち")
    # 実行
    create_label(REPO, spec)
    # 検証
    kwargs = gh_mon.rest.issues.create_label.call_args.kwargs
    assert kwargs["owner"] == "shuhei1101" and kwargs["repo"] == "ai-monitor"
    assert kwargs["name"] == "確認:architect"
    assert kwargs["color"] == "0e8a16"
    assert kwargs["description"] == "担当エージェントの作業待ち"


# ---- ラベル更新 ----


def test_update_label(gh_mon, resp):
    """更新 API への引数の受け渡しを確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.update_label.return_value = resp(_label_ns("議論中"))
    spec = LabelSpec(name="議論中", color="d93f0b", description="ユーザーとの議論が開いている")
    # 実行
    update_label(REPO, spec)
    # 検証
    kwargs = gh_mon.rest.issues.update_label.call_args.kwargs
    assert kwargs["name"] == "議論中"
    assert kwargs["color"] == "d93f0b"
    assert kwargs["description"] == "ユーザーとの議論が開いている"
    # 名前の変更は要求しない
    assert "new_name" not in kwargs

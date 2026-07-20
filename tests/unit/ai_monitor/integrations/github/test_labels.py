"""`src/ai_monitor/integrations/github/labels.py` の単体テスト。"""
from __future__ import annotations

import ai_monitor.integrations.github.labels as labels_mod


def test_add_label(gh_mon, mon_project):
    """付与 API の実行を確認する（正常系）。"""
    # 実行
    labels_mod.add_label(mon_project, 52, "処理中:architect")
    # 検証
    kwargs = gh_mon.rest.issues.add_labels.call_args.kwargs
    assert kwargs["owner"] == "shuhei1101"
    assert kwargs["repo"] == "ai-monitor-e2e"
    assert kwargs["issue_number"] == 52
    assert kwargs["labels"] == ["処理中:architect"]


def test_remove_label(gh_mon, mon_project):
    """除去 API の実行を確認する（正常系）。"""
    # 実行
    labels_mod.remove_label(mon_project, 52, "処理中:architect")
    # 検証
    kwargs = gh_mon.rest.issues.remove_label.call_args.kwargs
    assert kwargs["issue_number"] == 52
    assert kwargs["name"] == "処理中:architect"


def test_remove_label_when_not_attached(gh_mon, mon_project, request_failed):
    """未付与の 404 は無視を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.remove_label.side_effect = request_failed(404)
    # 実行・検証
    labels_mod.remove_label(mon_project, 52, "処理中:architect")

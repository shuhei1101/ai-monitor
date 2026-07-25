"""「作業完了報告」の結合テスト。"""
from __future__ import annotations

import pytest

import ai_monitor.mcp.server as server
from ai_monitor.mcp.models import MonitorAck


def test_normal(gh_mon, api, mon_registry, session_factory):
    """プロジェクト解決 → セッション検索 → ラベル除去 → 生存更新の一連を確認する（正常系）。"""
    # 準備
    session_factory("architect", 52)
    before = mon_registry.find("sandbox", "architect", 52).last_seen_at
    # 実行
    res = api.report_completion("architect", 52)
    # 検証
    kwargs = gh_mon.rest.issues.remove_label.call_args.kwargs
    assert (kwargs["owner"], kwargs["repo"], kwargs["issue_number"]) == ("shuhei1101", "ai-monitor-e2e", 52)
    assert kwargs["name"] == "処理中:architect"
    assert mon_registry.find("sandbox", "architect", 52).last_seen_at != before
    assert res == MonitorAck(ok=True)


def test_error_when_unknown_session(gh_mon, api):
    """台帳に該当セッションがない場合のエラーを確認する（異常系・セッション不明）。"""
    # 実行・検証
    with pytest.raises(server.SessionNotFoundError):
        api.report_completion("architect", 52)
    gh_mon.rest.issues.remove_label.assert_not_called()


def test_error_when_unknown_project(gh_mon, mon_settings, mon_registry, mcp_agents, mcp_ctx_factory):
    """ヘッダのプロジェクト名が設定に無い場合のエラーを確認する（異常系・プロジェクト不明）。"""
    # 準備
    report_completion = server._bind(
        server.report_completion,
        ctx=mcp_ctx_factory("unknown"),
        settings=mon_settings,
        registry=mon_registry,
        agents=mcp_agents,
    )
    # 実行・検証
    with pytest.raises(server.ProjectNotFoundError):
        report_completion("architect", 52)
    gh_mon.rest.issues.remove_label.assert_not_called()

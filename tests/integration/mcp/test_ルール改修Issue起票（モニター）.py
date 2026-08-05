"""「ルール改修Issue起票（モニター）」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import CreatedIssueResult

ARGS = dict(
    title="PR 本文テンプレート（エピック）に変更種別の記入例が無い",
    body="テンプレートに記入例が無く、列の要否を読み取れなかった。",
    rule_page="docs/wiki/テンプレート/PR本文/エピック.md",
    rule_excerpt="（`## ユースケース一覧` の記述例に変更種別の列が無い）",
    agent_name="epic-conductor",
    number=90,
)


def test_normal(gh, resp, api):
    """定型本文の組み立て → assignee 付き起票 → 番号と URL の返却の一連を確認する（正常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.create.return_value = resp(NS(number=214, html_url="http://i/214"))
    # 実行
    res = api.create_monitor_rule_issue(**ARGS)
    # 検証: 起票先が呼び出し元セッションのプロジェクト（sandbox）ではなく ai-monitor
    kwargs = gh.rest.issues.create.call_args.kwargs
    assert (kwargs["owner"], kwargs["repo"]) == ("shuhei1101", "ai-monitor")
    # 本文に報告元・対象ルール・指摘の内容が入る
    body = kwargs["body"]
    assert "| プロジェクト | sandbox |" in body
    assert "| エージェント | epic-conductor |" in body
    assert "| 対象 | shuhei1101/ai-monitor-e2e#90 |" in body
    assert "`docs/wiki/テンプレート/PR本文/エピック.md`" in body
    assert "> （`## ユースケース一覧` の記述例に変更種別の列が無い）" in body
    assert "## 指摘の内容" in body
    # 承認する相手が常にユーザーなので assignee は認証ユーザー 1 名で固定
    assert kwargs["assignees"] == ["shuhei1101"]
    # AI の報告であることを示すラベルだけ（確認ラベルはユーザーが付けるまで付けない）
    assert kwargs["labels"] == ["AI不具合報告"]
    assert res == CreatedIssueResult(issue_number=214, url="http://i/214", parent_issue_number=None)


def test_error_when_repo_unset(gh, api, mon_settings):
    """起票先が未設定のときのエラーを確認する（異常系）。"""
    # 準備
    mon_settings.ai_monitor_repo = None
    # 実行・検証
    with pytest.raises(ValueError, match="ai_monitor_repo"):
        api.create_monitor_rule_issue(**ARGS)
    gh.rest.issues.create.assert_not_called()


def test_error_when_api_error(gh, resp, api, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.create.side_effect = request_failed(500)
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.create_monitor_rule_issue(**ARGS)

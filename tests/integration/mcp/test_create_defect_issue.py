"""「不具合Issue起票」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import CreatedIssueResult


def test_normal(gh, resp, api, mon_settings, monkeypatch):
    """定型本文の組み立て → assignee 付き起票 → 通知 → 番号と URL の返却の一連を確認する（正常系）。"""
    # 準備
    import ai_monitor.features.notify.service as notify_service
    from ai_monitor.shared.settings import WebhookNotifySettings

    sent: list[str] = []
    monkeypatch.setattr(notify_service, "post_webhook", lambda url, kind, text: sent.append(text) or "")
    mon_settings.notifies = [WebhookNotifySettings(webhook_url="https://example.com/hook", kind="discord")]
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.create.return_value = resp(NS(number=214, html_url="http://i/214"))
    # 実行
    res = api.create_defect_issue(
        title="subsystemマージ の作業完了報告が失敗する",
        body="監視面除去を先に実行すると台帳を解決できない。",
        agent_name="subsystem-conductor",
        number=1179,
        source_pages=[
            "Claudeハーネス/共通ルール/最終マージの判定.md",
            "エージェント/subsystem-conductor/フェーズ/subsystemマージ.md",
        ],
        workaround="主番号で作業完了報告を出した。",
    )
    # 検証: 起票先が呼び出し元セッションのプロジェクト（sandbox）ではなく ai-monitor
    kwargs = gh.rest.issues.create.call_args.kwargs
    assert (kwargs["owner"], kwargs["repo"]) == ("shuhei1101", "ai-monitor")
    # 本文に報告元・該当ページ・事象・回避策が入る
    body = kwargs["body"]
    assert "| プロジェクト | sandbox |" in body
    assert "| エージェント | subsystem-conductor |" in body
    assert "#1179" in body
    assert "- `Claudeハーネス/共通ルール/最終マージの判定.md`" in body
    assert "- `エージェント/subsystem-conductor/フェーズ/subsystemマージ.md`" in body
    assert "監視面除去を先に実行すると台帳を解決できない。" in body
    assert "主番号で作業完了報告を出した。" in body
    # 承認する相手が常にユーザーなので assignee は認証ユーザー 1 名
    assert kwargs["assignees"] == ["shuhei1101"]
    # AI の報告であることを示すラベルだけを付ける（確認ラベルはユーザーが付けるまで付けない）
    assert kwargs["labels"] == ["AI不具合報告"]
    # 承認するまで Issue が動かないので、起票のたびに通知して溜めない
    assert sent, "契機通知が送られていない"
    assert "214" in sent[0]
    assert res == CreatedIssueResult(issue_number=214, url="http://i/214", parent_issue_number=None)


def test_normal_when_no_workaround(gh, resp, api):
    """回避策なしのときの本文を確認する（正常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.create.return_value = resp(NS(number=215, html_url="http://i/215"))
    # 実行
    api.create_defect_issue(
        title="手順に分岐がない",
        body="事象の説明。",
        agent_name="architect",
        number=52,
        source_pages=["規約/マージ手順.md"],
    )
    # 検証: 回避できず作業を中断したことが読み取れる
    body = gh.rest.issues.create.call_args.kwargs["body"]
    section = body.split("## 回避策", 1)[1]
    assert "なし" in section
    assert "中断" in section
    # 他のセクションは正常系と同じ形で入る
    assert "## 報告元" in body
    assert "## 該当ページ" in body
    assert "## 事象" in body


def test_normal_when_no_source_pages(gh, resp, api):
    """該当ページが不明なときの本文を確認する（正常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.create.return_value = resp(NS(number=216, html_url="http://i/216"))
    # 実行
    api.create_defect_issue(
        title="どの手順が原因か特定できない",
        body="事象の説明。",
        agent_name="architect",
        number=52,
        workaround="手順を補って続行した。",
    )
    # 検証: 該当ページのセクションだけが落ちる
    body = gh.rest.issues.create.call_args.kwargs["body"]
    assert "## 該当ページ" not in body
    assert "## 報告元" in body
    assert "## 事象" in body
    assert "## 回避策" in body


def test_error_when_repo_unset(gh, api, mon_settings):
    """起票先が未設定のときのエラーを確認する（異常系）。"""
    # 準備
    mon_settings.ai_monitor_repo = None
    # 実行・検証
    with pytest.raises(ValueError) as exc_info:
        api.create_defect_issue(title="件名", body="本文", agent_name="architect", number=52)
    # 設定キー名が分かるメッセージで、作成 API は呼ばない
    assert "ai_monitor_repo" in str(exc_info.value)
    gh.rest.issues.create.assert_not_called()


def test_error_when_api_error(gh, resp, request_failed, api):
    """作成失敗がツールエラーとして伝播することを確認する（異常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.create.side_effect = request_failed(422)
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.create_defect_issue(title="件名", body="本文", agent_name="architect", number=52)

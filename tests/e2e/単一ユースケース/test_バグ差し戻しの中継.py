"""「バグ差し戻しの中継」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, comments_from, issue, label_names
from tests.e2e.実装対象 import EPIC_BODY, EPIC_TITLE, INTAKE_BODY, INTAKE_TITLE, STORY_BODY_TEMPLATE, STORY_TITLE
from tests.e2e.統合テスト import add_merged_subsystem

BUG_HANDOVER = """> from: @epic-conductor
> to: @story-conductor

複合ユースケース E2E で fail が出ました。実装側の問題と判断しています。

| 失敗ケース | 内容 |
| --- | --- |
| `test_error_when_タイトルが空` | タイトルを空にしても `ValidationError` にならず保存される |

修正方針: `update_task` のタイトル検証を「1 文字以上 100 文字以内」に戻す。
該当する subsystem へ差し戻してください。

------
"""

FIX_DONE_REPORT = """> from: @subsystem-conductor
> to: @story-conductor

差し戻されたバグの修正が完了しました。

| 対象 | 内容 |
| --- | --- |
| `src/tasks/service.py` | タイトル検証を 1 文字以上 100 文字以内に修正 |

修正用 PR は epic ブランチへ merge 済みで、subsystem Issue は close しました。

------
"""


def _setup_tree(gh_live, owner, repo, epic_issue_factory, story_issue_factory, subsystem_issue_factory):
    """epic → story（reopen 済み想定）→ subsystem（closed）の Issue ツリーを用意する。"""
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number), labels=["layer:story", "type:feat"],
    )
    subsystem = add_merged_subsystem(gh_live, owner, repo, subsystem_issue_factory, story.number)
    return intake, epic, story, subsystem


def test_normal_when_handover(
    monitor, gh_live, repo_ctx, epic_issue_factory, story_issue_factory, subsystem_issue_factory, wait_until,
):
    """epic からのバグ差し戻しを該当 subsystem へ中継することを確認する（正常系・差し戻しの中継）。"""
    owner, repo = repo_ctx
    intake, epic, story, subsystem = _setup_tree(
        gh_live, owner, repo, epic_issue_factory, story_issue_factory, subsystem_issue_factory
    )
    # 準備: epic-conductor のバグ差し戻しコメント → 確認ラベル付与（起動トリガー）
    handover = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story.number, body=BUG_HANDOVER
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=story.number, labels=["確認:story-conductor"]
    )

    # 実行: 中継の完了を待つ（subsystem reopen + 確認:subsystem-conductor + バグ内容コメント）
    def _relayed():
        sub_now = issue(gh_live, owner, repo, subsystem.number)
        if sub_now.state != "open" or "確認:subsystem-conductor" not in label_names(sub_now):
            return None
        relayed = comments_from(gh_live, owner, repo, subsystem.number, "story-conductor")
        if not relayed:
            return None
        story_now = issue(gh_live, owner, repo, story.number)
        return (story_now, relayed[-1]) if "確認:story-conductor" not in label_names(story_now) else None

    story_now, relayed = wait_until(
        _relayed, timeout_sec=1800, message="バグ差し戻しの中継（subsystem reopen + 確認ラベル付与）"
    )

    # 検証: バグ内容コメントが @subsystem-conductor 宛で未解決のまま残っている
    assert "> to: @subsystem-conductor" in (relayed.body or ""), "バグ内容コメントの宛先が違う"
    assert not server._is_minimized(relayed.node_id), (
        "バグ内容コメントが Resolve されている（受領は subsystem-conductor）"
    )

    # 検証: 差し戻しコメントのスレッドに中継結果が返信追記され、Resolve 済み
    thread = next(c for c in comments(gh_live, owner, repo, story.number) if c.node_id == handover.node_id)
    assert f"#{subsystem.number}" in (thread.body or ""), "中継結果に対象 subsystem 番号がない"
    assert server._is_minimized(handover.node_id), "差し戻しコメントが未 Resolve"

    # 検証: story Issue は open のまま 確認:story-conductor が除去されている
    assert story_now.state == "open", "story Issue が close されている"
    assert "議論中" not in label_names(story_now), "議論中 が付与されている（自動完了のはず）"


def test_normal_when_completion(
    monitor, gh_live, repo_ctx, epic_issue_factory, story_issue_factory, subsystem_issue_factory, wait_until,
):
    """subsystem の修正完了を親 epic へ中継し story を再クローズすることを確認する（正常系・修正完了の中継）。"""
    owner, repo = repo_ctx
    intake, epic, story, subsystem = _setup_tree(
        gh_live, owner, repo, epic_issue_factory, story_issue_factory, subsystem_issue_factory
    )
    # 準備: subsystem-conductor の修正完了報告 → 確認ラベル付与（起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story.number, body=FIX_DONE_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=story.number, labels=["確認:story-conductor"]
    )

    # 実行: 中継の完了を待つ（story close + 親 epic に 確認:epic-conductor + 完了報告）
    def _relayed():
        story_now = issue(gh_live, owner, repo, story.number)
        if story_now.state != "closed" or "確認:story-conductor" in label_names(story_now):
            return None
        epic_now = issue(gh_live, owner, repo, epic.number)
        if "確認:epic-conductor" not in label_names(epic_now):
            return None
        relayed = comments_from(gh_live, owner, repo, epic.number, "story-conductor")
        return (story_now, relayed[-1]) if relayed else None

    story_now, relayed = wait_until(
        _relayed, timeout_sec=1800, message="修正完了の中継（story close + 親 epic への完了報告）"
    )

    # 検証: 完了報告が @epic-conductor 宛で未解決のまま残っている
    assert "> to: @epic-conductor" in (relayed.body or ""), "完了報告の宛先が epic-conductor でない"
    assert not server._is_minimized(relayed.node_id), "完了報告が Resolve されている（受領は epic-conductor）"

    # 検証: subsystem-conductor の完了報告が Resolve 済み
    assert server._is_minimized(report.node_id), "subsystem-conductor の完了報告が未 Resolve"
    assert story_now.state == "closed", "story Issue が再クローズされていない"

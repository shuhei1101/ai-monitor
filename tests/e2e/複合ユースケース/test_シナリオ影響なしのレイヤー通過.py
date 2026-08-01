"""「シナリオ影響なしのレイヤー通過」の E2E テスト。

シナリオに影響しない修正でも epic → story → subsystem を必ず通し、
影響なしと判定したレイヤーがシナリオ設計を挟まずに下位を起票することを見る。
"""
from __future__ import annotations

from tests.e2e.epic起動 import drive_requirements
from tests.e2e.ゲート応答 import open_prs_for
from tests.e2e.エスカレーション import (
    approve,
    issue,
    label_names,
    tree_paths,
    waiting_for_user,
)

INTAKE_TITLE = "ポーリング処理の関数分割"
INTAKE_BODY = """`run_cycle` が長くなってきたので、内部を関数に分割して読みやすくしてください。

- 外から見た振る舞いは一切変えない（入力も出力も同じ）
- 画面・API・保存データのどれも変更しない
- 既存のテストがそのまま通ることを条件にする
"""

COMPLEX_DIR = "docs/wiki/設計図/シナリオ/複合ユースケース/"
SINGLE_DIR = "docs/wiki/設計図/シナリオ/単一ユースケース/"

# epic 要件確定を「複合 UC 影響なし」へ決定的に誘導する回答
EPIC_ANSWER = "A（PoC 不要）/ A（画面変更なし）/ A（複合ユースケースへの影響なし）でお願いします。"
# story 要件確定を「単一 UC 影響なし」へ誘導する回答
STORY_ANSWER_NO_IMPACT = "1 UC のままで、単一ユースケースへの影響はありません（A）。実装だけの変更です。"
# story 要件確定を「単一 UC 影響あり」へ誘導する回答（異常シナリオ）
STORY_ANSWER_IMPACT = "分割にあわせて再試行の挙動が変わるので、単一ユースケースの更新が必要です（B）。"


def _drive_intake_to_epic(gh_live, owner, repo, wait_until, intake_issue_factory):
    """intake の分解判定を承認まで進め、起票された epic Issue を返す。"""
    intake = intake_issue_factory(title=INTAKE_TITLE, body=INTAKE_BODY)

    def _triage_done():
        data = issue(gh_live, owner, repo, intake.number)
        return data if waiting_for_user(data) else None

    triaged = wait_until(_triage_done, timeout_sec=1800, message="分解判定（初回）の完了（議論中 + assignee）")
    approve(gh_live, owner, repo, intake.number, triaged.assignees)

    def _subissues_created():
        data = issue(gh_live, owner, repo, intake.number)
        if any(name.startswith("確認:") for name in label_names(data)):
            return None
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=intake.number
        ).parsed_data
        return subs or None

    subs = wait_until(_subissues_created, timeout_sec=1800, message="サブIssue起票（完了処理）の完了")
    assert len(subs) == 1, f"epic 1 件に分解されていない: {[s.title for s in subs]}"
    return intake, subs[0]


def _drive_story_requirements(gh_live, owner, repo, wait_until, story_number: int, *, answer_body: str):
    """story 要件確定を 初回待機 → 回答 → 応答ループ → 承認 まで進める。"""

    def _first_turn_done():
        data = issue(gh_live, owner, repo, story_number)
        return data if waiting_for_user(data) else None

    first = wait_until(
        _first_turn_done, timeout_sec=1800, message="story 要件確定（初回）の完了（議論中 + assignee）"
    )
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story_number, body=answer_body
    )
    for assignee in first.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=story_number, assignees=[assignee.login]
        )

    def _replied():
        data = issue(gh_live, owner, repo, story_number)
        return data if data.assignees else None

    replied = wait_until(_replied, timeout_sec=1800, message="story 応答ループの完了（assignee 再設定）")
    approve(gh_live, owner, repo, story_number, replied.assignees)
    return first


def test_normal(monitor, gh_live, repo_ctx, intake_issue_factory, wait_until):
    """影響なしの判定で最短経路を通り subsystem へ届くことを実環境で確認する（正常シナリオ）。"""
    owner, repo = repo_ctx
    complex_before = set(tree_paths(gh_live, owner, repo, "master", COMPLEX_DIR))
    single_before = set(tree_paths(gh_live, owner, repo, "master", SINGLE_DIR))

    # 準備・実行: intake の分解 → epic 起票
    intake, epic = _drive_intake_to_epic(gh_live, owner, repo, wait_until, intake_issue_factory)

    # 実行: epic 要件確定（複合 UC 影響なしと回答）
    drive_requirements(gh_live, owner, repo, wait_until, epic.number, answer_body=EPIC_ANSWER)

    # 検証: epic 本文に複合 UC 影響なしの判定が記録されている
    epic_data = issue(gh_live, owner, repo, epic.number)
    epic_body = (epic_data.body or "").replace("\r\n", "\n")
    assert "複合ユースケースへの影響: なし" in epic_body, f"影響なしの判定が記録されていない: {epic_body[-400:]}"

    # 検証: 複合シナリオ設計・モック設計へ渡っていない
    epic_prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(epic_prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in epic_prs]}"
    epic_pr_labels = {label.name for label in epic_prs[0].labels}
    assert "確認:complex-scenario-writer" not in epic_pr_labels, "複合シナリオ設計へ渡っている"
    assert "確認:mock-designer" not in epic_pr_labels, "モック設計へ渡っている"

    # 実行: 子 story の起票を待つ
    def _story_created():
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=epic.number
        ).parsed_data
        return subs or None

    stories = wait_until(_story_created, timeout_sec=1800, message="子story起票（確認:story-conductor 付与）")
    assert len(stories) == 1, f"story 1 件でない: {[s.title for s in stories]}"
    story = stories[0]

    # 実行: story 要件確定（単一 UC 影響なしと回答）
    _drive_story_requirements(
        gh_live, owner, repo, wait_until, story.number, answer_body=STORY_ANSWER_NO_IMPACT
    )

    # 検証: story 本文に単一 UC 影響なしの判定が記録されている
    story_body = (issue(gh_live, owner, repo, story.number).body or "").replace("\r\n", "\n")
    assert "単一ユースケースへの影響: なし" in story_body, f"影響なしの判定が記録されていない: {story_body[-400:]}"

    # 検証: 単一シナリオ設計へ渡っていない
    story_prs = open_prs_for(gh_live, owner, repo, story.number)
    assert len(story_prs) == 1, f"story Draft PR が 1 件でない: {[pr.number for pr in story_prs]}"
    assert "確認:single-scenario-writer" not in {label.name for label in story_prs[0].labels}, (
        "単一シナリオ設計へ渡っている"
    )

    # 実行: 子 subsystem の起票と SS 設計への引き継ぎを待つ
    def _subsystem_handed_off():
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=story.number
        ).parsed_data
        if not subs:
            return None
        prs = open_prs_for(gh_live, owner, repo, subs[0].number)
        if not prs:
            return None
        return (subs[0], prs[0]) if "確認:architect" in {label.name for label in prs[0].labels} else None

    subsystem, subsystem_pr = wait_until(
        _subsystem_handed_off, timeout_sec=2400, message="子subsystem起票と SS設計への引き継ぎ（確認:architect）"
    )

    # 検証: intake の下に epic / story / subsystem が親子で連なっている
    assert epic.number in {s.number for s in gh_live.rest.issues.list_sub_issues(
        owner=owner, repo=repo, issue_number=intake.number
    ).parsed_data}
    assert subsystem_pr.draft is True

    # 検証: シナリオへの commit が発生していない
    for branch, label in ((epic_prs[0].head.ref, "epic"), (story_prs[0].head.ref, "story")):
        assert set(tree_paths(gh_live, owner, repo, branch, COMPLEX_DIR)) == complex_before, (
            f"{label} ブランチで複合シナリオに commit が発生している"
        )
        assert set(tree_paths(gh_live, owner, repo, branch, SINGLE_DIR)) == single_before, (
            f"{label} ブランチで単一シナリオに commit が発生している"
        )

    # 検証: 各レイヤーの Issue が open のまま 確認:* を残していない
    for number in (epic.number, story.number, subsystem.number):
        data = issue(gh_live, owner, repo, number)
        assert data.state == "open", f"#{number} が closed になっている"
    assert not [n for n in label_names(issue(gh_live, owner, repo, epic.number)) if n.startswith("確認:")]
    assert not [n for n in label_names(issue(gh_live, owner, repo, story.number)) if n.startswith("確認:")]


def test_error_when_impact_found_below(monitor, gh_live, repo_ctx, intake_issue_factory, wait_until):
    """上位が影響なしと判定した後に下位が影響を検知する経路を確認する（異常シナリオ）。"""
    owner, repo = repo_ctx
    complex_before = set(tree_paths(gh_live, owner, repo, "master", COMPLEX_DIR))

    # 準備・実行: intake の分解 → epic 起票 → epic 要件確定（複合 UC 影響なし）
    _intake, epic = _drive_intake_to_epic(gh_live, owner, repo, wait_until, intake_issue_factory)
    drive_requirements(gh_live, owner, repo, wait_until, epic.number, answer_body=EPIC_ANSWER)

    def _story_created():
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=epic.number
        ).parsed_data
        return subs or None

    stories = wait_until(_story_created, timeout_sec=1800, message="子story起票")
    story = stories[0]

    # 実行: story 要件確定で単一 UC の更新が必要と回答する
    _drive_story_requirements(
        gh_live, owner, repo, wait_until, story.number, answer_body=STORY_ANSWER_IMPACT
    )

    # 実行: 単一シナリオ設計への引き継ぎを待つ
    def _handed_to_writer():
        prs = open_prs_for(gh_live, owner, repo, story.number)
        if not prs:
            return None
        return prs[0] if "確認:single-scenario-writer" in {label.name for label in prs[0].labels} else None

    story_pr = wait_until(
        _handed_to_writer, timeout_sec=1800, message="単一シナリオ設計への引き継ぎ（確認:single-scenario-writer）"
    )

    # 検証: story 本文に単一 UC の更新が必要と記録されている
    story_body = (issue(gh_live, owner, repo, story.number).body or "").replace("\r\n", "\n")
    assert "単一ユースケースへの影響: あり" in story_body, f"影響ありの判定が記録されていない: {story_body[-400:]}"

    # 検証: 上位の epic へ差し戻していない（epic に 確認:* が戻っていない）
    epic_labels = label_names(issue(gh_live, owner, repo, epic.number))
    assert not [n for n in epic_labels if n.startswith("確認:")], (
        f"epic へ差し戻されている: {sorted(epic_labels)}"
    )

    # 検証: 複合シナリオに commit が発生していない
    assert set(tree_paths(gh_live, owner, repo, story_pr.head.ref, COMPLEX_DIR)) == complex_before, (
        "複合シナリオに commit が発生している"
    )

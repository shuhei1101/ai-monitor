"""「PoC判定からepic起動まで」の E2E テスト。"""
from __future__ import annotations

from pathlib import Path

from githubkit.exception import RequestFailed

from tests.e2e.epic起動 import (
    assert_comments_resolved,
    assert_task_list_body,
    drive_poc_verification,
    drive_requirements,
)
from tests.e2e.ゲート応答 import open_prs_for
from tests.e2e.システム import session_entry
from tests.e2e.エスカレーション import comments_from, issue, label_names

INTAKE_TITLE = "一時ファイル生成機構の導入"
INTAKE_BODY = """一時ファイルを介したデータ受け渡しの仕組みを入れたいです。

成立するかどうかは実際に動かしてみないと分からないので、先に確かめてから進めたいです。
"""
EPIC_TITLE = "一時ファイル生成機構"

# 要件確定の分岐を PoC 必要・画面変更なしへ決定的に誘導する回答
REQUIREMENTS_ANSWER = (
    "B（PoC 必要: Python 標準ライブラリのみで一時ファイルの生成・書き込み・読み戻しが"
    "成立するかを検証してください）/ A（画面変更なし）でお願いします。"
)


def test_normal(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path, sandbox):
    """PoC 必要判定 → 発注 → 検証 → 結果確認 → epic Draft PR までの連鎖を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: epic 要件確定をユーザー役として進める（PoC 必要・画面変更なしと回答）
    drive_requirements(gh_live, owner, repo, wait_until, epic.number, answer_body=REQUIREMENTS_ANSWER)

    # 検証: PoC Draft PR のみが作成され 確認:epic-poc-runner + @epic-poc-runner 宛の指示コメントが付いている
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"PoC Draft PR のみの 1 件でない: {[(pr.number, pr.title) for pr in prs]}"
    poc_pr = prs[0]
    poc_branch = poc_pr.head.ref
    assert poc_pr.title.startswith("PoC:"), f"タイトルが PoC: 始まりでない: {poc_pr.title}"
    assert poc_pr.draft is True, "PoC PR が Draft でない"
    assert "確認:epic-poc-runner" in {label.name for label in poc_pr.labels}, (
        f"PoC PR に 確認:epic-poc-runner がない: {sorted(label.name for label in poc_pr.labels)}"
    )
    instructions = comments_from(gh_live, owner, repo, poc_pr.number, "epic-conductor")
    assert instructions, "@epic-poc-runner 宛の指示コメントが投稿されていない"
    assert "> to: @epic-poc-runner" in (instructions[-1].body or ""), "指示コメントの宛先が違う"

    # 検証: 発注時点の epic-conductor セッションを台帳から押さえる（後段でセッションの同一性を見る）
    ordered = session_entry(e2e_state_path, "epic-conductor", epic.number)
    assert ordered, "epic-conductor のセッションが台帳に無い"
    assert poc_pr.number in ordered["watch_numbers"], "PoC PR が監視面に登録されていない"

    # 実行: 実現可能性 PoC 検証をユーザー役として進める（方針固め → 承認 → 検証実行 → 承認）
    drive_poc_verification(gh_live, owner, repo, wait_until, poc_pr.number)

    # 検証: epic Issue 本文に PoC 結果（PoC PR リンク込み）が記録され 確認:epic-conductor へ戻っている
    epic_now = issue(gh_live, owner, repo, epic.number)
    epic_body = (epic_now.body or "").replace("\r\n", "\n")
    assert "## PoC 結果" in epic_body, "epic 本文に ## PoC 結果 がない"
    poc_section = epic_body.split("## PoC 結果", 1)[1]
    assert f"#{poc_pr.number}" in poc_section, "PoC 結果 に PoC PR リンクが記載されていない"
    assert "確認:epic-conductor" in label_names(epic_now), "epic Issue に 確認:epic-conductor が戻っていない"

    # 実行: PoC 結果確認（PoC PR の close と epic Draft PR の作成）を待つ
    def _epic_pr_created():
        if "確認:epic-conductor" in label_names(issue(gh_live, owner, repo, epic.number)):
            return None
        poc_now = gh_live.rest.pulls.get(
            owner=owner, repo=repo, pull_number=poc_pr.number
        ).parsed_data
        if poc_now.state != "closed":
            return None
        others = [pr for pr in open_prs_for(gh_live, owner, repo, epic.number) if pr.number != poc_pr.number]
        if not others:
            return None
        pr = others[0]
        labels = {label.name for label in pr.labels}
        return (pr, poc_now) if "確認:complex-scenario-writer" in labels else None

    epic_pr, poc_now = wait_until(
        _epic_pr_created, timeout_sec=2400, message="PoC PR の close と epic Draft PR の作成"
    )

    # 実行: PoC ブランチの削除を待つ（close 直後はまだ残っていることがある）
    def _branch_deleted():
        try:
            gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=poc_branch)
            return None
        except RequestFailed:
            return True

    wait_until(_branch_deleted, timeout_sec=1800, message="PoC ブランチの削除")

    # 検証: PoC PR は未マージで close され、恒久記録として残っている
    assert poc_now.merged is False, "PoC PR がマージされている（恒久記録として close するだけ）"

    # 検証: PoC の worktree がモニターローカルから削除済み
    worktree_path = Path(sandbox["local_path"]) / ".claude" / "worktrees" / poc_branch.replace("/", "-")
    assert not worktree_path.exists(), f"PoC の worktree が残っている: {worktree_path}"

    # 検証: PoC PR が増えず、epic に紐づく open PR が epic Draft PR の 1 件だけになっている
    remaining = open_prs_for(gh_live, owner, repo, epic.number)
    assert [pr.number for pr in remaining] == [epic_pr.number], (
        f"epic に紐づく open PR が epic Draft PR だけでない: {[pr.number for pr in remaining]}"
    )

    # 検証: epic Draft PR（base=master・本文は 紐づく Issue のみ）が作成されている
    assert epic_pr.draft is True, "epic PR が Draft でない"
    assert epic_pr.base.ref == "master", f"epic PR の base が master でない: {epic_pr.base.ref}"
    assert_task_list_body(epic_pr)

    # 検証: 監視面が epic Draft PR へ入れ替わり、発注時と同一セッションが結果確認まで担っている
    confirmed = session_entry(e2e_state_path, "epic-conductor", epic.number)
    assert confirmed, "epic-conductor のセッションが台帳から消えている"
    assert epic_pr.number in confirmed["watch_numbers"], "epic Draft PR が監視面に登録されていない"
    assert poc_pr.number not in confirmed["watch_numbers"], "close した PoC PR が監視面に残っている"
    assert confirmed["session_name"] == ordered["session_name"], (
        f"epic-conductor のセッションが作り直されている: "
        f"{ordered['session_name']} → {confirmed['session_name']}"
    )

    # 検証: epic Issue の確認ラベルが除去され、自分宛コメントが全て Resolve 済み
    epic_now = issue(gh_live, owner, repo, epic.number)
    assert not [name for name in label_names(epic_now) if name.startswith("確認:")], (
        "epic Issue に確認ラベルが残っている"
    )
    assert_comments_resolved(gh_live, owner, repo, epic.number)

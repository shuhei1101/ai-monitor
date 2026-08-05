"""「PoC結果確認」の E2E テスト。"""
from __future__ import annotations

from pathlib import Path

import yaml
from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, comments_from, issue, label_names, waiting_for_user

INTAKE_TITLE = "一時ファイル生成機構"
INTAKE_BODY = "epic の成立に必要な一時ファイル生成機構を検証する。"

EPIC_TITLE = "一時ファイル生成機構"
_EPIC_BASE = """## 前提条件

なし

## 概要

Python 標準ライブラリで一時ファイルを生成・書き込み・読み戻しできることを確認する。

## 背景

外部依存を最小化するため、標準ライブラリのみで一時ファイルを扱う技術基盤の成立を検証する。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| 一時ファイル生成 | pathlib で一時ファイルを生成する | 未作成 |

## 横断要件

- 標準ライブラリのみで実装できること
{ui_requirement}
## PoC 結果

| 検証項目 | 成功条件 | 実測値 | 判定 |
| --- | --- | --- | --- |
| 書き込み | `Path.write_text()` で書き込める | 成功 | ✅ |
| 読み戻し | `Path.read_text()` で復元できる | 書き込んだ文字列と一致 | ✅ |
| 外部依存 | 追加パッケージ不要 | 標準ライブラリのみ | ✅ |

結論: 成立（epic を進めてよい）
"""

# 要件確定で「画面変更なし」と回答した場合の本文
EPIC_BODY_NO_UI = _EPIC_BASE.format(ui_requirement="- 画面の新規作成・レイアウト変更はなし\n")
# 要件確定で「画面変更あり」と回答した場合の本文
EPIC_BODY_WITH_UI = _EPIC_BASE.format(
    ui_requirement="- 一時ファイルの一覧を確認する画面を新規作成する\n"
)

POC_PR_BODY = """## 紐づく Issue

- #{epic_number}
"""

RUNNER_REPORT = """> from: @epic-poc-runner
> to: @epic-conductor

実現可能性 PoC の検証が完了しました。

| 検証項目 | 実測値 | 判定 |
| --- | --- | --- |
| 書き込み | 成功 | ✅ |
| 読み戻し | 書き込んだ文字列と一致 | ✅ |
| 外部依存 | 標準ライブラリのみ | ✅ |

結論: 成立（epic を進めてよい）。結果は epic Issue 本文の `## PoC 結果` に記録済みです。

------
"""

# 本文の実測値と矛盾する結論（疑問ありを誘発する）
INCONSISTENT_REPORT = """> from: @epic-poc-runner
> to: @epic-conductor

実現可能性 PoC の検証が完了しました。

| 検証項目 | 成功条件 | 実測値 | 判定 |
| --- | --- | --- | --- |
| 書き込み | 1 秒以内に 10000 件を書き込める | 42 秒 | ✅ |

結論: 成立（epic を進めてよい）。

------
"""

CONTINUE_ANSWER = (
    "実測値と判定の食い違いは記載ミスでした。書き込み性能は epic の成立条件ではないので、"
    "このまま次フェーズへ進めてください。"
)

REVERIFY_ANSWER = (
    "実測値が成功条件を満たしていないので、条件を見直したうえで再検証してください。"
    "同じ PoC PR で続けてください。"
)


def _watch_numbers(state_path: Path, epic_number: int) -> list[int]:
    """モニター台帳から epic-conductor セッションの監視面番号一覧を返す。"""
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        if entry["agent_name"] == "epic-conductor" and entry["primary_number"] == epic_number:
            return entry["watch_numbers"]
    return []


def _setup(gh_live, owner, repo, epic_issue_factory, epic_pr_factory, *, epic_body, report_body):
    """PoC 完了時点（PoC PR は open）の epic 一式を用意する。"""
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=epic_body, epic_labels=["layer:epic", "type:feat"]
    )
    poc_branch = f"poc/epic/tempfile-{epic.number}"
    poc_pr = epic_pr_factory(
        branch=poc_branch, title=f"PoC: 一時ファイル生成機構（#{epic.number}）",
        body=POC_PR_BODY.format(epic_number=epic.number),
    )
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic.number, body=report_body
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=epic.number, labels=["確認:epic-conductor"]
    )
    return {"intake": intake, "epic": epic, "poc_pr": poc_pr, "poc_branch": poc_branch, "report": report}


def _epic_prs(gh_live, owner, repo, epic_number: int, poc_number: int) -> list:
    """PoC PR 以外で epic に紐づく open PR を返す。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    return [
        pr for pr in pulls
        if pr.number != poc_number and f"#{epic_number}" in (pr.body or "")
    ]


def _wait_epic_pr(gh_live, owner, repo, ctx, next_label: str, wait_until, *, message):
    """PoC PR の close と epic Draft PR の作成を待つ。"""

    def _done():
        epic_now = issue(gh_live, owner, repo, ctx["epic"].number)
        if "確認:epic-conductor" in label_names(epic_now):
            return None
        poc_now = gh_live.rest.pulls.get(
            owner=owner, repo=repo, pull_number=ctx["poc_pr"].number
        ).parsed_data
        if poc_now.state != "closed":
            return None
        prs = _epic_prs(gh_live, owner, repo, ctx["epic"].number, ctx["poc_pr"].number)
        if not prs:
            return None
        pr = prs[0]
        labels = {label.name for label in pr.labels}
        return (pr, poc_now) if next_label in labels else None

    return wait_until(_done, timeout_sec=2400, message=message)


def _wait_poc_branch_deleted(gh_live, owner, repo, ctx, wait_until) -> None:
    """PoC ブランチの削除が終わるのを待つ（close 直後はまだ残っていることがある）。"""

    def _done():
        try:
            gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=ctx["poc_branch"])
            return None
        except RequestFailed:
            return True

    wait_until(_done, timeout_sec=1800, message="PoC ブランチの削除")


def _assert_epic_pr(gh_live, owner, repo, ctx, pr, poc_now, e2e_state_path) -> None:
    """epic Draft PR の形と PoC の後片付けを検証する。"""
    assert pr.draft is True, "epic PR が Draft でない"
    assert pr.base.ref == "master", f"epic PR の base が master でない: {pr.base.ref}"
    sections = [
        line for line in (pr.body or "").replace("\r\n", "\n").splitlines() if line.startswith("## ")
    ]
    assert sections == ["## 紐づく Issue"], f"PR 本文のセクションが 紐づく Issue のみでない: {sections}"
    assert poc_now.merged is False, "PoC PR がマージされている（恒久記録として close するだけ）"
    assert pr.number in _watch_numbers(e2e_state_path, ctx["epic"].number), (
        "作成した PR の番号が監視面に登録されていない"
    )


def test_normal_when_no_ui(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, wait_until, e2e_state_path,
):
    """結果に疑問なしのとき epic Draft PR を作り complex-scenario-writer へ引き継ぐことを確認する（正常系・画面変更なし）。"""
    owner, repo = repo_ctx
    ctx = _setup(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory,
        epic_body=EPIC_BODY_NO_UI, report_body=RUNNER_REPORT,
    )

    pr, poc_now = _wait_epic_pr(
        gh_live, owner, repo, ctx, "確認:complex-scenario-writer", wait_until,
        message="PoC PR の close と epic Draft PR の作成",
    )

    _wait_poc_branch_deleted(gh_live, owner, repo, ctx, wait_until)
    _assert_epic_pr(gh_live, owner, repo, ctx, pr, poc_now, e2e_state_path)

    # 検証: epic Issue の自分宛コメントが全て Resolve 済み
    for comment in comments(gh_live, owner, repo, ctx["epic"].number):
        assert server._is_minimized(comment.node_id), f"未 Resolve のコメント: {comment.html_url}"


def test_normal_when_with_ui(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, wait_until, e2e_state_path,
):
    """画面変更ありのとき mock-designer へ指示コメント付きで引き継ぐことを確認する（正常系・画面変更あり）。"""
    owner, repo = repo_ctx
    ctx = _setup(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory,
        epic_body=EPIC_BODY_WITH_UI, report_body=RUNNER_REPORT,
    )

    pr, poc_now = _wait_epic_pr(
        gh_live, owner, repo, ctx, "確認:mock-designer", wait_until,
        message="PoC PR の close と epic Draft PR の作成（mock-designer 引き継ぎ）",
    )

    _wait_poc_branch_deleted(gh_live, owner, repo, ctx, wait_until)
    _assert_epic_pr(gh_live, owner, repo, ctx, pr, poc_now, e2e_state_path)

    # 検証: @mock-designer 宛の指示コメントが未 Resolve で投稿されている
    directed = [
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=pr.number
        ).parsed_data
        if "> to: @mock-designer" in (c.body or "")
    ]
    assert directed, "@mock-designer 宛の指示コメントが投稿されていない"
    assert not server._is_minimized(directed[-1].node_id), "指示コメントが Resolve されている"


def test_error_when_continue(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, wait_until, e2e_state_path,
):
    """結果への疑問をユーザーが解消したあと次フェーズへ進むことを確認する（異常系・続行指示）。"""
    owner, repo = repo_ctx
    ctx = _setup(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory,
        epic_body=EPIC_BODY_NO_UI, report_body=INCONSISTENT_REPORT,
    )

    # 実行: 矛盾の検知による質問コメント（議論中 + assignee）を待つ
    def _questioned():
        data = issue(gh_live, owner, repo, ctx["epic"].number)
        return data if waiting_for_user(data) else None

    data = wait_until(_questioned, timeout_sec=2400, message="PoC 結果への質問コメント")

    # 実行: ユーザーが続行を指示（議論中 除去 + assignee 外し）
    latest = comments(gh_live, owner, repo, ctx["epic"].number)[-1]
    gh_live.rest.issues.update_comment(
        owner=owner, repo=repo, comment_id=latest.id, body=f"{latest.body}\n\n------\n{CONTINUE_ANSWER}"
    )
    try:
        gh_live.rest.issues.remove_label(
            owner=owner, repo=repo, issue_number=ctx["epic"].number, name="議論中"
        )
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=ctx["epic"].number, assignees=[assignee.login]
        )

    pr, poc_now = _wait_epic_pr(
        gh_live, owner, repo, ctx, "確認:complex-scenario-writer", wait_until,
        message="続行指示後の epic Draft PR の作成",
    )
    _wait_poc_branch_deleted(gh_live, owner, repo, ctx, wait_until)
    _assert_epic_pr(gh_live, owner, repo, ctx, pr, poc_now, e2e_state_path)

    # 検証: 質問とユーザー回答が epic Issue に記録され、自分宛コメントが Resolve 済み
    for comment in comments(gh_live, owner, repo, ctx["epic"].number):
        assert server._is_minimized(comment.node_id), f"未 Resolve のコメント: {comment.html_url}"


def test_error_when_reverify(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, wait_until,
):
    """結果への疑問に対しユーザーが再検証を指示したときの差し戻しを確認する（異常系・再検証指示）。"""
    owner, repo = repo_ctx
    ctx = _setup(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory,
        epic_body=EPIC_BODY_NO_UI, report_body=INCONSISTENT_REPORT,
    )

    # 実行: 矛盾の検知による質問コメント（議論中 + assignee）を待つ
    def _questioned():
        data = issue(gh_live, owner, repo, ctx["epic"].number)
        return data if waiting_for_user(data) else None

    data = wait_until(_questioned, timeout_sec=2400, message="PoC 結果への質問コメント")

    # 実行: ユーザーが再検証を指示（議論中 除去 + assignee 外し）
    latest = comments(gh_live, owner, repo, ctx["epic"].number)[-1]
    gh_live.rest.issues.update_comment(
        owner=owner, repo=repo, comment_id=latest.id, body=f"{latest.body}\n\n------\n{REVERIFY_ANSWER}"
    )
    try:
        gh_live.rest.issues.remove_label(
            owner=owner, repo=repo, issue_number=ctx["epic"].number, name="議論中"
        )
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=ctx["epic"].number, assignees=[assignee.login]
        )

    # 実行: 同一 PoC PR への再検証指示を待つ
    def _reverify_requested():
        poc_now = issue(gh_live, owner, repo, ctx["poc_pr"].number)
        if "確認:epic-poc-runner" not in label_names(poc_now):
            return None
        directed = comments_from(gh_live, owner, repo, ctx["poc_pr"].number, "epic-conductor")
        return (poc_now, directed[-1]) if directed else None

    poc_now, instruction = wait_until(
        _reverify_requested, timeout_sec=2400, message="同一 PoC PR への再検証指示"
    )

    # 検証: 再検証指示が @epic-poc-runner 宛で未解決、PoC PR は open のまま
    assert "> to: @epic-poc-runner" in (instruction.body or ""), "再検証指示の宛先が違う"
    assert not server._is_minimized(instruction.node_id), "再検証指示が Resolve されている"
    assert poc_now.state == "open", "PoC PR が close されている（PR・ブランチは保持したまま差し戻す）"

    # 検証: PoC PR が増えておらず、epic Draft PR も作られていない
    pocs = [
        pr for pr in gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        if f"#{ctx['epic'].number}" in (pr.body or "")
    ]
    assert [pr.number for pr in pocs] == [ctx["poc_pr"].number], (
        f"PoC PR が増えている / epic Draft PR が作られている: {[pr.number for pr in pocs]}"
    )

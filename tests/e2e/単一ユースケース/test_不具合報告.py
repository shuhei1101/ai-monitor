"""「不具合報告」の E2E テスト。

手順どおりに進められない事象を決定的に作るため、複製した Wiki のフェーズページを差し替えて
エージェントに欠けた手順書を読ませる（`broken_phase_page`）。

差し替え先に `統合テスト割り当て` を選ぶのは、ユーザーとの往復を挟まずに次の担当へ引き継いで終わる
フェーズで、続行できたか中断したかが確認ラベルの行き先だけで判別できるため（シナリオ代表の選択理由）。
"""
from __future__ import annotations

import pytest

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import issue, label_names, me, waiting_for_user
from tests.e2e.実装対象 import add_worktree
from tests.e2e.統合テスト import STORY_PR_BODY, setup_story, story_branch_files

# 起票されるのはテストデータなので、起票先を sandbox へ上書きした別実行で回す
# （複製 Wiki のページ差し替えが他テストからも見えるため直列実行も前提）
# 起票先の上書き（defect_report）に加え、手順書を書き換えるので単独で走らせる（serial）
pytestmark = [pytest.mark.defect_report, pytest.mark.serial]

PHASE_PAGE = "エージェント/single-scenario-writer/フェーズ/統合テスト割り当て.md"

SCENARIO_DONE_REPORT = """> from: @single-scenario-writer
> to: @{login}

ユースケースシナリオの設計が完了し、ユーザー確認を経て確定しました。

| ファイル | 内容 |
| --- | --- |
| `設計図/シナリオ/` 配下 | 対象シナリオを作成し、索引にも行を追加 |

------
"""

# ラベル遷移だけが存在しないツールを指す状態（他の MCP ツールで代替できる）
UNKNOWN_TOOL_PHASE = """# 統合テスト割り当て

story-conductor から委任された統合テスト一式のうち、テスト実装を single-scenario-tester に割り当てる。

## 手順

### 委任内容の確認

story PR 本文の `## 単一ユースケースシナリオテスト結果` が未記入（セクションが無い、または行が無い）であることを確認する。

### single-scenario-tester への割り当て

MCP `comment` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `sender`: `single-scenario-writer`
- `receiver`: `single-scenario-tester`
- `format`:
  - `type`: `pages`
  - `body`: テスト実装の指示（E2E テスト化するシナリオのページ名）
  - `entries`: 各ページの `page` と `commit`（範囲があれば `start_commit` も）の組

続けて MCP `switch_confirm_labels` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `from_label`: `$AI_MONITOR_LABEL_CONFIRM_SINGLE_SCENARIO_WRITER` の値
- `to_label`: `$AI_MONITOR_LABEL_CONFIRM_SINGLE_SCENARIO_TESTER` の値

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `single-scenario-writer`
- `number`: $pr_number
"""

# 手順が丸ごと欠けた状態（補って完了する余地がない）
EMPTY_PHASE = """# 統合テスト割り当て

story-conductor から委任された統合テスト一式のうち、テスト実装を single-scenario-tester に割り当てる。

## 手順
"""


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file):
    """セットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "commit_file": commit_file,
    }


def _setup(gh_live, owner, repo, factories, sandbox):
    """統合テスト割り当ての起動条件を満たす story 一式を用意する。"""
    # テスト結果表が未記入（セクション自体が無い）の PR
    ctx = setup_story(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"],
        factories["draft_pr_factory"], factories["story_issue_factory"], factories["commit_file"],
        pr_body=STORY_PR_BODY, files=story_branch_files(),
    )
    add_worktree(sandbox["local_path"], ctx["story_branch"])
    # シナリオ設計が済んだ状態（自身の投稿コメントがないと シナリオ作成（初回）が先にマッチする）
    login = gh_live.rest.users.get_authenticated().parsed_data.login
    posted = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number,
        body=SCENARIO_DONE_REPORT.format(login=login),
    ).parsed_data
    server._minimize_comment(posted.node_id)
    return ctx


def _start(gh_live, owner, repo, pr_number):
    """conductor の委任（確認ラベル付与）を再現する。"""
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=["確認:single-scenario-writer"]
    )


def _wait_defect_issue(gh_live, owner, repo, wait_until, *, seeded, message):
    """不具合 Issue（確認ラベルなし + assignee あり）が立つのを待つ。"""

    def _done():
        listed = gh_live.rest.issues.list_for_repo(owner=owner, repo=repo, state="open").parsed_data
        for data in listed:
            if data.number in seeded or data.pull_request is not None:
                continue
            if list(data.labels) or not data.assignees:
                continue
            return data
        return None

    return wait_until(_done, timeout_sec=2400, message=message)


def test_normal_when_workaround(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, sandbox, wait_until, broken_phase_page,
):
    """回避して作業を続けられる場合の報告と続行を確認する（正常系・回避して作業を続けられる）。"""
    owner, repo = repo_ctx
    # 準備: ラベル遷移だけが存在しないツールを指す手順書に差し替える
    broken_phase_page(PHASE_PAGE, UNKNOWN_TOOL_PHASE)
    ctx = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        sandbox,
    )
    seeded = {ctx["story"].number, ctx["epic"].number, ctx["intake"].number, ctx["pr"].number}
    _start(gh_live, owner, repo, ctx["pr"].number)

    # 実行: 不具合 Issue の起票を待つ
    defect = _wait_defect_issue(
        gh_live, owner, repo, wait_until, seeded=seeded, message="不具合 Issue の起票"
    )

    # 検証: assignee がユーザー・ラベルなしで承認待ちになっている
    assert [a.login for a in defect.assignees] == [me(gh_live)]
    assert not list(defect.labels)
    # 検証: 本文から報告元と該当ページを辿れる
    body = (defect.body or "").replace("\r\n", "\n")
    assert "single-scenario-writer" in body
    assert f"#{ctx['pr'].number}" in body
    assert "統合テスト割り当て" in body
    # 検証: 回避策が記録されている（作業を続けられた合図）
    assert "なし（回避できず作業を中断した）" not in body

    # 実行・検証: 本来の割り当ても完了して tester へ渡っている
    def _handed_over():
        data = issue(gh_live, owner, repo, ctx["pr"].number)
        names = label_names(data)
        if "確認:single-scenario-tester" not in names or "確認:single-scenario-writer" in names:
            return None
        return data

    wait_until(_handed_over, timeout_sec=2400, message="tester への割り当て")


def test_normal_when_no_workaround(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, sandbox, wait_until, broken_phase_page,
):
    """作業を続けられない場合の報告と待機を確認する（正常系・作業を続けられない）。"""
    owner, repo = repo_ctx
    # 準備: 手順が丸ごと欠けた手順書に差し替える
    broken_phase_page(PHASE_PAGE, EMPTY_PHASE)
    ctx = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        sandbox,
    )
    seeded = {ctx["story"].number, ctx["epic"].number, ctx["intake"].number, ctx["pr"].number}
    _start(gh_live, owner, repo, ctx["pr"].number)

    # 実行: 不具合 Issue の起票を待つ
    defect = _wait_defect_issue(
        gh_live, owner, repo, wait_until, seeded=seeded, message="不具合 Issue の起票"
    )

    # 検証: assignee がユーザー・ラベルなしで承認待ちになっている
    assert [a.login for a in defect.assignees] == [me(gh_live)]
    assert not list(defect.labels)
    # 検証: 回避できず中断したことが本文から分かる
    body = (defect.body or "").replace("\r\n", "\n")
    assert "なし（回避できず作業を中断した）" in body

    # 実行: 担当 PR が 議論中 + assignee で待機に入るのを待つ
    def _waiting():
        data = issue(gh_live, owner, repo, ctx["pr"].number)
        return data if waiting_for_user(data) else None

    data = wait_until(_waiting, timeout_sec=2400, message="中断の報告と待機")

    # 検証: 起票した Issue へ辿れる中断の報告コメントが残っている
    posted = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["pr"].number
    ).parsed_data
    assert [c for c in posted if f"#{defect.number}" in (c.body or "")], "起票した Issue へのリンクがない"
    # 検証: 次の担当へは渡っていない
    assert "確認:single-scenario-tester" not in label_names(data)

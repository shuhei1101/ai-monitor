"""「マージ」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, comments_from, issue, label_names, waiting_for_user
from tests.e2e.システム import (
    BUILD_DONE_REPORT,
    FOUNDATION_FILES,
    SYSTEM_ISSUE_BODY,
    SYSTEM_PR_BODY_DONE,
    SYSTEM_TITLE,
    system_branch,
    watch_numbers,
)
from tests.e2e.実装対象 import (
    IMPLEMENTED_SERVICE_PY,
    STORY_BODY_TEMPLATE,
    STORY_TITLE,
    PROJECT_FILES,
    RED_TEST_PATH,
    RED_TEST_PY,
    add_worktree,
    setup_subsystem,
)
from tests.e2e.統合テスト import (
    COMPLEX_E2E_TEST_PY,
    add_merged_subsystem,
    E2E_TEST_PY,
    EPIC_PR_BODY_ALL_PASSED,
    STORY_PR_BODY_ALL_PASSED,
    complex_result_rows,
    epic_branch_files,
    setup_epic,
    setup_story,
    story_branch_files,
)

DONE_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [x] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [x] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [x] `update_task` を実装
- [x] 単体テストを作成して実行

## 単体テスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/tasks/test_service.py` | 全実行 | ✅ | 6 ケース |

## 結合テスト結果

なし
"""

MERGE_REQUEST = """> from: @subsystem-conductor
> to: @{login}

設計〜実装レビューの一式が完了しました。マージしてよいかご確認ください。

| 項目 | 状態 |
| --- | --- |
| タスク一覧 | 全チェック済み |
| 単体テスト | 全 pass |

- 問題なければ `議論中` ラベルを外して assignee を外してください

---
"""

WRITER_PASS_REPORT = """> from: @{writer}
> to: @{conductor}

統合テストが全 pass しました。

| ファイル | 結果 |
| --- | --- |
| 新規 + 回帰の全行 | ✅ |

マージをお願いします。

---
"""

SIBLING_EPIC_TITLE = "タスク通知機能"
SIBLING_EPIC_BODY = "期限が近いタスクを通知する（未着手）。"


def _worktree(local_path: str, branch: str) -> Path:
    """ブランチに対応する worktree のパスを返す。"""
    return Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")


def _branch_exists(gh_live, owner, repo, branch: str) -> bool:
    """リモートにブランチが存在するかを返す。"""
    try:
        gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=branch)
        return True
    except RequestFailed:
        return False


def _wait_merged(gh_live, owner, repo, pr_number, wait_until, *, message, timeout_sec=2400):
    """PR が merged になるまで待つ。"""

    def _done():
        data = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr_number).parsed_data
        return data if data.merged else None

    return wait_until(_done, timeout_sec=timeout_sec, message=message)


def _wait_cleaned_up(gh_live, owner, repo, sandbox, branch, wait_until, *, message):
    """マージ後のブランチ削除と worktree 削除が終わるのを待つ。

    マージ直後はまだ conductor のターンが続いているため、後片付けの完了を待ってから検証する。
    """

    def _done():
        if _branch_exists(gh_live, owner, repo, branch):
            return None
        return True if not _worktree(sandbox["local_path"], branch).exists() else None

    return wait_until(_done, timeout_sec=1800, message=message)


def _watch_numbers(state_path: Path, epic_number: int) -> list[int]:
    """モニター台帳から epic-conductor セッションの監視面番号一覧を返す。"""
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        if entry["agent_name"] == "epic-conductor" and entry["primary_number"] == epic_number:
            return entry["watch_numbers"]
    return []


def test_normal_subsystem(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """ユーザー最終承認後の subsystem PR マージと親 story への完了報告を確認する（正常系・subsystem レベル）。"""
    owner, repo = repo_ctx
    login = gh_live.rest.users.get_authenticated().parsed_data.login
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=DONE_PR_BODY,
    )
    files = {
        **PROJECT_FILES,
        "src/tasks/service.py": IMPLEMENTED_SERVICE_PY,
        "tests/tasks/__init__.py": "",
        RED_TEST_PATH: RED_TEST_PY,
    }
    for path, content in files.items():
        commit_file(ctx["subsystem_branch"], path, content, f"chore: e2e 用に {path} を配置")
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])
    pr_number = ctx["pr"].number
    gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=pr_number, draft=False)

    # 準備: マージ起動のゲート中（確認ラベル + 議論中 + assignee）を再現する
    request = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number, body=MERGE_REQUEST.format(login=login)
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=["確認:subsystem-conductor", "議論中"]
    )
    gh_live.rest.issues.add_assignees(
        owner=owner, repo=repo, issue_number=pr_number, assignees=[login]
    )

    # 実行: ユーザー最終承認（議論中 除去 + assignee 外し）→ マージ実行
    gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr_number, name="議論中")
    gh_live.rest.issues.remove_assignees(
        owner=owner, repo=repo, issue_number=pr_number, assignees=[login]
    )
    _wait_merged(gh_live, owner, repo, pr_number, wait_until, message="subsystem PR のマージ")

    # 実行: 親 story への完了報告を待つ
    def _reported():
        story_now = issue(gh_live, owner, repo, ctx["story"].number)
        if "確認:story-conductor" not in label_names(story_now):
            return None
        reports = comments_from(gh_live, owner, repo, ctx["story"].number, "subsystem-conductor")
        return reports[-1] if reports else None

    report = wait_until(_reported, timeout_sec=1800, message="親 story への完了報告")

    # 検証: リモートブランチ・ローカル worktree とも削除済み
    _wait_cleaned_up(
        gh_live, owner, repo, sandbox, ctx["subsystem_branch"], wait_until,
        message="subsystem ブランチ / worktree の削除",
    )

    # 検証: subsystem Issue が close 済み
    assert issue(gh_live, owner, repo, ctx["subsystem"].number).state == "closed", (
        "subsystem Issue が close されていない"
    )

    # 検証: 完了報告が @story-conductor 宛で未解決、確認ラベルは除去済み
    assert "> to: @story-conductor" in (report.body or ""), "完了報告の宛先が story-conductor でない"
    assert not server._is_minimized(report.node_id), "完了報告が Resolve されている（受領は story-conductor）"
    pr_now = issue(gh_live, owner, repo, pr_number)
    assert "確認:subsystem-conductor" not in label_names(pr_now), "確認:subsystem-conductor が残っている"
    assert server._is_minimized(request.node_id), "最終確認の依頼コメントが未 Resolve"


def test_normal_story(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """全 pass 報告後の story PR 自動マージと親 epic への完了報告を確認する（正常系・story レベル）。"""
    owner, repo = repo_ctx
    ctx = setup_story(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file,
        pr_body=STORY_PR_BODY_ALL_PASSED, files=story_branch_files(e2e_test=E2E_TEST_PY),
    )
    # 全 subsystem がマージ済み（closed）の状態にする（子subsystem起票 フェーズを避けるため）
    add_merged_subsystem(gh_live, owner, repo, subsystem_issue_factory, ctx["story"].number)
    add_worktree(sandbox["local_path"], ctx["story_branch"])

    # 準備: writer の全 pass 完了報告 → 確認ラベル付与（自動マージの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["story"].number,
        body=WRITER_PASS_REPORT.format(writer="single-scenario-writer", conductor="story-conductor"),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["story"].number, labels=["確認:story-conductor"]
    )

    merged = _wait_merged(
        gh_live, owner, repo, ctx["pr"].number, wait_until, message="story PR の自動マージ"
    )

    # 検証: epic ブランチへマージされ、ブランチ・worktree とも削除済み
    assert merged.base.ref == ctx["epic_branch"], f"base が epic ブランチでない: {merged.base.ref}"
    _wait_cleaned_up(
        gh_live, owner, repo, sandbox, ctx["story_branch"], wait_until,
        message="story ブランチ / worktree の削除",
    )

    # 実行: 親 epic への完了報告を待つ
    def _reported():
        epic_now = issue(gh_live, owner, repo, ctx["epic"].number)
        if "確認:epic-conductor" not in label_names(epic_now):
            return None
        reports = comments_from(gh_live, owner, repo, ctx["epic"].number, "story-conductor")
        return reports[-1] if reports else None

    epic_report = wait_until(_reported, timeout_sec=1800, message="親 epic への完了報告")

    # 検証: story Issue が close 済み・完了報告が未解決・確認ラベル除去
    assert issue(gh_live, owner, repo, ctx["story"].number).state == "closed", (
        "story Issue が close されていない"
    )
    assert "> to: @epic-conductor" in (epic_report.body or ""), "完了報告の宛先が epic-conductor でない"
    assert not server._is_minimized(epic_report.node_id), "完了報告が Resolve されている"
    assert server._is_minimized(report.node_id), "writer の全 pass 報告が未 Resolve"


def test_normal_epic(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, story_issue_factory,
    commit_file, wait_until, sandbox, master_baseline,
):
    """全 pass 報告後の epic PR マージと配下セッションの一括解放を確認する（正常系・epic レベル）。"""
    owner, repo = repo_ctx
    ctx = setup_epic(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory, commit_file,
        pr_body=EPIC_PR_BODY_ALL_PASSED,
        files=epic_branch_files(complex_e2e_test=COMPLEX_E2E_TEST_PY),
    )
    # 全 story がマージ済み（closed）の状態にする（子story起票 フェーズを避けるため）
    story = story_issue_factory(
        ctx["epic"].number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=ctx["epic"].number),
        labels=["layer:story", "type:feat"],
    )
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=story.number, state="closed", state_reason="completed"
    )
    add_worktree(sandbox["local_path"], ctx["epic_branch"])

    # 準備: writer の全 pass 完了報告 → 確認ラベル付与（終端処理の起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["epic"].number,
        body=WRITER_PASS_REPORT.format(writer="complex-scenario-writer", conductor="epic-conductor"),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["epic"].number, labels=["確認:epic-conductor"]
    )

    merged = _wait_merged(
        gh_live, owner, repo, ctx["pr"].number, wait_until, message="epic PR の master へのマージ"
    )

    # 検証: master へマージされ、ブランチ・worktree とも削除済み
    assert merged.base.ref == "master", f"base が master でない: {merged.base.ref}"
    _wait_cleaned_up(
        gh_live, owner, repo, sandbox, ctx["epic_branch"], wait_until,
        message="epic ブランチ / worktree の削除",
    )

    # 検証: epic Issue が close 済みで、配下に確認ラベルが残っていない
    def _closed():
        epic_now = issue(gh_live, owner, repo, ctx["epic"].number)
        if epic_now.state != "closed":
            return None
        return epic_now if not [n for n in label_names(epic_now) if n.startswith("確認:")] else None

    wait_until(_closed, timeout_sec=1800, message="epic Issue のクローズと確認ラベルの解消")
    assert server._is_minimized(report.node_id), "writer の全 pass 報告が未 Resolve"

    # 検証: epic 配下のエージェントセッションが一括解放されている
    def _released():
        listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
        alive = [
            name for name in listed.stdout.splitlines()
            if any(
                name.startswith(f"ai-monitor-{sandbox['name']}-{number}-")
                for number in (ctx["epic"].number, ctx["pr"].number)
            )
        ]
        return True if not alive else None

    wait_until(_released, timeout_sec=900, message="epic 配下のセッション一括解放")

    # 検証: テスト結果表が全 pass のまま残っている
    rows = complex_result_rows((issue(gh_live, owner, repo, ctx["pr"].number).body or ""))
    assert rows and all("✅" in row for row in rows), f"テスト結果表が全 pass でない: {rows}"


def test_normal_epic_with_parent(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, story_issue_factory,
    issue_factory, commit_file, wait_until, sandbox, master_baseline, e2e_state_path,
):
    """親 system Issue がある epic PR のマージと上位への完了報告を確認する（正常系・上位レイヤーあり）。"""
    owner, repo = repo_ctx
    ctx = setup_epic(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory, commit_file,
        pr_body=EPIC_PR_BODY_ALL_PASSED,
        files=epic_branch_files(complex_e2e_test=COMPLEX_E2E_TEST_PY),
        parent_title=SYSTEM_TITLE, parent_body=SYSTEM_ISSUE_BODY,
        parent_labels=["layer:system", "type:feat"],
    )
    # parent_labels を layer:system にしているので intake キーの実体は system Issue
    system = ctx["intake"]
    # 全 story がマージ済み（closed）の状態にする（子story起票 フェーズを避けるため）
    story = story_issue_factory(
        ctx["epic"].number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=ctx["epic"].number),
        labels=["layer:story", "type:feat"],
    )
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=story.number, state="closed", state_reason="completed"
    )
    # 未着手の兄弟 epic を system にぶら下げる（一括解放が走らないことの確認用）
    sibling = issue_factory(SIBLING_EPIC_TITLE, SIBLING_EPIC_BODY, ["layer:epic", "type:feat"])
    gh_live.rest.issues.add_sub_issue(
        owner=owner, repo=repo, issue_number=system.number, sub_issue_id=sibling.id
    )
    add_worktree(sandbox["local_path"], ctx["epic_branch"])

    # 準備: writer の全 pass 完了報告 → 確認ラベル付与（マージの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["epic"].number,
        body=WRITER_PASS_REPORT.format(writer="complex-scenario-writer", conductor="epic-conductor"),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["epic"].number, labels=["確認:epic-conductor"]
    )

    merged = _wait_merged(
        gh_live, owner, repo, ctx["pr"].number, wait_until, message="epic PR の master へのマージ"
    )

    # 検証: master へマージされ、ブランチ・worktree とも削除済み
    assert merged.base.ref == "master", f"base が master でない: {merged.base.ref}"
    _wait_cleaned_up(
        gh_live, owner, repo, sandbox, ctx["epic_branch"], wait_until,
        message="epic ブランチ / worktree の削除",
    )

    # 実行: 親 system への完了報告を待つ
    def _reported():
        system_now = issue(gh_live, owner, repo, system.number)
        if "確認:system-conductor" not in label_names(system_now):
            return None
        reports = comments_from(gh_live, owner, repo, system.number, "epic-conductor")
        return reports[-1] if reports else None

    system_report = wait_until(_reported, timeout_sec=1800, message="親 system への完了報告")

    # 検証: 完了報告は未解決（受領は system-conductor）で、writer の報告は Resolve 済み
    assert not server._is_minimized(system_report.node_id), "完了報告が Resolve されている"
    assert server._is_minimized(report.node_id), "writer の全 pass 報告が未 Resolve"
    epic_now = issue(gh_live, owner, repo, ctx["epic"].number)
    assert "確認:epic-conductor" not in label_names(epic_now), "確認:epic-conductor が残っている"

    # 検証: 監視面から epic PR の番号だけが除去され、epic Issue の番号は残っている
    def _watch_updated():
        numbers = _watch_numbers(e2e_state_path, ctx["epic"].number)
        return numbers if ctx["pr"].number not in numbers else None

    numbers = wait_until(_watch_updated, timeout_sec=900, message="epic PR の番号が監視面から除去")
    assert ctx["epic"].number in numbers, f"epic Issue の番号が監視面から消えている: {numbers}"

    # 検証: 一括解放が走っておらず、epic 配下のセッションが常駐している
    listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
    alive = [
        name for name in listed.stdout.splitlines()
        if name.startswith(f"ai-monitor-{sandbox['name']}-{ctx['epic'].number}-")
    ]
    assert alive, "epic 配下のセッションが解放されている（一括解放が走った）"

    # 検証: 兄弟 epic が open のまま残っている
    assert issue(gh_live, owner, repo, sibling.number).state == "open", "兄弟 epic が close されている"


def test_normal_system(
    monitor, gh_live, repo_ctx, system_issue_factory, draft_pr_factory, commit_file,
    wait_until, sandbox, master_baseline, e2e_state_path,
):
    """土台生成後の system PR 自動マージと子epic起票への引き継ぎを確認する（正常系・system レベル）。"""
    owner, repo = repo_ctx
    login = gh_live.rest.users.get_authenticated().parsed_data.login
    system = system_issue_factory(
        SYSTEM_TITLE, SYSTEM_ISSUE_BODY, labels=["layer:system", "type:feat"],
    )
    branch = system_branch(system.number)
    pr = draft_pr_factory(
        branch, SYSTEM_TITLE, SYSTEM_PR_BODY_DONE.format(system_number=system.number)
    )
    # 土台生成済みの成果物を system ブランチに積む
    for path, content in FOUNDATION_FILES.items():
        commit_file(branch, path, content, f"docs: e2e 用に {path} を配置")
    add_worktree(sandbox["local_path"], branch)

    # 準備: system-architect の完了報告 → 確認:system-conductor 付与（自動マージの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr.number, body=BUILD_DONE_REPORT.format(login=login)
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:system-conductor"]
    )

    merged = _wait_merged(
        gh_live, owner, repo, pr.number, wait_until, message="system PR の master へのマージ"
    )

    # 検証: master へマージされ、ブランチ・worktree とも削除済み
    assert merged.base.ref == "master", f"base が master でない: {merged.base.ref}"
    _wait_cleaned_up(
        gh_live, owner, repo, sandbox, branch, wait_until, message="system ブランチ / worktree の削除",
    )

    # 検証: 土台が master に入っている
    for path in FOUNDATION_FILES:
        assert gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref="master"), (
            f"master に {path} が入っていない"
        )

    # 実行: 子epic起票への引き継ぎ（system Issue への確認ラベル付与）を待つ
    def _handed_off():
        data = issue(gh_live, owner, repo, system.number)
        return data if "確認:system-conductor" in label_names(data) else None

    wait_until(_handed_off, timeout_sec=1800, message="子epic起票への引き継ぎ")

    # 検証: PR 側の確認ラベルは除去され、完了報告は Resolve 済み
    pr_now = issue(gh_live, owner, repo, pr.number)
    assert "確認:system-conductor" not in label_names(pr_now), "system PR に確認ラベルが残っている"
    assert server._is_minimized(report.node_id), "system-architect の完了報告が未 Resolve"

    # 検証: system PR の番号が監視面から除去されている
    def _watch_updated():
        numbers = watch_numbers(e2e_state_path, "system-conductor", system.number)
        return True if pr.number not in numbers else None

    wait_until(_watch_updated, timeout_sec=900, message="system PR の番号が監視面から除去")


def test_error_conflict(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """base 側の先行変更と競合したときの相談 → 解消 → マージを確認する（異常系・コンフリクト発生）。"""
    owner, repo = repo_ctx
    login = gh_live.rest.users.get_authenticated().parsed_data.login
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=DONE_PR_BODY,
    )
    files = {
        **PROJECT_FILES,
        "src/tasks/service.py": IMPLEMENTED_SERVICE_PY,
        "tests/tasks/__init__.py": "",
        RED_TEST_PATH: RED_TEST_PY,
    }
    for path, content in files.items():
        commit_file(ctx["subsystem_branch"], path, content, f"chore: e2e 用に {path} を配置")
    # base（story ブランチ）側で同じファイルを先に変更してコンフリクトを仕込む
    commit_file(
        ctx["story_branch"], "src/tasks/service.py",
        IMPLEMENTED_SERVICE_PY.replace(
            '"""登録済みタスクのタイトルと本文を更新して返す。"""',
            '"""タスクのタイトルと本文を更新する（base 側の先行変更）。"""',
        ),
        "feat: base 側で service.py を先に変更",
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])
    pr_number = ctx["pr"].number
    gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=pr_number, draft=False)

    # 準備: マージ起動のゲート中を再現してユーザー最終承認まで進める
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number, body=MERGE_REQUEST.format(login=login)
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=["確認:subsystem-conductor", "議論中"]
    )
    gh_live.rest.issues.add_assignees(owner=owner, repo=repo, issue_number=pr_number, assignees=[login])
    gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr_number, name="議論中")
    gh_live.rest.issues.remove_assignees(owner=owner, repo=repo, issue_number=pr_number, assignees=[login])

    # 実行: 競合の相談コメント（議論中 + assignee）を待つ
    def _consulted():
        data = issue(gh_live, owner, repo, pr_number)
        if not waiting_for_user(data):
            return None
        consults = comments_from(gh_live, owner, repo, pr_number, "subsystem-conductor")
        return (data, consults[-1]) if consults else None

    data, consult = wait_until(
        _consulted, timeout_sec=2400, message="コンフリクトの相談コメント（議論中 + assignee）"
    )

    # 実行: マージされるまで解消方針の返答を繰り返す（追加の競合で再相談されることがある）
    def _merged_or_asked():
        pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr_number).parsed_data
        if pr_now.merged:
            return ("merged", pr_now)
        current = issue(gh_live, owner, repo, pr_number)
        return ("asked", current) if waiting_for_user(current) else None

    merged = None
    for _ in range(10):
        event, current = wait_until(
            _merged_or_asked, timeout_sec=2400, message="解消の再相談 または subsystem PR マージ"
        )
        if event == "merged":
            merged = current
            break
        latest = comments(gh_live, owner, repo, pr_number)[-1]
        gh_live.rest.issues.update_comment(
            owner=owner, repo=repo, comment_id=latest.id,
            body=f"{latest.body}\n\n---\nPR 側（subsystem ブランチ）の内容を採用して解消してください。",
        )
        for assignee in current.assignees:
            gh_live.rest.issues.remove_assignees(
                owner=owner, repo=repo, issue_number=pr_number, assignees=[assignee.login]
            )
    assert merged is not None, "10 回応答してもマージされなかった"

    # 検証: 解消 commit を含んでマージされ、解消内容が相談スレッドに記録されている
    assert merged.merged is True, "PR がマージされていない"
    thread = next(c for c in comments(gh_live, owner, repo, pr_number) if c.node_id == consult.node_id)
    assert "> from: @subsystem-conductor" in (thread.body or "").split("---", 1)[-1], (
        "解消内容が相談スレッドに返信追記されていない"
    )

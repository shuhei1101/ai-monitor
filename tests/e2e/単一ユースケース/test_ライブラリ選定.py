"""「ライブラリ選定」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import append_user_block, comments, comments_from, issue, label_names, me, waiting_for_user
from tests.e2e.ライブラリPoC import (
    EXTERNAL_LIB_INDEX_MD,
    EXTERNAL_LIB_INDEX_PATH,
    POC_PR_BODY_DONE,
    PREVIOUS_REPORT,
    SUBSYSTEM_PR_BODY,
    WIKI_APPROVAL,
)
from tests.e2e.実装対象 import add_worktree, seed_subsystem_branch, setup_subsystem

EXTERNAL_LIB_DIR = "docs/wiki/外部ライブラリ/"

# PoC 要否判定に該当する未経験ライブラリ 1 件（単一 UC は最小構成で回す）
SINGLE_CANDIDATE_COMPARISON = """> from: @architect
> to: @{login}

タスクの永続化に使うライブラリを調査しました。
外部パッケージを追加できないため、標準ライブラリの sqlite3 を候補にしています。

| 候補 | 概要 | ライセンス | 導入コスト |
| --- | --- | --- | --- |
| sqlite3 | 組み込み RDB（ファイル / インメモリ） | PSF License | 追加インストール不要 |

未経験のため PoC で実測したいです。

| 観点 | 成功条件 |
| --- | --- |
| CRUD | 作成 → 書き込み → 取得 → 更新 → 削除 が一連で成功する |
| 型の往復 | `str` / `int` / `None` が書き込み時と同じ型で取り出せる |

- 候補と検証観点で問題なければ、このコメントに合意の返信をして assignee を外してください

---
"""

# 実績のある既知ライブラリのみ（PoC 要否判定に非該当 = PoC スキップを誘発）
KNOWN_CANDIDATE_COMPARISON = """> from: @architect
> to: @{login}

タスク ID の採番方式を調査しました。
候補は標準ライブラリの `uuid` で、実績が十分にあり PoC 要否判定のカテゴリには該当しません。

| 候補 | 概要 | ライセンス | 実績 |
| --- | --- | --- | --- |
| uuid | 標準ライブラリの UUID 生成（`uuid4`） | PSF License | 広く使われている標準機能 |

推奨: uuid（追加依存なし・衝突確率が実用上無視できる）

- この推奨で問題なければ採用決定の返信をして assignee を外してください

---
"""

# 要件を満たす候補が残らないケース（相談を誘発する）
NO_CANDIDATE_COMPARISON = """> from: @architect
> to: @{login}

`update_task` の入力検証に使うバリデーションライブラリを調査しましたが、要件を満たす候補が残りませんでした。

| 候補 | 判定 | 理由 |
| --- | --- | --- |
| validate-a | 不可 | ライセンスが商用利用不可 |
| validate-b | 不可 | ライセンスが商用利用不可 |
| validate-c | 不可 | メンテナンス停止（最終リリースが 4 年前） |

対応の方向性をご相談させてください。

---
"""

AGREE_SINGLE = (
    "候補（sqlite3）と検証観点（CRUD / 型の往復）で問題ありません。この内容で PoC の検証をお願いします。"
)
ADOPT_KNOWN = "uuid を採用してください。外部ライブラリ Wiki への反映をお願いします。"
ESCALATE_INSTRUCTION = (
    "subsystem レイヤーでは決められない論点なので、subsystem-conductor へエスカレーションしてください。"
)
ADDITIONAL_VERIFY = (
    "結果を確認しました。採用判断の前にトランザクションのロールバックを 1 観点足したいので、"
    "追加検証をお願いします。"
)


def _setup(gh_live, owner, repo, factories, commit_file, sandbox, *, comparison: str, login: str):
    """設計の応答ループ中にライブラリ選定論点が出た状態の subsystem PR を用意する。"""
    ctx = setup_subsystem(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["draft_pr_factory"],
        factories["story_issue_factory"], factories["subsystem_issue_factory"], commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        design_overrides={EXTERNAL_LIB_INDEX_PATH: EXTERNAL_LIB_INDEX_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])
    comment = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=comparison.format(login=login)
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect", "議論中"]
    )
    gh_live.rest.issues.add_assignees(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, assignees=[login]
    )
    return ctx, comment


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory):
    """セットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "subsystem_issue_factory": subsystem_issue_factory,
    }


def _unassign(gh_live, owner, repo, number) -> None:
    """ユーザー役の返信操作（assignee 外しのみ・議論中 は残す）。"""
    data = issue(gh_live, owner, repo, number)
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def _poc_prs(gh_live, owner, repo, subsystem_number: int, *, state: str = "open") -> list:
    """発注された PoC PR の一覧を返す。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state=state, per_page=100).parsed_data
    return [p for p in pulls if p.head.ref.startswith("poc/") and f"#{subsystem_number}" in (p.body or "")]


def _cleanup_poc(gh_live, owner, repo, sandbox, subsystem_number: int) -> None:
    """残った PoC PR / ブランチ / worktree を片付ける。"""
    local_path = sandbox["local_path"]
    for pr in _poc_prs(gh_live, owner, repo, subsystem_number):
        branch = pr.head.ref
        try:
            gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=pr.number, state="closed")
            gh_live.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{branch}")
        except RequestFailed:
            pass
        subprocess.run(
            ["git", "-C", local_path, "worktree", "remove", "--force",
             str(Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-"))],
            capture_output=True, text=True, check=False,
        )
        subprocess.run(
            ["git", "-C", local_path, "branch", "-D", branch], capture_output=True, text=True, check=False
        )
    subprocess.run(["git", "-C", local_path, "worktree", "prune"], capture_output=True, text=True, check=False)


def _new_architect_comment(gh_live, owner, repo, number, seen: set[str]):
    """新しく投稿された architect のコメントを返す。"""
    for comment in comments_from(gh_live, owner, repo, number, "architect"):
        if comment.node_id not in seen:
            return comment
    return None


def test_normal_with_poc(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """合意された候補の PoC 発注と検証指示の投稿を確認する（正常系・PoC あり）。"""
    owner, repo = repo_ctx
    login = me(gh_live)
    ctx, comparison = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, sandbox, comparison=SINGLE_CANDIDATE_COMPARISON, login=login,
    )
    try:
        # 実行: ユーザーが候補・検証観点に合意（assignee 外しのみ）
        append_user_block(gh_live, owner, repo, comparison, AGREE_SINGLE)
        _unassign(gh_live, owner, repo, ctx["pr"].number)

        def _ordered():
            prs = _poc_prs(gh_live, owner, repo, ctx["subsystem"].number)
            if not prs:
                return None
            poc = prs[0]
            labels = {label.name for label in poc.labels}
            if "確認:library-poc-runner" not in labels:
                return None
            return poc if comments_from(gh_live, owner, repo, poc.number, "architect") else None

        poc = wait_until(
            _ordered, timeout_sec=2400, message="PoC PR の作成と検証指示（確認:library-poc-runner）"
        )

        # 検証: base=master・本文に必須セクションが揃っている
        assert poc.base.ref == "master", f"PoC PR の base が master でない: {poc.base.ref}"
        body = (poc.body or "").replace("\r\n", "\n")
        for section in ("## 紐づく Issue", "## 発注元 PR", "## 検証対象", "## 調査結果", "## 検証観点と結果"):
            assert section in body, f"PoC PR 本文に {section} がない"
        assert f"#{ctx['pr'].number}" in body, "発注元 PR の番号がない"

        # 検証: 候補比較コメントのスレッドに PoC PR のリンクが追記されている
        thread = next(
            c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == comparison.node_id
        )
        assert f"#{poc.number}" in (thread.body or ""), "候補比較スレッドに PoC PR のリンクがない"

        # 検証: subsystem PR は 確認:architect + 議論中 のまま結果を待っている
        names = label_names(issue(gh_live, owner, repo, ctx["pr"].number))
        assert "確認:architect" in names and "議論中" in names, (
            f"設計の応答ループ状態が保たれていない: {sorted(names)}"
        )
    finally:
        _cleanup_poc(gh_live, owner, repo, sandbox, ctx["subsystem"].number)


def test_normal_reverify(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """追加検証の依頼で同一 PoC PR へ再発注することを確認する（正常系・追加検証の再発注）。"""
    owner, repo = repo_ctx
    login = me(gh_live)
    ctx, comparison = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, sandbox, comparison=SINGLE_CANDIDATE_COMPARISON, login=login,
    )
    # 準備: 検証済みの PoC PR と、結果まとめの待機状態を再現する
    poc_branch = f"poc/backend/task-edit-{ctx['subsystem'].number}/sqlite3"
    poc = draft_pr_factory(
        poc_branch, f"PoC: sqlite3（#{ctx['subsystem'].number}）",
        POC_PR_BODY_DONE.format(
            subsystem_number=ctx["subsystem"].number, origin_pr_number=ctx["pr"].number
        ),
        base_branch="master",
    )
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=poc.number, body=PREVIOUS_REPORT
    )
    summary = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number,
        body=(
            f"> from: @architect\n> to: @{login}\n\n"
            "sqlite3 の PoC 検証が完了しました。全観点で成功条件を満たしています。\n\n"
            f"- PoC PR: #{poc.number}\n\n"
            "採用を決定する場合はその旨を、追加検証が必要な場合は観点を返信してください。"
        ),
    ).parsed_data
    try:
        # 実行: ユーザーが追加検証を依頼（assignee 外しのみ）
        append_user_block(gh_live, owner, repo, summary, ADDITIONAL_VERIFY)
        _unassign(gh_live, owner, repo, ctx["pr"].number)

        def _reordered():
            poc_now = issue(gh_live, owner, repo, poc.number)
            if "確認:library-poc-runner" not in label_names(poc_now):
                return None
            directed = comments_from(gh_live, owner, repo, poc.number, "architect")
            return (poc_now, directed[-1]) if directed else None

        poc_now, instruction = wait_until(
            _reordered, timeout_sec=2400, message="同一 PoC PR への再検証指示"
        )

        # 検証: 再検証指示が @library-poc-runner 宛で未解決、PoC PR は増えていない
        assert "> to: @library-poc-runner" in (instruction.body or ""), "再検証指示の宛先が違う"
        assert not server._is_minimized(instruction.node_id), "再検証指示が Resolve されている"
        assert poc_now.state == "open", "PoC PR が close されている"
        assert [p.number for p in _poc_prs(gh_live, owner, repo, ctx["subsystem"].number)] == [poc.number], (
            "PoC PR が増えている（同一 PR へ差し戻すはず）"
        )
    finally:
        _cleanup_poc(gh_live, owner, repo, sandbox, ctx["subsystem"].number)


def test_normal_without_poc(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """PoC 不要な既知ライブラリの採用決定と Wiki 反映を確認する（正常系・PoC なしで採用決定）。"""
    owner, repo = repo_ctx
    login = me(gh_live)
    ctx, comparison = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, sandbox, comparison=KNOWN_CANDIDATE_COMPARISON, login=login,
    )
    seen = {comparison.node_id}

    # 実行: ユーザーが採用を決定（assignee 外しのみ）
    append_user_block(gh_live, owner, repo, comparison, ADOPT_KNOWN)
    _unassign(gh_live, owner, repo, ctx["pr"].number)

    # 実行: 外部ライブラリ Wiki への反映を待つ
    def _reflected():
        report = _new_architect_comment(gh_live, owner, repo, ctx["pr"].number, seen)
        if report is None:
            return None
        tree = gh_live.rest.git.get_tree(
            owner=owner, repo=repo, tree_sha=ctx["subsystem_branch"], recursive="1"
        ).parsed_data
        pages = [
            t.path for t in tree.tree
            if t.path.startswith(EXTERNAL_LIB_DIR) and not t.path.endswith("README.md")
        ]
        return (report, pages) if pages else None

    report, pages = wait_until(
        _reflected, timeout_sec=2400, message="外部ライブラリ Wiki への反映（PoC なし）"
    )

    # 検証: PoC PR が一切作られていない
    assert not _poc_prs(gh_live, owner, repo, ctx["subsystem"].number), (
        "PoC 不要のはずが PoC PR が作成されている"
    )
    assert any("uuid" in path for path in pages), f"採用ライブラリのページがない: {pages}"

    # 実行: ユーザーが Wiki を承認（assignee 外しのみ）
    append_user_block(gh_live, owner, repo, report, WIKI_APPROVAL)
    _unassign(gh_live, owner, repo, ctx["pr"].number)

    # 実行: ライブラリ選定関連コメントの一括 Resolve を待つ
    def _wrapped_up():
        return True if server._is_minimized(comparison.node_id) else None

    wait_until(_wrapped_up, timeout_sec=2400, message="ライブラリ選定関連コメントの一括 Resolve")
    assert server._is_minimized(report.node_id), "Wiki 反映報告が未 Resolve"


def test_error_no_candidate(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """適合候補ゼロのときの相談コメントと待機を確認する（異常系・適合候補が見つからない）。"""
    owner, repo = repo_ctx
    login = me(gh_live)
    # 相談コメントは architect 自身が投稿するので、確認ラベルのみで起動をかける
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        design_overrides={EXTERNAL_LIB_INDEX_PATH: EXTERNAL_LIB_INDEX_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])
    consult = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number,
        body=NO_CANDIDATE_COMPARISON.format(login=login),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    # 実行: 相談 + 待機（議論中 + assignee）を待つ
    def _consulted():
        data = issue(gh_live, owner, repo, ctx["pr"].number)
        return data if waiting_for_user(data) else None

    data = wait_until(_consulted, timeout_sec=2400, message="適合候補ゼロの相談コメント（議論中 + assignee）")

    # 検証: 代替方針を並べた相談が投稿され、PoC PR は作られていない
    proposals = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, "architect")
        if c.node_id != consult.node_id
    ] or [consult]
    assert proposals, "相談コメントが投稿されていない"
    assert not _poc_prs(gh_live, owner, repo, ctx["subsystem"].number), "PoC PR が作成されている"
    assert "確認:architect" in label_names(data), "確認:architect が保持されていない"


def test_error_escalate(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """適合候補ゼロからのエスカレーション指示を確認する（異常系・epic へ方針転換）。"""
    owner, repo = repo_ctx
    login = me(gh_live)
    ctx, consult = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, sandbox, comparison=NO_CANDIDATE_COMPARISON, login=login,
    )

    # 実行: ユーザーがエスカレーションを指示（議論中 除去 + assignee 外し）
    append_user_block(gh_live, owner, repo, consult, ESCALATE_INSTRUCTION)
    try:
        gh_live.rest.issues.remove_label(
            owner=owner, repo=repo, issue_number=ctx["pr"].number, name="議論中"
        )
    except RequestFailed:
        pass
    _unassign(gh_live, owner, repo, ctx["pr"].number)

    # 実行: subsystem-conductor へのエスカレーション報告を待つ
    def _escalated():
        data = issue(gh_live, owner, repo, ctx["pr"].number)
        names = label_names(data)
        if "確認:subsystem-conductor" not in names or "確認:architect" in names:
            return None
        reports = comments_from(gh_live, owner, repo, ctx["pr"].number, "architect")
        return (data, reports[-1]) if reports else None

    data, report = wait_until(
        _escalated, timeout_sec=2400, message="subsystem-conductor へのエスカレーション報告"
    )

    # 検証: 報告が @subsystem-conductor 宛で未解決、設計 Wiki への新規 commit なし
    assert "> to: @subsystem-conductor" in (report.body or ""), "報告の宛先が subsystem-conductor でない"
    assert not server._is_minimized(report.node_id), "報告が Resolve されている（受領は conductor）"

    # 検証: 上位 Issue へのラベル付与・コメント投稿が発生していない
    for number in (ctx["story"].number, ctx["epic"].number):
        upper = issue(gh_live, owner, repo, number)
        assert not [n for n in label_names(upper) if n.startswith("確認:")], (
            f"#{number} に確認ラベルが付与されている（レイヤーを跨いだ直接連絡はしない）"
        )
        assert not comments(gh_live, owner, repo, number), f"#{number} にコメントが投稿されている"

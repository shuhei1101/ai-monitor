"""「全体UI設計」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import answer_review_threads

INTAKE_TITLE = "タスク編集画面の追加"
INTAKE_BODY = "既存タスク一覧画面から編集画面へ遷移して編集できるようにする。"

EPIC_TITLE = "タスク編集画面の追加"
EPIC_BODY = """## 概要

既存タスクを編集できる画面を新規追加する。

## 背景

現状はタスクの新規作成のみで編集導線がないため、ユーザーの利便性を上げる。

## ユースケース一覧

| ユースケース | 変更種別 | 概要 | 対応 story | 補足 |
| --- | --- | --- | --- | --- |
| タスク編集 | 変更 | 一覧から編集画面へ遷移して編集内容を保存する | 未作成 | - |

## 横断要件

- 既存の一覧画面のレイアウトは変更しない
- 保存時は既存 API を利用する
"""

INSTRUCTION_BODY = """> from: @epic-conductor
> to: @mock-designer

epic 全体の UI 設計を発注します。

**画面方針の要点:**
- タスク編集画面を新規作成する（既存の一覧画面からの遷移導線を追加）
- レイアウト・スタイルは既存画面と揃える
- モックは 1 案でよい

------
"""

# モック成果物 PR の本文（epic-conductor が『要件確定（完了処理）』で作る形）
MOCK_ARTIFACT_PR_BODY = """## 紐づく Issue

- #{intake_number}

## タスク一覧

- [ ] タスク編集画面のモックを作成
- [ ] `## UI 設計` の画面一覧・画面遷移・モックを記入
"""


def _worktree(local_path, branch):
    """対象ブランチのローカル worktree を用意する（本番では conductor が worktree_create で用意する）。"""
    worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
    subprocess.run(["git", "-C", local_path, "fetch", "origin", branch], check=True)
    subprocess.run(["git", "-C", local_path, "worktree", "add", str(worktree_path), branch], check=True)


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    sandbox, wait_until, tmp_path,
):
    """方針提案 → 承認 → モック作成 → 承認 → 完了処理までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: 5 セクション確定済みの epic Issue（確認ラベルなし）+ 親 intake
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic"]
    )
    # 準備: 要件の SoT になる epic ベース PR（確認ラベルなし = 起動対象にしない）
    epic_branch = f"feat/epic/task-edit-{epic.number}/base"
    epic_pr = epic_pr_factory(
        branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n"
    )
    # 準備: 作業対象のモック成果物 PR（base=epic ブランチ）。UI 設計は成果物 PR 本文が持つ
    branch = f"docs/epic/task-edit-{epic.number}/mock"
    pr = draft_pr_factory(
        branch, f"{EPIC_TITLE}（モック）",
        MOCK_ARTIFACT_PR_BODY.format(intake_number=intake.number), base_branch=epic_branch,
    )
    _worktree(sandbox["local_path"], branch)
    # 準備: epic-conductor の指示コメントを投稿してから確認ラベルを付ける
    instruction = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr.number, body=INSTRUCTION_BODY
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:mock-designer"]
    )

    # 実行: モニターの polling 検知 → 方針提案（初回）完了を待つ
    def _plan_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        body_now = (data.body or "").replace("\r\n", "\n")
        if "議論中" in labels and data.assignees and "### 画面一覧" in body_now:
            return data
        return None

    pr_data = wait_until(_plan_done, timeout_sec=1200, message="方針提案の完了（議論中 + assignee + ### 画面一覧 記入）")

    # 検証: PR 本文に `## UI 設計` と 2 セクション（画面一覧・画面遷移）が記入されている
    body = (pr_data.body or "").replace("\r\n", "\n")
    assert "## UI 設計" in body
    assert "### 画面一覧" in body
    assert "### 画面遷移" in body

    # 実行: 確認事項へ回答してから方針のユーザー承認を再現（議論中 除去 + assignee 外し）
    # （未解決の確認事項が残っていると完了処理が応答ループへ戻す）
    answer_review_threads(gh_live, owner, repo, pr.number)
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in pr_data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    # 実行: モック作成完了を待つ（議論中 + assignee 再セット + PR body に ### モック 記入）
    def _mock_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        body_now = (data.body or "").replace("\r\n", "\n")
        if "議論中" in labels and data.assignees and "### モック" in body_now:
            return data
        return None

    pr_data = wait_until(_mock_done, timeout_sec=1800, message="モック作成の完了（議論中 + assignee + ### モック 記入）")

    # 検証: PR 本文に 3 セクションすべて記入済み
    body = (pr_data.body or "").replace("\r\n", "\n")
    assert "### モック" in body

    # 検証: 待機に入る時点でタスク一覧がチェック済み（commit 直後に入れる規定）
    assert "- [ ]" not in body, f"成果物 PR のタスク一覧に未チェックの行が残っている: {body}"

    # 検証: モック HTML が epic PR 番号配下へ、モック成果物ブランチにコミットされている
    tree = gh_live.rest.git.get_tree(
        owner=owner, repo=repo, tree_sha=branch, recursive="1"
    ).parsed_data
    mock_files = [
        t.path for t in tree.tree
        if t.path.startswith("docs/mock/pages/") and f"/{epic_pr.number}/" in t.path
        and t.path.endswith("index.html")
    ]
    assert mock_files, (
        f"モック HTML が epic PR 番号 {epic_pr.number} 配下にコミットされていない: "
        f"{[t.path for t in tree.tree if t.path.startswith('docs/mock/pages/')]}"
    )

    # 検証: PR に raw.githack.com の URL を含むコメント（モック URL 共有）が投稿されている
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    mock_url_comments = [c for c in pr_comments if "raw.githack.com" in c.body]
    assert mock_url_comments, "モック URL コメント（raw.githack.com）が投稿されていない"

    # 実行: 確認事項へ回答してからモックのユーザー承認を再現（議論中 除去 + assignee 外し）
    # （未解決の確認事項が残っていると完了処理が応答ループへ戻す）
    answer_review_threads(gh_live, owner, repo, pr.number)
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in pr_data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    # 実行: 完了処理完了を待つ（成果物 PR の 確認:mock-designer 除去 + 親 epic PR に 確認:epic-conductor 付与）
    def _wrapped_up():
        pr_now = _get(pr.number)
        epic_pr_now = _get(epic_pr.number)
        pr_labels = {label.name for label in pr_now.labels}
        epic_pr_labels = {label.name for label in epic_pr_now.labels}
        if "確認:mock-designer" not in pr_labels and "確認:epic-conductor" in epic_pr_labels:
            return (pr_now, epic_pr_now)
        return None

    pr_data, epic_pr_data = wait_until(_wrapped_up, timeout_sec=1200, message="完了処理の完了")

    # 検証: 親 epic PR に @epic-conductor 宛の完了報告コメント（未 Resolve）が投稿されている
    epic_comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=epic_pr.number
    ).parsed_data
    completion = [c for c in epic_comments if "> to: @epic-conductor" in c.body]
    assert completion, "@epic-conductor 宛の完了報告コメントが投稿されていない"
    assert not server._is_minimized(completion[-1].node_id), "完了報告が Resolve されてしまっている"

    # 検証: PR のエージェント投稿コメント + 指示コメントが全て Resolve 済み
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    for comment in pr_comments:
        assert server._is_minimized(comment.node_id), f"PR コメント {comment.html_url} が未 Resolve"
    assert server._is_minimized(instruction.node_id), "指示コメントが未 Resolve"


RE_INSTRUCTION_BODY = """> from: @epic-conductor
> to: @mock-designer

epic 全体の UI 設計を発注します。

**画面方針の要点:**
- master にある現状モックを採取し、UC 一覧との対応を整理する
- 現状にあって UC 一覧に無い画面は確認事項として挙げる
- モックは 1 案でよい

------
"""

# master にある現状モック（RE PR がマージ済みの状態）
CURRENT_MOCK_PATH = "docs/mock/pages/タスク編集画面/current/index.html"
CURRENT_MOCK_HTML = (
    "<html><body><h1>タスク編集（現状）</h1>"
    "<form><input name=\"title\"><textarea name=\"content\"></textarea>"
    "<button>保存</button></form></body></html>\n"
)


def _approve(gh_live, owner, repo, number, assignees):
    """ユーザー役の承認操作（確認事項への回答 + 議論中 除去 + assignee 外し）。"""
    # 未解決の確認事項が残っていると完了処理が応答ループへ戻す
    answer_review_threads(gh_live, owner, repo, number)
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name="議論中")
    except RequestFailed:
        pass
    for assignee in assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def test_normal_when_reverse(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    commit_file, sandbox, wait_until,
):
    """現状モックを入力にした全体 UI 設計を実環境で確認する（正常系・リバースエンジニアリング）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: RE 経路の epic Issue + epic Draft PR
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY,
        epic_labels=["layer:epic", "type:docs", "リバースエンジニアリング"],
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}/base"
    epic_pr = epic_pr_factory(
        branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n"
    )
    # 準備: 現状モック RE PR がマージ済み（現状モックが epic ブランチにある）状態を再現する
    commit_file(epic_branch, CURRENT_MOCK_PATH, CURRENT_MOCK_HTML, "docs: 現状モックを追加")
    # 準備: 作業対象のモック成果物 PR（base=epic ブランチ。現状モックを引き継ぐ）
    branch = f"docs/epic/task-edit-{epic.number}/mock"
    pr = draft_pr_factory(
        branch, f"{EPIC_TITLE}（モック）",
        MOCK_ARTIFACT_PR_BODY.format(intake_number=intake.number), base_branch=epic_branch,
    )
    _worktree(sandbox["local_path"], branch)
    # 準備: epic-conductor の採取指示コメントを投稿してから確認ラベルを付ける
    instruction = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr.number, body=RE_INSTRUCTION_BODY
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:mock-designer"]
    )

    # 実行: 方針提案（現状モックの採取）の完了を待つ
    def _plan_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        body_now = (data.body or "").replace("\r\n", "\n")
        if "議論中" in labels and data.assignees and "### 画面一覧" in body_now:
            return data
        return None

    pr_data = wait_until(_plan_done, timeout_sec=1800, message="現状モックの採取と方針提案の完了")

    # 検証: 画面一覧・画面遷移が現状モックの画面と対応して記入されている
    body = (pr_data.body or "").replace("\r\n", "\n")
    assert "## UI 設計" in body and "### 画面一覧" in body and "### 画面遷移" in body
    assert "タスク編集" in body, "現状モックの画面が画面一覧に反映されていない"

    _approve(gh_live, owner, repo, pr.number, pr_data.assignees)

    # 実行: モック作成の完了を待つ
    def _mock_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        body_now = (data.body or "").replace("\r\n", "\n")
        if "議論中" in labels and data.assignees and "### モック" in body_now:
            return data
        return None

    pr_data = wait_until(_mock_done, timeout_sec=2400, message="モック作成の完了")

    # 検証: モックが epic PR 番号配下へ commit され、URL がコメントで共有されている
    tree = gh_live.rest.git.get_tree(owner=owner, repo=repo, tree_sha=branch, recursive="1").parsed_data
    mock_files = [
        t.path for t in tree.tree
        if t.path.startswith("docs/mock/pages/") and f"/{epic_pr.number}/" in t.path
    ]
    assert mock_files, (
        f"epic PR 番号 {epic_pr.number} 配下にモックが commit されていない: "
        f"{[t.path for t in tree.tree if t.path.startswith('docs/mock/pages/')]}"
    )
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    assert [c for c in pr_comments if "raw.githack.com" in (c.body or "")], (
        "モック URL コメント（raw.githack.com）が投稿されていない"
    )

    _approve(gh_live, owner, repo, pr.number, pr_data.assignees)

    # 実行: 完了処理の完了を待つ
    def _wrapped_up():
        pr_now = _get(pr.number)
        epic_pr_now = _get(epic_pr.number)
        if "確認:mock-designer" in {label.name for label in pr_now.labels}:
            return None
        return epic_pr_now if "確認:epic-conductor" in {label.name for label in epic_pr_now.labels} else None

    wait_until(_wrapped_up, timeout_sec=1800, message="完了処理の完了")

    # 検証: 親 epic PR に完了報告（未 Resolve）が投稿され、成果物 PR 側のコメントは全て Resolve 済み
    epic_comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=epic_pr.number
    ).parsed_data
    completion = [c for c in epic_comments if "> to: @epic-conductor" in (c.body or "")]
    assert completion, "@epic-conductor 宛の完了報告コメントが投稿されていない"
    assert not server._is_minimized(completion[-1].node_id), "完了報告が Resolve されてしまっている"
    assert server._is_minimized(instruction.node_id), "採取指示コメントが未 Resolve"
    assert intake is not None

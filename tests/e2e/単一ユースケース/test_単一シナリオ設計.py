"""「単一シナリオ設計」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import answer_review_threads

INTAKE_TITLE = "タスク編集機能"
INTAKE_BODY = "既存タスクを編集できる機能を追加する。"

EPIC_TITLE = "タスク編集機能"
EPIC_BODY = """## 概要

既存タスクを一覧から選択して編集できる機能を提供する。

## 背景

現状はタスクの新規作成のみで編集導線がなく、内容の修正ができない。

## ユースケース一覧

| ユースケース | 変更種別 | 概要 | 対応 story | 補足 |
| --- | --- | --- | --- | --- |
| タスク編集 | 変更 | 一覧から編集画面へ遷移して編集内容を保存する | 未作成 | - |

## 横断要件

- 保存時は既存 API を利用する
"""

STORY_TITLE = "タスク編集"
STORY_BODY_TEMPLATE = """## 概要

ユーザーが一覧からタスクを選択して、内容を編集して保存する。

## 背景

親 epic #{epic_number} の UC「タスク編集」に対応。既存の一覧画面から編集導線を追加する必要がある。

## ユースケース要件

| 要件 | 補足 |
| --- | --- |
| 一覧からタスクを選択して編集画面に遷移できる | - |
| タスクの内容を編集して保存できる | - |
| 保存時にバリデーションエラーをインライン表示 | フィールド直下に表示 |
| 保存成功時にトーストで通知 | 3 秒表示 |
"""


def test_normal(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    sandbox,
    wait_until,
    tmp_path,
):
    """シナリオ作成 → 承認 → 完了処理までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: 要件確定済みの story ベース PR + 作業対象のシナリオ成果物 PR + worktree
    ctx = _setup_scenario_pr(
        gh_live, owner, repo, sandbox,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory,
    )
    story_pr, pr, branch = ctx["story_pr"], ctx["pr"], ctx["branch"]
    # 準備: 確認ラベルを付ける（前工程はなく、指示コメントは不要 = シナリオでもセットアップに指示コメントは書かれていない）
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:single-scenario-writer"]
    )

    # 実行: モニターの polling 検知 → シナリオ作成の完了を待つ（議論中 + assignee + シナリオ md commit）
    def _scenario_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        if not ("議論中" in labels and data.assignees):
            return None
        # story ブランチに 単一ユースケース/*.md が commit されているか
        tree = gh_live.rest.git.get_tree(owner=owner, repo=repo, tree_sha=branch, recursive="1").parsed_data
        scenario_files = [
            t.path for t in tree.tree
            if t.path.startswith("docs/wiki/設計図/シナリオ/単一ユースケース/") and t.path.endswith(".md")
        ]
        if not scenario_files:
            return None
        return (data, scenario_files)

    pr_data, scenario_files = wait_until(
        _scenario_done, timeout_sec=1500, message="シナリオ作成の完了（議論中 + assignee + 単一UC .md commit）"
    )

    # 検証: 待機に入る時点でタスク一覧がチェック済み（commit 直後に入れる規定）
    assert "- [ ]" not in (pr_data.body or ""), (
        f"成果物 PR のタスク一覧に未チェックの行が残っている: {pr_data.body}"
    )

    # 検証: 単一ユースケース .md が新規に commit されている（master には無いパス）
    master_tree = gh_live.rest.git.get_tree(owner=owner, repo=repo, tree_sha="master", recursive="1").parsed_data
    master_paths = {t.path for t in master_tree.tree}
    new_scenarios = [f for f in scenario_files if f not in master_paths]
    assert new_scenarios, f"新規追加された単一UC .md が見つからない（story ブランチ: {scenario_files}）"

    # 検証: シナリオ索引 README も更新されている
    readme_story = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path="docs/wiki/設計図/シナリオ/README.md", ref=branch
    ).parsed_data
    readme_master = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path="docs/wiki/設計図/シナリオ/README.md", ref="master"
    ).parsed_data
    assert readme_story.sha != readme_master.sha, "シナリオ README が更新されていない"

    # 実行: 確認事項へ回答してからシナリオ承認を再現（議論中 除去 + assignee 外し）
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

    # 実行: 完了処理完了を待つ（PR の 確認:single-scenario-writer 除去 + 親 story に 確認:story-conductor 付与 + @story-conductor 宛完了報告コメント投稿）
    def _wrapped_up():
        pr_now = _get(pr.number)
        story_now = _get(story_pr.number)
        pr_labels = {label.name for label in pr_now.labels}
        story_labels = {label.name for label in story_now.labels}
        if not ("確認:single-scenario-writer" not in pr_labels and "確認:story-conductor" in story_labels):
            return None
        story_comments = gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=story_pr.number
        ).parsed_data
        completion = [c for c in story_comments if "> to: @story-conductor" in c.body]
        if not completion:
            return None
        return (pr_now, story_now, completion)

    pr_data, story_data, completion = wait_until(
        _wrapped_up, timeout_sec=1200, message="完了処理の完了（ラベル遷移 + 完了報告投稿）"
    )

    # 検証: @story-conductor 宛の完了報告コメントが未 Resolve
    assert not server._is_minimized(completion[-1].node_id), "完了報告が Resolve されてしまっている"

    # 検証: PR の自身投稿コメントが全て Resolve 済み
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    for comment in pr_comments:
        assert server._is_minimized(comment.node_id), f"PR コメント {comment.html_url} が未 Resolve"


CURRENT_SCENARIO_PATH = "docs/wiki/設計図/シナリオ/単一ユースケース/タスク編集.md"
CURRENT_SCENARIO_MD = """# タスク編集

現状の実装から起こした単一 UC。

## 正常シナリオ

### 期待値

- 一覧に編集後のタイトルと本文が表示されている
"""

FIX_INSTRUCTION = """> from: @story-conductor
> to: @single-scenario-writer

エスカレーションの決定を受けて、単一 UC シナリオの修正をお願いします。

**決定内容:** タイトルの検証はバックエンドでも行う（フロントエンド任せにしない）

修正が終わったら親 Issue へ完了報告してください。

------
"""


def _worktree(local_path, branch):
    """対象ブランチのローカル worktree を用意する（本番では conductor が用意する）。"""
    worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
    subprocess.run(["git", "-C", local_path, "fetch", "origin", branch], check=True)
    subprocess.run(["git", "-C", local_path, "worktree", "add", str(worktree_path), branch], check=True)


ARTIFACT_PR_BODY = """## 紐づく Issue

- #{intake_number}

## タスク一覧

- [ ] `設計図/シナリオ/単一ユースケース/タスク編集.md` を作成 / 更新
- [ ] `設計図/シナリオ/README.md` の `## 一覧` に該当行を追加
"""


def _setup_scenario_pr(
    gh_live, owner, repo, sandbox,
    epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory,
    *, extra_labels=None,
):
    """story ベース PR と、作業対象の単一UCシナリオ成果物 PR まで用意する。

    要件はベース PR が持ち、writer は成果物 PR 上で作業する（規約『ブランチ戦略』の成果物ブランチ）。
    """
    marks = list(extra_labels or [])
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY,
        epic_labels=["layer:epic", *marks],
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}/base"
    epic_pr_factory(
        branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{intake.number}\n"
    )
    story = story_issue_factory(
        epic.number, STORY_TITLE, body=STORY_BODY_TEMPLATE.format(epic_number=epic.number),
        labels=["layer:story", *marks],
    )
    # 要件の SoT になる story ベース PR（確認ラベルなし = 起動対象にしない）
    story_branch = f"feat/story/task-edit-{story.number}/base"
    story_pr = draft_pr_factory(
        story_branch, STORY_TITLE, STORY_BODY_TEMPLATE.format(epic_number=epic.number),
        base_branch=epic_branch,
    )
    # 作業対象の成果物 PR（base=story ブランチ）
    branch = f"docs/story/task-edit-{story.number}/scenario"
    pr = draft_pr_factory(
        branch, f"{STORY_TITLE}（単一ユースケースシナリオ）",
        ARTIFACT_PR_BODY.format(intake_number=intake.number), base_branch=story_branch,
    )
    _worktree(sandbox["local_path"], branch)
    return {
        "intake": intake, "epic": epic, "story": story,
        "story_pr": story_pr, "pr": pr, "branch": branch,
    }


def test_normal_when_scenario_fix(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, sandbox, wait_until,
):
    """エスカレーションの決定を受けたシナリオ修正を実環境で確認する（正常系・エスカレーション由来のシナリオ修正）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: 確定済みシナリオが載ったシナリオ成果物 PR
    ctx = _setup_scenario_pr(
        gh_live, owner, repo, sandbox,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory,
    )
    story_pr, pr, branch = ctx["story_pr"], ctx["pr"], ctx["branch"]
    commit_file(branch, CURRENT_SCENARIO_PATH, CURRENT_SCENARIO_MD, "docs: 単一UC シナリオを追加")
    seed = gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=branch).parsed_data.commit.sha

    # 準備: story-conductor のシナリオ修正指示 → 確認ラベル付与（起動トリガー）
    instruction = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr.number, body=FIX_INSTRUCTION
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:single-scenario-writer"]
    )

    # 実行: 修正完了（親 story へ完了報告 + PR の確認ラベル除去）を待つ
    def _fixed():
        pr_now = _get(pr.number)
        if "確認:single-scenario-writer" in {label.name for label in pr_now.labels}:
            return None
        story_now = _get(story_pr.number)
        if "確認:story-conductor" not in {label.name for label in story_now.labels}:
            return None
        story_comments = gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=story_pr.number
        ).parsed_data
        completion = [c for c in story_comments if "> to: @story-conductor" in (c.body or "")]
        return completion if completion else None

    completion = wait_until(_fixed, timeout_sec=1800, message="シナリオ修正の完了報告")

    # 検証: 修正 commit が story ブランチに積まれている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed}...{branch}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert CURRENT_SCENARIO_PATH in changed, f"シナリオの修正 commit が積まれていない: {changed}"

    # 検証: 指示コメントに修正内容が返信追記され、Resolve 済み
    thread = next(
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=pr.number
        ).parsed_data if c.node_id == instruction.node_id
    )
    assert "> from: @single-scenario-writer" in (thread.body or ""), "修正内容が返信追記されていない"
    assert server._is_minimized(instruction.node_id), "シナリオ修正指示コメントが未 Resolve"

    # 検証: 完了報告が未 Resolve のまま親 story PR に投稿されている
    assert not server._is_minimized(completion[-1].node_id), "完了報告が Resolve されている"


def test_normal_when_reverse(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, sandbox, wait_until,
):
    """現状のシナリオを入力にした単一 UC シナリオ設計を実環境で確認する（正常系・リバースエンジニアリング）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: RE 経路の epic / story と、現状のシナリオが入ったシナリオ成果物 PR
    ctx = _setup_scenario_pr(
        gh_live, owner, repo, sandbox,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory,
        extra_labels=["type:docs", "リバースエンジニアリング"],
    )
    pr, branch = ctx["pr"], ctx["branch"]
    commit_file(branch, CURRENT_SCENARIO_PATH, CURRENT_SCENARIO_MD, "docs: 現状の単一UC シナリオを追加")
    seed = gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=branch).parsed_data.commit.sha
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:single-scenario-writer"]
    )

    # 実行: シナリオ作成の完了（議論中 + assignee）を待つ
    def _scenario_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    pr_data = wait_until(_scenario_done, timeout_sec=1800, message="現状からのシナリオ整理の完了")

    # 検証: 現状のシナリオを起点にした差分（あるべき姿への変更）が積まれている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed}...{branch}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert CURRENT_SCENARIO_PATH in changed, f"現状のシナリオが更新されていない: {changed}"
    assert "docs/wiki/設計図/シナリオ/README.md" in changed, f"シナリオ索引が更新されていない: {changed}"

    # 検証: 確認事項コメントが投稿されている
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    assert [c for c in pr_comments if (c.body or "").lstrip().startswith("> from: @single-scenario-writer")], (
        "確認事項コメントが投稿されていない"
    )
    assert pr_data is not None

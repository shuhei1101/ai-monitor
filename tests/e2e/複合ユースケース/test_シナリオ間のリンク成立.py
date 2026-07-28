"""「シナリオ間のリンク成立」の E2E テスト。"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from githubkit.exception import RequestFailed

INTAKE_TITLE = "タスク編集機能"
INTAKE_BODY = "既存タスクを編集できる機能を追加する。"

EPIC_TITLE = "タスク編集機能"
# 子story起票 の起動条件に合わせて 対応 story 列は 未起票 のままにする
EPIC_BODY = """## 前提条件

なし

## 概要

既存タスクを一覧から選択して編集できる機能を提供する。

## 背景

現状はタスクの新規作成のみで編集導線がなく、内容の修正ができない。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| タスク編集 | 一覧から編集画面へ遷移して編集内容を保存する | 未起票 |

## 横断要件

- 保存時は既存 API を利用する
"""

COMPLEX_DIR = "docs/wiki/設計図/シナリオ/複合ユースケース/"
SINGLE_DIR = "docs/wiki/設計図/シナリオ/単一ユースケース/"
# 複合UC の click 行（`click {ID} "../単一ユースケース/{UC名}.md#{アンカー}"`）
CLICK_PATTERN = re.compile(r'click\s+\S+\s+"\.\./単一ユースケース/([^"#]+)(?:#([^"]*))?"')


def _issue(gh_live, owner, repo, number):
    """Issue / PR の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def _label_names(data) -> set[str]:
    """スナップショットのラベル名集合を返す。"""
    return {label.name for label in data.labels}


def _tree_paths(gh_live, owner, repo, ref, prefix) -> list[str]:
    """指定 ref で prefix から始まる .md のパス一覧を返す。"""
    tree = gh_live.rest.git.get_tree(owner=owner, repo=repo, tree_sha=ref, recursive="1").parsed_data
    return [t.path for t in tree.tree if t.path.startswith(prefix) and t.path.endswith(".md")]


def _file_text(gh_live, owner, repo, path, ref) -> str:
    """指定 ref のファイル内容を返す。"""
    import base64

    content = gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref).parsed_data
    return base64.b64decode(content.content).decode("utf-8")


def _anchor(heading: str) -> str:
    """見出しテキストを Pages の見出し ID 規則でアンカー化する。"""
    # 小文字化 → 記号除去 → 空白をハイフンに置換
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower(), flags=re.UNICODE)
    return re.sub(r"\s+", "-", text)


def _add_worktree(local_path: str, branch: str) -> None:
    """指定ブランチのローカル worktree を作る（前工程の conductor が用意する分の再現）。"""
    worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", local_path, "fetch", "origin", branch], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", local_path, "worktree", "add", str(worktree_path), branch],
        check=True, capture_output=True,
    )


def _approve(gh_live, owner, repo, number, assignees) -> None:
    """ユーザー役の承認操作（議論中 除去 + assignee 外し）。"""
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name="議論中")
    except RequestFailed:
        pass
    for assignee in assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def _cleanup_agent_stories(gh_live, owner, repo, sandbox, story_numbers: list[int]) -> None:
    """エージェントが起票した story の PR / ブランチ / worktree を片付ける。

    story Issue 自体は親 intake からの再帰クローズで回収されるが、
    その PR は本文が story 番号を参照するため親 factory の掃除対象から外れる。
    """
    local_path = sandbox["local_path"]
    try:
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    except RequestFailed:
        pulls = []
    for pr in pulls:
        if not any(f"#{number}" in (pr.body or "") for number in story_numbers):
            continue
        branch = pr.head.ref
        try:
            gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=pr.number, state="closed")
        except RequestFailed:
            pass
        try:
            gh_live.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{branch}")
        except RequestFailed:
            pass
        worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
        subprocess.run(
            ["git", "-C", local_path, "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True, text=True, check=False,
        )
        subprocess.run(
            ["git", "-C", local_path, "branch", "-D", branch], capture_output=True, text=True, check=False
        )
    subprocess.run(["git", "-C", local_path, "worktree", "prune"], capture_output=True, text=True, check=False)


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, sandbox, wait_until,
):
    """複合シナリオ → 子story起票 → story要件確定 → 単一シナリオでリンクが成立することを確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: ユースケース一覧 確定済みの epic Issue + epic Draft PR + epic ブランチの worktree
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    epic_pr = epic_pr_factory(
        branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n"
    )
    _add_worktree(sandbox["local_path"], epic_branch)
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=epic_pr.number, labels=["確認:complex-scenario-writer"]
    )

    story_numbers: list[int] = []
    try:
        # 実行: 複合シナリオ設計（作成 → 待機）を待つ
        def _complex_scenario_done():
            data = _issue(gh_live, owner, repo, epic_pr.number)
            names = _label_names(data)
            if "議論中" not in names or not data.assignees:
                return None
            files = _tree_paths(gh_live, owner, repo, epic_branch, COMPLEX_DIR)
            return (data, files) if files else None

        pr_data, complex_files = wait_until(
            _complex_scenario_done, timeout_sec=1800,
            message="複合シナリオ設計の完了（議論中 + assignee + 複合UC .md commit）",
        )

        # 検証: 複合UC .md が epic ブランチに新規 commit されている
        master_paths = set(_tree_paths(gh_live, owner, repo, "master", COMPLEX_DIR))
        new_complex = [path for path in complex_files if path not in master_paths]
        assert new_complex, f"新規追加された複合UC .md が見つからない: {complex_files}"

        # 準備: ユーザー承認（複合シナリオの確定）
        _approve(gh_live, owner, repo, epic_pr.number, pr_data.assignees)

        # 実行: 完了報告 → epic-conductor の子story起票 を待つ
        def _stories_created():
            epic_now = _issue(gh_live, owner, repo, epic.number)
            if any(name.startswith("確認:") for name in _label_names(epic_now)):
                return None
            subs = gh_live.rest.issues.list_sub_issues(
                owner=owner, repo=repo, issue_number=epic.number
            ).parsed_data
            return (epic_now, subs) if subs else None

        epic_now, stories = wait_until(
            _stories_created, timeout_sec=1800, message="子story起票の完了（story Issue 起票 + 確認:* 除去）"
        )
        story_numbers = [story.number for story in stories]

        # 検証: ユースケース一覧の行数と同数の story が layer:story + 確認:story-conductor で起票されている
        uc_rows = [
            line for line in (epic_now.body or "").replace("\r\n", "\n")
            .split("## ユースケース一覧", 1)[1].split("\n## ", 1)[0].splitlines()
            if line.startswith("|")
        ][2:]
        assert len(stories) == len(uc_rows), (
            f"ユースケース一覧 {len(uc_rows)} 行に対し story が {len(stories)} 件"
        )
        for story in stories:
            names = _label_names(story)
            assert "layer:story" in names, f"#{story.number} に layer:story がない: {sorted(names)}"
            assert "確認:story-conductor" in names, (
                f"#{story.number} に 確認:story-conductor がない: {sorted(names)}"
            )
        assert "未起票" not in (epic_now.body or ""), "対応 story 列に 未起票 が残っている"
        for number in story_numbers:
            assert f"#{number}" in (epic_now.body or ""), f"対応 story 列に #{number} が反映されていない"

        story = stories[0]

        # 実行: story要件確定（本文確定 → 待機）を待つ
        def _story_requirements_done():
            data = _issue(gh_live, owner, repo, story.number)
            names = _label_names(data)
            return data if "議論中" in names and data.assignees else None

        story_data = wait_until(
            _story_requirements_done, timeout_sec=1800,
            message="story要件確定の完了（議論中 + assignee）",
        )

        # 検証: story 本文に 4 セクションが揃い、親 epic の UC との対応が書かれている
        story_body = (story_data.body or "").replace("\r\n", "\n")
        for section in ("## 前提条件", "## 概要", "## 背景", "## ユースケース要件"):
            assert section in story_body, f"story 本文に {section} がない"
        assert f"#{epic.number}" in story_body, "story 本文の 背景 に親 epic の番号がない"

        # 準備: ユーザー承認（story 要件の確定）
        _approve(gh_live, owner, repo, story.number, story_data.assignees)

        # 実行: story Draft PR の作成 + 確認:single-scenario-writer の付与を待つ
        def _story_pr_created():
            story_now = _issue(gh_live, owner, repo, story.number)
            if "確認:story-conductor" in _label_names(story_now):
                return None
            pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
            candidates = [p for p in pulls if f"#{story.number}" in (p.body or "")]
            if not candidates:
                return None
            pr = candidates[0]
            labels = {label.name for label in pr.labels}
            return pr if "確認:single-scenario-writer" in labels else None

        story_pr = wait_until(
            _story_pr_created, timeout_sec=1800,
            message="story Draft PR の作成（確認:single-scenario-writer 付与）",
        )
        story_branch = story_pr.head.ref
        assert story_pr.base.ref == epic_branch, (
            f"story PR の base が epic ブランチでない: {story_pr.base.ref}"
        )

        # 実行: 単一シナリオ設計（作成 → 待機）を待つ
        def _single_scenario_done():
            data = _issue(gh_live, owner, repo, story_pr.number)
            names = _label_names(data)
            if "議論中" not in names or not data.assignees:
                return None
            files = _tree_paths(gh_live, owner, repo, story_branch, SINGLE_DIR)
            return (data, files) if files else None

        story_pr_data, single_files = wait_until(
            _single_scenario_done, timeout_sec=1800,
            message="単一シナリオ設計の完了（議論中 + assignee + 単一UC .md commit）",
        )

        # 検証: 単一UC .md が story ブランチに新規 commit されている
        master_single = set(_tree_paths(gh_live, owner, repo, "master", SINGLE_DIR))
        new_single = [path for path in single_files if path not in master_single]
        assert new_single, f"新規追加された単一UC .md が見つからない: {single_files}"

        # 準備: ユーザー承認（単一シナリオの確定）
        _approve(gh_live, owner, repo, story_pr.number, story_pr_data.assignees)

        # 実行: 単一シナリオ設計の完了処理（親 story への完了報告）を待つ
        def _single_scenario_wrapped_up():
            pr_now = _issue(gh_live, owner, repo, story_pr.number)
            story_now = _issue(gh_live, owner, repo, story.number)
            if "確認:single-scenario-writer" in _label_names(pr_now):
                return None
            return story_now if "確認:story-conductor" in _label_names(story_now) else None

        wait_until(
            _single_scenario_wrapped_up, timeout_sec=1800,
            message="単一シナリオ設計の完了処理（親 story への完了報告）",
        )

        # 実行: story ブランチを epic ブランチへ取り込む（後続工程のマージ相当）
        gh_live.rest.repos.merge(
            owner=owner, repo=repo, base=epic_branch, head=story_branch,
            commit_message=f"chore: e2e 用に {story_branch} を取り込み",
        )

        # 検証: 複合UC の click リンクが単一UC ファイルとして epic ブランチに実在する
        merged_single = set(_tree_paths(gh_live, owner, repo, epic_branch, SINGLE_DIR))
        checked = 0
        for complex_path in new_complex:
            body = _file_text(gh_live, owner, repo, complex_path, epic_branch)
            links = CLICK_PATTERN.findall(body)
            assert links, f"{complex_path} に単一UC への click リンクがない"
            for filename, fragment in links:
                target = f"{SINGLE_DIR}{filename}"
                assert target in merged_single, (
                    f"{complex_path} の click 先が実在しない: {target}（実在: {sorted(merged_single)}）"
                )
                # 検証: フラグメントが単一UC の見出しアンカーと一致している
                headings = [
                    line[3:] for line in
                    _file_text(gh_live, owner, repo, target, epic_branch).replace("\r\n", "\n").splitlines()
                    if line.startswith("## ")
                ]
                anchors = {_anchor(heading) for heading in headings}
                assert fragment in anchors, (
                    f"{complex_path} の click アンカー #{fragment} が {target} の見出しと一致しない: {sorted(anchors)}"
                )
                checked += 1
        assert checked, "検証した click リンクが 0 件"
    finally:
        _cleanup_agent_stories(gh_live, owner, repo, sandbox, story_numbers)

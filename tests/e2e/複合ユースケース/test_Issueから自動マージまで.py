"""「Issueから自動マージまで」の E2E テスト。"""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import yaml
from githubkit.exception import RequestFailed

from tests.e2e.ゲート応答 import drive_gates
from tests.e2e.エスカレーション import issue, label_names

INTAKE_TITLE = "タスク編集画面の追加"
INTAKE_BODY = """既存タスク一覧画面から編集画面へ遷移して、タスクの内容を編集できるようにしたいです。

- 編集できるのはタイトルと本文
- 保存は既存 API を利用する
- 一覧画面のレイアウトは変えない
"""

# epic 要件確定の確認質問への回答（UC の 正常シナリオ（PoC 不要・画面変更あり）を誘発する）
EPIC_ANSWER = (
    "A（PoC 不要）/ B（画面変更あり: タスク編集画面を新規作成し、一覧画面から遷移導線を追加）でお願いします。"
    "その他の確認事項は推奨案のとおりで問題ありません。"
)


def _sub_issues(gh_live, owner, repo, number: int) -> list:
    """指定 Issue の Sub-issue 一覧を返す。"""
    try:
        return gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=number
        ).parsed_data
    except RequestFailed:
        return []


def _issue_tree(gh_live, owner, repo, intake_number: int) -> dict[str, list[int]]:
    """intake から辿れる Issue 番号をレイヤー別に返す。"""
    epics = [e.number for e in _sub_issues(gh_live, owner, repo, intake_number)]
    stories: list[int] = []
    for epic_number in epics:
        stories += [s.number for s in _sub_issues(gh_live, owner, repo, epic_number)]
    subsystems: list[int] = []
    for story_number in stories:
        subsystems += [s.number for s in _sub_issues(gh_live, owner, repo, story_number)]
    return {"epic": epics, "story": stories, "subsystem": subsystems}


def _open_prs(gh_live, owner, repo) -> list:
    """sandbox の open PR 一覧を返す。"""
    return gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data


def _monitor_alive(port: int) -> bool:
    """モニターの待受ポートが開いているかを返す。"""
    try:
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
        return True
    except OSError:
        return False


def _sessions_for(numbers: list[int], project: str) -> list[str]:
    """指定番号のエージェントセッション名一覧を返す。"""
    listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
    return [
        name for name in listed.stdout.splitlines()
        if any(name.startswith(f"ai-monitor-{project}-{number}-") for number in numbers)
    ]


def test_normal(
    monitor, gh_live, repo_ctx, intake_issue_factory, wait_until, sandbox, e2e_settings_path,
    master_baseline,
):
    """intake 起票から master マージ・intake 自動クローズまでの全工程を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    port = yaml.safe_load(e2e_settings_path.read_text(encoding="utf-8")).get("port", 8765)
    intake = intake_issue_factory(INTAKE_TITLE, INTAKE_BODY)
    answered: set[int] = set()

    def _faces():
        tree = _issue_tree(gh_live, owner, repo, intake.number)
        numbers = [intake.number] + tree["epic"] + tree["story"] + tree["subsystem"]
        faces = [("intake_issue", intake.number)]
        faces += [("epic_issue", number) for number in tree["epic"]]
        faces += [("issue", number) for number in tree["story"] + tree["subsystem"]]
        # PR は本文が Issue 番号を参照しているものを対象にする
        faces += [
            ("pr", pr.number) for pr in _open_prs(gh_live, owner, repo)
            if any(f"#{number}" in (pr.body or "") for number in numbers)
        ]
        return faces

    def _epic_reply(kind, number, history):
        """epic 要件確定の確認質問には 1 度だけ回答する。"""
        if number in answered:
            return None
        answered.add(number)
        return EPIC_ANSWER

    def _terminal():
        current = issue(gh_live, owner, repo, intake.number)
        return current if current.state == "closed" else None

    # 実行: 全工程のユーザー確認ゲートに応答しながら intake のクローズまで進める
    history, closed_intake = drive_gates(
        gh_live, owner, repo,
        faces=_faces,
        choices={("epic_issue", "確認:epic-conductor"): _epic_reply},
        terminal=_terminal,
        wait_until=wait_until,
        max_rounds=60, timeout_sec=5400, interval_sec=60,
    )

    # 検証: intake Issue が completed で close されている
    assert closed_intake.state_reason == "completed", (
        f"intake の close 理由が completed でない: {closed_intake.state_reason}"
    )

    # 検証: epic PR が master へ merge 済み
    tree = _issue_tree(gh_live, owner, repo, intake.number)
    assert tree["epic"], "epic Issue が起票されていない"
    all_numbers = [intake.number] + tree["epic"] + tree["story"] + tree["subsystem"]
    closed_prs = gh_live.rest.pulls.list(
        owner=owner, repo=repo, state="closed", per_page=100
    ).parsed_data
    epic_prs = [
        pr for pr in closed_prs
        if pr.base.ref == "master" and any(f"#{number}" in (pr.body or "") for number in tree["epic"])
    ]
    assert epic_prs, "epic PR が見つからない"
    assert any(
        gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr.number).parsed_data.merged
        for pr in epic_prs
    ), f"epic PR が master へマージされていない: {[pr.number for pr in epic_prs]}"

    # 検証: 全ての中間 Issue が close 済みで、対応ブランチが削除済み
    for number in all_numbers:
        current = issue(gh_live, owner, repo, number)
        assert current.state == "closed", f"#{number}（{current.title}）が open のまま"
    assert not [
        pr for pr in _open_prs(gh_live, owner, repo)
        if any(f"#{number}" in (pr.body or "") for number in all_numbers)
    ], "紐づく PR が open のまま残っている"
    branches = {b.name for b in gh_live.rest.repos.list_branches(
        owner=owner, repo=repo, per_page=100
    ).parsed_data}
    leftovers = [
        pr.head.ref for pr in closed_prs
        if pr.head.ref in branches
        and any(f"#{number}" in (pr.body or "") for number in all_numbers)
    ]
    assert not leftovers, f"マージ後のブランチが削除されていない: {leftovers}"

    # 検証: 処理中ラベルがどの Issue / PR にも残っていない
    for number in all_numbers:
        names = label_names(issue(gh_live, owner, repo, number))
        assert not [name for name in names if name.startswith("処理中:")], (
            f"#{number} に処理中ラベルが残っている: {sorted(names)}"
        )

    # 検証: epic 配下の tmux セッションが全て解放済み
    def _sessions_released():
        return True if not _sessions_for(all_numbers, sandbox["name"]) else None

    wait_until(_sessions_released, timeout_sec=900, message="epic 配下のセッション一括解放")

    # 検証: モニタープロセスが稼働継続している
    assert _monitor_alive(port), "モニタープロセスが停止している"
    assert history, "ユーザー確認ゲートが 1 度も開かなかった"

    # 検証: 本テストで作られたブランチの worktree がローカルに残っていない
    worktree_root = Path(sandbox["local_path"]) / ".claude" / "worktrees"
    own_branches = [
        pr.head.ref for pr in closed_prs
        if any(f"#{number}" in (pr.body or "") for number in all_numbers)
    ]
    remaining = [
        branch for branch in own_branches
        if (worktree_root / branch.replace("/", "-")).exists()
    ]
    assert not remaining, f"worktree が残っている: {remaining}"

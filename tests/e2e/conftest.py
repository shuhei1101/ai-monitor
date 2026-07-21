"""E2E テスト共通の fixture（実モニター + sandbox 実環境・--run-e2e ガード）。"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from githubkit.exception import RequestFailed

import server

REPO_ROOT = Path(__file__).resolve().parents[2]


def pytest_addoption(parser):
    """誤実行防止の --run-e2e フラグを定義する。"""
    parser.addoption(
        "--run-e2e", action="store_true", default=False, help="実モニター + 実 LLM でシナリオ E2E テストを実行する"
    )


def pytest_collection_modifyitems(config, items):
    """--run-e2e なしでは E2E テスト（本フォルダ配下）を全 skip する。"""
    if config.getoption("--run-e2e"):
        return
    skip_marker = pytest.mark.skip(reason="--run-e2e なしのため skip")
    e2e_dir = Path(__file__).resolve().parent
    for item in items:
        if item.path.resolve().is_relative_to(e2e_dir):
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def e2e_settings_path() -> Path:
    """AI_MONITOR_ENV=e2e の設定ファイルパスを返す（未設定なら skip）。"""
    env = os.environ.get("AI_MONITOR_ENV")
    if env != "e2e":
        pytest.skip("AI_MONITOR_ENV=e2e が未設定")
    path = Path.home() / ".config" / "ai-monitor" / f"settings.{env}.yaml"
    if not path.exists():
        pytest.skip(f"{path} が未作成")
    return path


@pytest.fixture(autouse=True)
def sandbox(e2e_settings_path, monkeypatch) -> dict:
    """CWD を sandbox クローンへ切り替え、設定を e2e に向ける。"""
    settings = yaml.safe_load(e2e_settings_path.read_text(encoding="utf-8"))
    project = settings["projects"][0]
    monkeypatch.chdir(project["local_path"])
    monkeypatch.setattr(server, "SETTINGS_PATH", e2e_settings_path)
    monkeypatch.setattr(server, "_client", None, raising=False)
    return project


@pytest.fixture
def gh_live():
    """sandbox 向けの実 githubkit クライアントを返す。"""
    return server._get_client()


@pytest.fixture
def repo_ctx() -> tuple[str, str]:
    """sandbox の (owner, repo) を返す。"""
    return server._get_repo()


@pytest.fixture
def monitor(e2e_settings_path, tmp_path):
    """実モニター（FastAPI + ポーリングループ）をサブプロセスで起動する。"""
    env = os.environ.copy()
    env["AI_MONITOR_ENV"] = "e2e"
    env["STATE_PATH"] = str(tmp_path / "state.yaml")
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    proc = subprocess.Popen(
        ["uv", "run", "python", "-c", "from ai_monitor.main import main; main()"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # 待受ポートの開通を待つ
    port = yaml.safe_load(e2e_settings_path.read_text(encoding="utf-8")).get("port", 8765)
    deadline = time.time() + 60
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"モニターが起動に失敗:\n{proc.stdout.read()[-2000:]}")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            ready = True
            break
        except OSError:
            time.sleep(1)
    if not ready:
        proc.terminate()
        pytest.fail("モニターの待受ポートが開通しない")
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def intake_issue_factory(gh_live, repo_ctx, sandbox):
    """確認ラベル付きの intake Issue を作成し、テスト後に Sub-issue・tmux セッションごと片付ける factory。"""
    owner, repo = repo_ctx
    created: list[int] = []

    def _create(title: str, body: str) -> object:
        issue = gh_live.rest.issues.create(
            owner=owner, repo=repo, title=title, body=body, labels=["確認:intake-issue-triager"]
        ).parsed_data
        created.append(issue.number)
        return issue

    yield _create
    cleanup_numbers: list[int] = []
    for number in reversed(created):
        try:
            subs = gh_live.rest.issues.list_sub_issues(owner=owner, repo=repo, issue_number=number).parsed_data
        except RequestFailed:
            subs = []
        for sub in subs:
            cleanup_numbers.append(sub.number)
            try:
                gh_live.rest.issues.update(
                    owner=owner, repo=repo, issue_number=sub.number, state="closed", state_reason="not_planned"
                )
            except RequestFailed:
                pass
        cleanup_numbers.append(number)
        try:
            gh_live.rest.issues.update(
                owner=owner, repo=repo, issue_number=number, state="closed", state_reason="not_planned"
            )
        except RequestFailed:
            pass
    # テスト中に作られたエージェントセッションを kill する（sandbox の該当番号のみ）
    listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
    for name in listed.stdout.splitlines():
        if any(name.startswith(f"ai-monitor-{sandbox['name']}-{n}-") for n in cleanup_numbers):
            subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True, check=False)


@pytest.fixture
def epic_issue_factory(gh_live, repo_ctx, sandbox):
    """親 intake 付きの epic Issue を作成し、テスト後に PR・ブランチ・worktree・tmux セッションごと片付ける factory。"""
    owner, repo = repo_ctx
    created: list[dict[str, int]] = []

    def _create(
        intake_title: str,
        intake_body: str,
        epic_title: str,
        *,
        epic_body: str = "",
        epic_labels: list[str] | None = None,
    ) -> tuple[object, object]:
        # 親 intake（分解済み想定のため確認ラベルなし）を作成する
        intake = gh_live.rest.issues.create(
            owner=owner, repo=repo, title=intake_title, body=intake_body, labels=["layer:intake", "type:feat"]
        ).parsed_data
        # epic Issue を作成して親 intake に Sub-issue リンクする（既定は本文空 + 確認ラベル付き）
        labels = epic_labels if epic_labels is not None else ["layer:epic", "確認:epic-conductor"]
        epic = gh_live.rest.issues.create(
            owner=owner, repo=repo, title=epic_title, body=epic_body, labels=labels
        ).parsed_data
        gh_live.rest.issues.add_sub_issue(owner=owner, repo=repo, issue_number=intake.number, sub_issue_id=epic.id)
        created.append({"intake": intake.number, "epic": epic.number})
        return intake, epic

    yield _create
    cleanup_numbers: list[int] = []
    branches: list[str] = []
    for pair in reversed(created):
        # epic に紐づく open PR をクローズしてリモートブランチを削除する
        try:
            pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open").parsed_data
        except RequestFailed:
            pulls = []
        for pr in pulls:
            if f"#{pair['epic']}" not in (pr.body or ""):
                continue
            cleanup_numbers.append(pr.number)
            branches.append(pr.head.ref)
            try:
                gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=pr.number, state="closed")
            except RequestFailed:
                pass
            try:
                gh_live.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{pr.head.ref}")
            except RequestFailed:
                pass
        # epic 配下の Sub-issue（story）をクローズする
        try:
            subs = gh_live.rest.issues.list_sub_issues(owner=owner, repo=repo, issue_number=pair["epic"]).parsed_data
        except RequestFailed:
            subs = []
        for sub in subs:
            cleanup_numbers.append(sub.number)
            try:
                gh_live.rest.issues.update(
                    owner=owner, repo=repo, issue_number=sub.number, state="closed", state_reason="not_planned"
                )
            except RequestFailed:
                pass
        # epic → intake の順に not_planned でクローズする
        for number in (pair["epic"], pair["intake"]):
            cleanup_numbers.append(number)
            try:
                gh_live.rest.issues.update(
                    owner=owner, repo=repo, issue_number=number, state="closed", state_reason="not_planned"
                )
            except RequestFailed:
                pass
    # エージェントが作成した worktree とローカルブランチを削除する（sandbox クローン側）
    local_path = sandbox["local_path"]
    for branch in branches:
        worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
        subprocess.run(
            ["git", "-C", local_path, "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True, text=True, check=False,
        )
        subprocess.run(["git", "-C", local_path, "branch", "-D", branch], capture_output=True, text=True, check=False)
    subprocess.run(["git", "-C", local_path, "worktree", "prune"], capture_output=True, text=True, check=False)
    # テスト中に作られたエージェントセッションを kill する（sandbox の該当番号のみ）
    listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
    for name in listed.stdout.splitlines():
        if any(name.startswith(f"ai-monitor-{sandbox['name']}-{n}-") for n in cleanup_numbers):
            subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True, check=False)


@pytest.fixture
def epic_pr_factory(gh_live, repo_ctx):
    """master から空 commit ブランチを生やして Draft PR を作成する factory。

    後片付けは epic_issue_factory の紐づく PR 掃除（close + ブランチ削除）に委ねる。
    """
    owner, repo = repo_ctx

    def _create(branch: str, title: str, body: str) -> object:
        # master 先端の commit / tree を取得して空 commit を作る（API のみで diff なし PR を成立させる）
        base = gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch="master").parsed_data
        commit = gh_live.rest.git.create_commit(
            owner=owner, repo=repo, message="chore: e2e 用の空コミット",
            tree=base.commit.commit.tree.sha, parents=[base.commit.sha],
        ).parsed_data
        gh_live.rest.git.create_ref(owner=owner, repo=repo, ref=f"refs/heads/{branch}", sha=commit.sha)
        return gh_live.rest.pulls.create(
            owner=owner, repo=repo, title=title, head=branch, base="master", body=body, draft=True
        ).parsed_data

    return _create


@pytest.fixture
def epic_body() -> str:
    """5 セクション確定済みの epic Issue 本文（要件確定済み状態の再現用）。"""
    return """## 前提条件

なし

## 概要

タスクの期限が近づいたらメールで通知する機能を提供する。

## 背景

期限切れタスクの見逃しが多く、通知による予防が求められている。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| 期限通知メールの受信 | 期限が近いタスクをメールで通知する | 未起票 |

## 横断要件

- 通知は期限の 24 時間前までに送信する
"""


@pytest.fixture
def wait_until():
    """条件が真値を返すまでポーリングで待つ function fixture。"""

    def _wait(condition, *, timeout_sec: int, interval_sec: int = 15, message: str = ""):
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            value = condition()
            if value:
                return value
            time.sleep(interval_sec)
        pytest.fail(f"タイムアウト（{timeout_sec} 秒）: {message}")

    return _wait

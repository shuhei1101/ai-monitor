"""E2E テスト共通の fixture（実モニター + sandbox 実環境・--run-e2e ガード）。"""
from __future__ import annotations

import base64
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
import yaml
from githubkit.exception import RequestError, RequestFailed

import ai_monitor.mcp.server as server

REPO_ROOT = Path(__file__).resolve().parents[2]

# モニターを全テストで共有するための作業ディレクトリ（xdist の worker 間で共有する）
SHARED_DIR = REPO_ROOT / ".e2e"


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


def pytest_sessionstart(session):
    """前回の実行が残したモニターとロックを掃除する（xdist では controller 側だけが実行する）。

    残骸が生きていると新しい実行が古いコードのモニターに相乗りしてしまうため、必ず停止させる。
    """
    if hasattr(session.config, "workerinput"):
        return
    pid_path = SHARED_DIR / "monitor.pid"
    if pid_path.exists():
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        # 生きていれば止める（既に落ちている場合は無視する）
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
        except ProcessLookupError:
            pass
        pid_path.unlink()
    (SHARED_DIR / "monitor.lock").unlink(missing_ok=True)


def pytest_sessionfinish(session, exitstatus):
    """共有モニターを停止してロックを解放する（xdist では controller 側だけが実行する）。"""
    # worker 側は自分の session 終了ごとに呼ばれるため何もしない（他 worker がまだ走っている）
    if hasattr(session.config, "workerinput"):
        return
    pid_path = SHARED_DIR / "monitor.pid"
    if pid_path.exists():
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        # 起動役のプロセスを止める（既に落ちている場合は無視する）
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        pid_path.unlink()
    (SHARED_DIR / "monitor.lock").unlink(missing_ok=True)


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
def repo_ctx(sandbox) -> tuple[str, str]:
    """sandbox の (owner, repo) を返す。"""
    owner, repo = sandbox["repo"].split("/", 1)
    return (owner, repo)


@pytest.fixture(scope="session")
def e2e_state_path() -> Path:
    """共有モニターのセッション台帳のパスを返す。"""
    return SHARED_DIR / "state.yaml"


@pytest.fixture(scope="session")
def monitor(e2e_settings_path, e2e_state_path):
    """実モニター（FastAPI + ポーリングループ）をテスト全体で 1 本だけ共有する。

    1 プロセスが全対象を監視する本番と同じ構成にすることで、テストを並列実行できる。
    起動役は排他生成したロックファイルで 1 つに決まり、他のプロセスはポート開通を待って相乗りする。
    停止は controller 側の `pytest_sessionfinish` が全 worker の終了後に行う。
    """
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    port = yaml.safe_load(e2e_settings_path.read_text(encoding="utf-8")).get("port", 8765)
    log_path = SHARED_DIR / "monitor.log"
    # ロックをアトミックに作れたプロセスだけが起動役になる
    try:
        os.close(os.open(SHARED_DIR / "monitor.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        is_owner = True
    except FileExistsError:
        is_owner = False
    if is_owner:
        # 起動役の時点でポートが開いていれば、テスト管理外のモニターが占有している
        # （相乗りすると意図しないコードで検証してしまうため落とす）
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            pytest.fail(f"ポート {port} がテスト管理外のプロセスに占有されている")
        except OSError:
            pass
        env = os.environ.copy()
        env["AI_MONITOR_ENV"] = "e2e"
        env["STATE_PATH"] = str(e2e_state_path)
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        # 起動元セッションの環境変数が設定ファイルを上書きしないようにする
        # （SessionStart フックが同名の変数をエージェント向けに展開している）
        for name in ("AI_MONITOR_WIKI_BASE", "WIKI_BASE", "PORT"):
            env.pop(name, None)
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                ["uv", "run", "python", "-c", "from ai_monitor.main import main; main()"],
                cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
            )
        (SHARED_DIR / "monitor.pid").write_text(str(proc.pid), encoding="utf-8")
    # 起動役も相乗り側も待受ポートの開通を待つ
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            break
        except OSError:
            time.sleep(1)
    else:
        tail = log_path.read_text(encoding="utf-8")[-2000:] if log_path.exists() else ""
        pytest.fail(f"モニターの待受ポートが開通しない:\n{tail}")
    yield


def _close_issue_tree(gh_live, owner: str, repo: str, number: int, collected: list[int]) -> None:
    """Sub-issue を再帰的にたどって子から順に not_planned でクローズし、番号を collected に積む。

    エージェントが起票した子孫 Issue は factory の管理外に生まれるため、親から辿って回収する。
    """
    try:
        subs = gh_live.rest.issues.list_sub_issues(owner=owner, repo=repo, issue_number=number).parsed_data
    except RequestFailed:
        subs = []
    for sub in subs:
        _close_issue_tree(gh_live, owner, repo, sub.number, collected)
    collected.append(number)
    try:
        gh_live.rest.issues.update(
            owner=owner, repo=repo, issue_number=number, state="closed", state_reason="not_planned"
        )
    except RequestFailed:
        pass


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
        _close_issue_tree(gh_live, owner, repo, number, cleanup_numbers)
    # テスト中に作られたエージェントセッションを kill する（sandbox の該当番号のみ）
    listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
    for name in listed.stdout.splitlines():
        if any(name.startswith(f"ai-monitor-{sandbox['name']}-{n}-") for n in cleanup_numbers):
            subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True, check=False)


@pytest.fixture
def issue_factory(gh_live, repo_ctx, sandbox):
    """任意のラベルで Issue を作成し、テスト後に Sub-issue・tmux セッションごと片付ける factory。"""
    owner, repo = repo_ctx
    created: list[int] = []

    def _create(title: str, body: str, labels: list[str]) -> object:
        issue = gh_live.rest.issues.create(
            owner=owner, repo=repo, title=title, body=body, labels=labels
        ).parsed_data
        created.append(issue.number)
        return issue

    yield _create
    cleanup_numbers: list[int] = []
    for number in reversed(created):
        _close_issue_tree(gh_live, owner, repo, number, cleanup_numbers)
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
        parent_labels: list[str] | None = None,
    ) -> tuple[object, object]:
        # 親 intake（分解済み想定のため確認ラベルなし）を作成する
        # 上位レイヤーありの検証では parent_labels に layer:system を渡して system Issue にする
        parent_labels_ = parent_labels if parent_labels is not None else ["layer:intake", "type:feat"]
        intake = gh_live.rest.issues.create(
            owner=owner, repo=repo, title=intake_title, body=intake_body, labels=parent_labels_
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
        # intake から子孫（epic → story → subsystem）を辿って子から順にクローズする
        _close_issue_tree(gh_live, owner, repo, pair["intake"], cleanup_numbers)
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
def story_issue_factory(gh_live, repo_ctx, sandbox):
    """親 epic 付きの story Issue を作成し、テスト後に PR・ブランチ・worktree・tmux セッションごと片付ける factory。"""
    owner, repo = repo_ctx
    created: list[int] = []

    def _create(
        parent_epic_number: int,
        title: str,
        *,
        body: str = "",
        labels: list[str] | None = None,
    ) -> object:
        # 既定は本文空 + layer:story + 確認:story-conductor で作成する
        labels_ = labels if labels is not None else ["layer:story", "確認:story-conductor"]
        story = gh_live.rest.issues.create(
            owner=owner, repo=repo, title=title, body=body, labels=labels_
        ).parsed_data
        # 親 epic に Sub-issue リンクする
        gh_live.rest.issues.add_sub_issue(
            owner=owner, repo=repo, issue_number=parent_epic_number, sub_issue_id=story.id
        )
        created.append(story.number)
        return story

    yield _create
    cleanup_numbers: list[int] = []
    branches: list[str] = []
    for story_number in reversed(created):
        # story に紐づく open PR をクローズしてリモートブランチを削除する
        try:
            pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open").parsed_data
        except RequestFailed:
            pulls = []
        for pr in pulls:
            if f"#{story_number}" not in (pr.body or ""):
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
        # story から子孫（エージェントが起票した subsystem）を辿って子から順にクローズする
        _close_issue_tree(gh_live, owner, repo, story_number, cleanup_numbers)
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
def draft_pr_factory(gh_live, repo_ctx):
    """指定 base から空 commit ブランチを生やして Draft PR を作成する factory。

    後片付けは各 issue_factory の紐づく PR 掃除（close + ブランチ削除）に委ねる。
    """
    owner, repo = repo_ctx

    def _create(branch: str, title: str, body: str, *, base_branch: str = "master") -> object:
        # base 先端の commit / tree を取得して空 commit を作る（API のみで diff なし PR を成立させる）
        base = gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=base_branch).parsed_data
        commit = gh_live.rest.git.create_commit(
            owner=owner, repo=repo, message="chore: e2e 用の空コミット",
            tree=base.commit.commit.tree.sha, parents=[base.commit.sha],
        ).parsed_data
        gh_live.rest.git.create_ref(owner=owner, repo=repo, ref=f"refs/heads/{branch}", sha=commit.sha)
        return gh_live.rest.pulls.create(
            owner=owner, repo=repo, title=title, head=branch, base=base_branch, body=body, draft=True
        ).parsed_data

    return _create


@pytest.fixture
def epic_pr_factory(draft_pr_factory):
    """master を base とする Draft PR を作成する factory。"""

    def _create(branch: str, title: str, body: str) -> object:
        return draft_pr_factory(branch, title, body)

    return _create


@pytest.fixture
def commit_file(gh_live, repo_ctx):
    """指定ブランチにファイルを 1 件 commit する function fixture。"""
    owner, repo = repo_ctx

    def _commit(branch: str, path: str, content: str, message: str) -> None:
        # 既存ファイルの上書きには blob の sha が要る（無いと 422 になる）
        try:
            current = gh_live.rest.repos.get_content(
                owner=owner, repo=repo, path=path, ref=branch
            ).parsed_data
            sha = getattr(current, "sha", None)
        except RequestFailed:
            sha = None
        kwargs = {"sha": sha} if sha else {}
        gh_live.rest.repos.create_or_update_file_contents(
            owner=owner, repo=repo, path=path, message=message,
            content=base64.b64encode(content.encode("utf-8")).decode("ascii"), branch=branch,
            **kwargs,
        )

    return _commit


@pytest.fixture
def subsystem_issue_factory(gh_live, repo_ctx, sandbox):
    """親 story 付きの subsystem Issue を作成し、テスト後に PR・ブランチ・worktree・tmux セッションごと片付ける factory。"""
    owner, repo = repo_ctx
    created: list[int] = []

    def _create(
        parent_story_number: int,
        title: str,
        *,
        body: str = "",
        labels: list[str] | None = None,
    ) -> object:
        # 既定は本文空 + layer:subsystem + 確認:subsystem-conductor で作成する
        labels_ = labels if labels is not None else ["layer:subsystem", "確認:subsystem-conductor"]
        subsystem = gh_live.rest.issues.create(
            owner=owner, repo=repo, title=title, body=body, labels=labels_
        ).parsed_data
        # 親 story に Sub-issue リンクする
        gh_live.rest.issues.add_sub_issue(
            owner=owner, repo=repo, issue_number=parent_story_number, sub_issue_id=subsystem.id
        )
        created.append(subsystem.number)
        return subsystem

    yield _create
    cleanup_numbers: list[int] = []
    branches: list[str] = []
    for subsystem_number in reversed(created):
        # subsystem に紐づく open PR をクローズしてリモートブランチを削除する
        try:
            pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open").parsed_data
        except RequestFailed:
            pulls = []
        for pr in pulls:
            if f"#{subsystem_number}" not in (pr.body or ""):
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
        # subsystem Issue を not_planned でクローズする
        cleanup_numbers.append(subsystem_number)
        try:
            gh_live.rest.issues.update(
                owner=owner, repo=repo, issue_number=subsystem_number, state="closed", state_reason="not_planned"
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
def system_issue_factory(gh_live, repo_ctx, sandbox):
    """system Issue を作成し、テスト後に子孫 Issue・PR・ブランチ・worktree・tmux セッションごと片付ける factory。

    system 配下は epic / story / subsystem まで連鎖するため、
    Issue ツリーを先に辿って番号を集め、その番号を指す open PR をまとめて閉じる。
    """
    owner, repo = repo_ctx
    created: list[int] = []

    def _create(title: str, body: str, *, labels: list[str] | None = None) -> object:
        # 既定はユーザーが起票した直後（確認ラベルだけ・layer:system はエージェントが付ける）
        labels_ = labels if labels is not None else ["確認:system-conductor"]
        system = gh_live.rest.issues.create(
            owner=owner, repo=repo, title=title, body=body, labels=labels_
        ).parsed_data
        created.append(system.number)
        return system

    yield _create
    cleanup_numbers: list[int] = []
    for system_number in reversed(created):
        _close_issue_tree(gh_live, owner, repo, system_number, cleanup_numbers)
    # 集めた Issue 番号のいずれかを指す open PR を閉じてリモートブランチを削除する
    branches: list[str] = []
    try:
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    except RequestFailed:
        pulls = []
    for pr in pulls:
        if not any(f"#{number}" in (pr.body or "") for number in cleanup_numbers):
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
def master_baseline(gh_live, repo_ctx):
    """master へマージするテストの後始末として、master のツリーを実行前へ戻す fixture。

    epic PR を master へマージするテストは sandbox の master に成果物を残す。
    残ったまま次のテストが走ると、seed が「既存ファイルを削除した」ように見えて
    レビュー系エージェントが正当に指摘するため、テストごとにツリーを戻す。
    """
    owner, repo = repo_ctx
    baseline = gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch="master").parsed_data
    baseline_tree = baseline.commit.commit.tree.sha
    yield baseline.commit.sha
    current = gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch="master").parsed_data
    if current.commit.commit.tree.sha == baseline_tree:
        return
    # ツリーだけ実行前に戻す commit を積む（履歴は書き換えない）
    restored = gh_live.rest.git.create_commit(
        owner=owner, repo=repo, message="chore: e2e の成果物を master から除去する",
        tree=baseline_tree, parents=[current.commit.sha],
    ).parsed_data
    gh_live.rest.git.update_ref(
        owner=owner, repo=repo, ref="heads/master", sha=restored.sha
    )


@pytest.fixture
def wait_until():
    """条件が真値を返すまでポーリングで待つ function fixture。"""

    def _wait(condition, *, timeout_sec: int, interval_sec: int = 15, message: str = ""):
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            # 長時間のポーリングでは一時的な通信断が起きるので、次の周期に回して待ち続ける
            # （githubkit は通信断を RequestError に包む。ステータス異常の RequestFailed は素通しする）
            try:
                value = condition()
            except httpx.TransportError:
                value = None
            except RequestFailed:
                raise
            except RequestError:
                value = None
            if value:
                return value
            time.sleep(interval_sec)
        pytest.fail(f"タイムアウト（{timeout_sec} 秒）: {message}")

    return _wait

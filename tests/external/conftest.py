"""外部疎通テストの共通 fixture（sandbox 実測・--run-external ガード）。"""
from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path

import pytest
import yaml
from githubkit.exception import RequestFailed

import server


def pytest_addoption(parser):
    """誤実行防止の --run-external フラグを定義する。"""
    parser.addoption(
        "--run-external", action="store_true", default=False, help="実 API に接続する外部疎通テストを実行する"
    )


def pytest_collection_modifyitems(config, items):
    """--run-external なしでは外部疎通テスト（本フォルダ配下）を全 skip する。"""
    if config.getoption("--run-external"):
        return
    skip_marker = pytest.mark.skip(reason="--run-external なしのため skip")
    external_dir = Path(__file__).resolve().parent
    for item in items:
        if item.path.resolve().is_relative_to(external_dir):
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
def issue_factory(gh_live, repo_ctx):
    """sandbox に検証用 Issue を作成し、テスト後にクローズする factory。"""
    owner, repo = repo_ctx
    created: list[int] = []

    def _create(title: str = "外部疎通テスト", body: str = "外部疎通テスト用（自動クローズ）") -> object:
        issue = gh_live.rest.issues.create(owner=owner, repo=repo, title=title, body=body).parsed_data
        created.append(issue.number)
        return issue

    yield _create
    for number in reversed(created):
        try:
            gh_live.rest.issues.update(
                owner=owner, repo=repo, issue_number=number, state="closed", state_reason="not_planned"
            )
        except RequestFailed:
            pass


@pytest.fixture
def branch_factory(gh_live, repo_ctx):
    """master から検証用ブランチ + 3 行ファイルの commit を作成し、テスト後にブランチを削除する factory。"""
    owner, repo = repo_ctx
    created: list[str] = []

    def _create() -> str:
        branch = f"ext/{uuid.uuid4().hex[:8]}"
        sha = gh_live.rest.git.get_ref(owner=owner, repo=repo, ref="heads/master").parsed_data.object_.sha
        gh_live.rest.git.create_ref(owner=owner, repo=repo, ref=f"refs/heads/{branch}", sha=sha)
        gh_live.rest.repos.create_or_update_file_contents(
            owner=owner,
            repo=repo,
            path=f"{branch}.txt",
            branch=branch,
            message="外部疎通テスト用 commit",
            content=base64.b64encode(b"line1\nline2\nline3\n").decode(),
        )
        created.append(branch)
        return branch

    yield _create
    for branch in reversed(created):
        try:
            gh_live.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{branch}")
        except RequestFailed:
            pass


@pytest.fixture
def pr_factory(gh_live, repo_ctx, branch_factory):
    """sandbox に検証用 PR を作成し、テスト後にクローズする factory。"""
    owner, repo = repo_ctx
    created: list[int] = []

    def _create(draft: bool = True) -> object:
        branch = branch_factory()
        pr = gh_live.rest.pulls.create(
            owner=owner,
            repo=repo,
            title=f"外部疎通テスト {branch}",
            body="## 紐づく Issue\n\n- #1",
            head=branch,
            base="master",
            draft=draft,
        ).parsed_data
        created.append(pr.number)
        return pr

    yield _create
    for number in reversed(created):
        try:
            gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=number, state="closed")
        except RequestFailed:
            pass

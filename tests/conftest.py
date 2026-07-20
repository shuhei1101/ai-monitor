"""単体 / 結合テスト共通の fixture。"""
from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

MCP_DIR = Path(__file__).resolve().parents[1] / "plugins" / "ai-monitor" / "mcp"
sys.path.insert(0, str(MCP_DIR))
INJECT_DIR = Path(__file__).resolve().parents[1] / "plugins" / "ai-monitor" / "inject"
sys.path.insert(0, str(INJECT_DIR))
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import server  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch):
    """テスト間でクライアントキャッシュをリセットする。"""
    monkeypatch.setattr(server, "_client", None, raising=False)


@pytest.fixture
def gh(monkeypatch):
    """githubkit クライアントを MagicMock に差し替える。"""
    mock = MagicMock(name="githubkit_client")
    monkeypatch.setattr(server, "_client", mock, raising=False)
    return mock


@pytest.fixture
def resp():
    """parsed_data 付きの REST 応答モックを作る factory。"""

    def _make(data):
        r = MagicMock()
        r.parsed_data = data
        return r

    return _make


@pytest.fixture
def request_failed():
    """モック応答から RequestFailed を作る factory。"""
    from githubkit.exception import RequestFailed

    def _make(status_code: int = 404):
        response = MagicMock()
        response.status_code = status_code
        return RequestFailed(response)

    return _make


@pytest.fixture
def graphql_failed():
    """モック応答から GraphQLFailed を作る factory。"""
    from githubkit.exception import GraphQLFailed

    def _make():
        return GraphQLFailed(MagicMock())

    return _make


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    """一時フォルダに settings.yaml を作成して読み込ませる。"""
    path = tmp_path / "settings.yaml"
    path.write_text(
        "github_token: github_pat_test\n"
        "port: 18999\n"
        "projects:\n"
        "  - name: sandbox\n"
        "    repo: shuhei1101/ai-monitor-e2e\n"
        "    local_path: /tmp/sandbox\n"
        "    wiki_base: https://example.com/wiki\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "SETTINGS_PATH", path)
    return path


@pytest.fixture
def fake_remote(monkeypatch):
    """git remote の解決を sandbox リポジトリの URL に差し替える。"""

    def run(args, **kwargs):
        return NS(args=args, returncode=0, stdout="https://github.com/shuhei1101/ai-monitor-e2e.git\n", stderr="")

    monkeypatch.setattr(server.subprocess, "run", run)


class _FakeWikiResponse:
    def __init__(self, body: str):
        self.status = 200
        self._body = body

    def read(self):
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_wiki(monkeypatch):
    """urlopen をページ辞書ベースの Wiki 応答に差し替え、リクエスト URL を記録する。"""
    state = NS(pages={}, calls=[])

    def fake(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        state.calls.append(url)
        # 登録済みページか（キーは unquote 済み URL）
        unquoted = urllib.parse.unquote(url)
        if unquoted not in state.pages:
            # 未登録: 404 相当のエラー
            raise urllib.error.URLError(f"not found: {unquoted}")
        return _FakeWikiResponse(state.pages[unquoted])

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return state


class _FakeHTTPResponse:
    def __init__(self):
        self.status = 200

    def read(self):
        return b'{"ok": true}'

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def urlopen_calls(monkeypatch):
    """urlopen を 200 応答のモックに差し替え、リクエストを記録する。"""
    calls = []

    def fake(req, timeout=None):
        calls.append(req)
        return _FakeHTTPResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls


@pytest.fixture
def mon_project():
    """モニターテスト用の監視対象プロジェクト設定を返す。"""
    from ai_monitor.shared.settings import MonitoredProject

    return MonitoredProject(
        name="sandbox",
        repo="shuhei1101/ai-monitor-e2e",
        local_path="/tmp/sandbox",
        wiki_base="https://example.com/wiki",
    )


@pytest.fixture
def gh_mon(monkeypatch):
    """モニター側の githubkit クライアントを MagicMock に差し替える。"""
    from ai_monitor.integrations.github import client as gh_client

    mock = MagicMock(name="monitor_githubkit_client")
    monkeypatch.setattr(gh_client, "_client", mock, raising=False)
    return mock


@pytest.fixture
def tmp_state_path(tmp_path) -> Path:
    """一時フォルダの state.yaml パスを返す。"""
    return tmp_path / "state.yaml"


@pytest.fixture
def label_settings():
    """全ラベル値を明示した LabelSettings を生成する。"""
    from ai_monitor.shared.settings import LabelSettings

    values = {}
    for field in LabelSettings.model_fields:
        # フィールド名からラベル値を機械生成する（confirm_epic_conductor → 確認:epic-conductor）
        if field == "in_discussion":
            values[field] = "議論中"
        elif field.startswith("confirm_"):
            values[field] = "確認:" + field.removeprefix("confirm_").replace("_", "-")
        elif field.startswith("processing_"):
            values[field] = "処理中:" + field.removeprefix("processing_").replace("_", "-")
    return LabelSettings(**values)


@pytest.fixture
def tmp_session_name():
    """衝突しないテスト用 tmux セッション名を払い出し、残っていれば kill する。"""
    import uuid

    name = f"ai-monitor-pytest-{uuid.uuid4().hex[:8]}"
    yield name
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True, check=False)


@pytest.fixture
def tmp_tmux_session(tmp_session_name, tmp_path):
    """テスト用 tmux セッションを作成して名前を返す。"""
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", tmp_session_name, "-c", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return tmp_session_name


@pytest.fixture
def mon_settings(mon_project):
    """モニターの結合テスト用の全体設定を返す。"""
    return NS(
        projects=[mon_project],
        poll_interval_sec=1,
        heartbeat_interval_sec=60,
        session_timeout_min=30,
        port=8765,
    )


@pytest.fixture
def mon_registry(tmp_state_path):
    """一時 state.yaml を使う実セッション台帳を返す。"""
    from ai_monitor.features.sessions.registry import SessionRegistry

    return SessionRegistry(tmp_state_path)


@pytest.fixture
def tmux_calls(monkeypatch):
    """tmux 実行入口を記録用モックに差し替える（has-session の終了コードを制御可能）。"""
    import ai_monitor.integrations.tmux.ops as tmux_ops

    state = NS(calls=[], has_session_rc=0)

    def fake(args, check=True):
        state.calls.append(list(args))
        rc = state.has_session_rc if args[0] == "has-session" else 0
        if check and rc != 0:
            raise subprocess.CalledProcessError(rc, ["tmux", *args])
        return subprocess.CompletedProcess(["tmux", *args], rc, stdout="", stderr="")

    monkeypatch.setattr(tmux_ops, "_run_tmux", fake)
    return state


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def tmp_git_repo(tmp_path, monkeypatch):
    """origin 付きの一時 git リポジトリを作成して CWD にする。"""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "master")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", str(origin), str(clone))
    _git(clone, "config", "user.email", "test@example.com")
    _git(clone, "config", "user.name", "test")
    _git(clone, "checkout", "-b", "master")
    (clone / "README.md").write_text("init\n", encoding="utf-8")
    _git(clone, "add", "README.md")
    _git(clone, "commit", "-m", "init")
    _git(clone, "push", "-u", "origin", "master")

    monkeypatch.chdir(clone)
    return clone

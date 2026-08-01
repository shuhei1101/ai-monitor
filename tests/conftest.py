"""単体 / 結合テスト共通の fixture。"""
from __future__ import annotations

import logging
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.metrics.export import MetricExporter

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "ai-monitor"
INJECT_DIR = PLUGIN_DIR / "inject"
sys.path.insert(0, str(INJECT_DIR))
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import ai_monitor.mcp.server as server  # noqa: E402


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
def agent_settings():
    """全エージェント分の AgentSettings を明示した辞書を返す（テスト用に一律 sonnet）。"""
    from ai_monitor.shared.settings import _AGENT_NAMES, AgentSettings

    return {name: AgentSettings(model="sonnet") for name in _AGENT_NAMES}


@pytest.fixture
def label_settings():
    """全ラベル値を明示した LabelSettings を生成する。"""
    from ai_monitor.shared.settings import LabelSettings

    values = {}
    for field in LabelSettings.model_fields:
        # フィールド名からラベル値を機械生成する（confirm_epic_conductor → 確認:epic-conductor）
        if field == "in_discussion":
            values[field] = "議論中"
        elif field == "confirm_prefix":
            values[field] = "確認:"
        elif field.startswith("layer_"):
            values[field] = "layer:" + field.removeprefix("layer_").replace("_", "-")
        elif field.startswith("confirm_"):
            values[field] = "確認:" + field.removeprefix("confirm_").replace("_", "-")
        elif field.startswith("processing_"):
            values[field] = "処理中:" + field.removeprefix("processing_").replace("_", "-")
    # 優先度は機械生成できないため実値を明示する
    values["priority_urgent"] = "優先度:急ぎ"
    values["priority_low"] = "優先度:いつでも"
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
    from ai_monitor.shared.settings import WatchdogSettings

    return NS(
        projects=[mon_project],
        watchdog=WatchdogSettings(),
        poll_interval_sec=1,
        heartbeat_interval_sec=60,
        session_timeout_min=30,
        rate_limit_fallback_min=60,
        port=8765,
        telemetry=None,
        notifies=[],
        ai_monitor_wiki_base="https://example.com/ai-monitor-wiki",
        ai_monitor_repo="shuhei1101/ai-monitor",
    )


@pytest.fixture
def notify():
    """契機通知のスタブを返す（呼び出しを記録する）。"""
    from ai_monitor.features.notify.types import SendResult

    calls: list[tuple[str, str, str, str | None, int | None]] = []

    def _notify(event, title, body, *, repo=None, number=None):
        calls.append((event, title, body, repo, number))
        return SendResult(sent=True)

    _notify.calls = calls
    return _notify


@pytest.fixture
def rate_limit_gate():
    """待機していないレートリミット関門を返す。"""
    from ai_monitor.features.rate_limit.gate import RateLimitGate

    return RateLimitGate()


@pytest.fixture
def mon_registry(tmp_state_path):
    """一時 state.yaml を使う実セッション台帳を返す。"""
    from ai_monitor.features.sessions.registry import SessionRegistry

    return SessionRegistry(tmp_state_path)


@pytest.fixture
def mcp_ctx_factory():
    """`X-Project` ヘッダを持つ MCP リクエストコンテキストのモックを作る factory。"""

    def _create(project: str | None = "sandbox"):
        headers = {} if project is None else {"X-Project": project}
        return NS(request_context=NS(request=NS(headers=headers)))

    return _create


@pytest.fixture
def mcp_agents():
    """MCP ツールが処理中ラベルの解決に使うエージェント定義を返す。"""
    from ai_monitor.features.agents.types import Agent

    return [
        Agent(
            name="architect",
            confirm_label="確認:architect",
            processing_label="処理中:architect",
            model="sonnet",
            effort="high",
        )
    ]


@pytest.fixture
def api(mon_settings, mon_registry, mcp_agents, mcp_ctx_factory, label_settings):
    """設定・台帳・エージェント一覧・ラベル設定・コンテキストを束ねた MCP ツール呼び出し口を返す。"""
    deps = dict(
        ctx=mcp_ctx_factory(),
        settings=mon_settings,
        registry=mon_registry,
        agents=mcp_agents,
        label_settings=label_settings,
    )

    class _Tools:
        def __getattr__(self, name):
            return server._bind(getattr(server, name), **deps)

    return _Tools()


@pytest.fixture
def session_factory(mon_registry):
    """台帳へテスト用のエージェントセッションを登録する factory。"""
    from ai_monitor.features.sessions.types import AgentSession

    def _create(
        agent_name: str, number: int, *, project: str = "sandbox", watch_numbers: list[int] | None = None
    ) -> AgentSession:
        session = AgentSession(
            session_name=f"ai-monitor-{project}-{number}-{agent_name}",
            project=project,
            agent_name=agent_name,
            primary_number=number,
            watch_numbers=list(watch_numbers or []),
        )
        mon_registry.register(session)
        return session

    return _create


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


class _FakeLogExporter:
    """OTLP Log Exporter のスタブ。生成引数と送出済みレコードを記録する。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.records = []
        self.export_calls = 0
        self.shutdown_called = False
        self.fail = False

    def export(self, batch):
        from opentelemetry.sdk._logs.export import LogRecordExportResult

        self.export_calls += 1
        # 送信失敗を誘発する設定なら例外を投げる（Collector 未起動の再現）
        if self.fail:
            raise RuntimeError("Collector に接続できません")
        self.records.extend(batch)
        return LogRecordExportResult.SUCCESS

    def shutdown(self):
        self.shutdown_called = True

    def force_flush(self, timeout_millis: float = 30_000) -> bool:
        return True


class _FakeSpanExporter:
    """OTLP Span Exporter のスタブ。生成引数と送出済み Span を記録する。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.spans = []

    def export(self, spans):
        from opentelemetry.sdk.trace.export import SpanExportResult

        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


class _FakeMetricExporter(MetricExporter):
    """OTLP Metric Exporter のスタブ。生成引数と送出済みメトリクスを記録する。"""

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.metrics = []

    def export(self, metrics_data, timeout_millis: float = 10_000, **kwargs) -> bool:
        self.metrics.append(metrics_data)
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        return None

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True


@pytest.fixture
def otel_stub(monkeypatch):
    """観測基盤のプロセス外依存（3 種の Exporter / atexit）をスタブに差し替える。"""
    from opentelemetry import trace as otel_trace
    from opentelemetry._logs import _internal as logs_internal
    from opentelemetry.metrics import _internal as metrics_internal
    from opentelemetry.util._once import Once

    from ai_monitor.observability import otel

    # 環境変数の値がテストに漏れ込まないように既定値へ戻す
    for name in ("AI_MONITOR_OTEL_OTLP_ENDPOINT", "AI_MONITOR_OTEL_OTLP_INSECURE", "AI_MONITOR_OTEL_DEPLOYMENT_ENVIRONMENT", "AI_MONITOR_OTEL_SERVICE_NAMESPACE"):
        monkeypatch.delenv(name, raising=False)
    # 前のテストが登録した Provider を捨てる（グローバル Provider は 1 度しか設定できない）
    monkeypatch.setattr(otel, "_logger_provider", None)
    monkeypatch.setattr(otel, "_tracer_provider", None)
    monkeypatch.setattr(otel, "_meter_provider", None)
    monkeypatch.setattr(logs_internal, "_LOGGER_PROVIDER", None)
    monkeypatch.setattr(logs_internal, "_LOGGER_PROVIDER_SET_ONCE", Once())
    monkeypatch.setattr(otel_trace, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(otel_trace, "_TRACER_PROVIDER_SET_ONCE", Once())
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER", None)
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER_SET_ONCE", Once())

    state = NS(log_exporters=[], span_exporters=[], metric_exporters=[], atexit_calls=[])

    def _make(cls, sink):
        def _factory(**kwargs):
            exporter = cls(**kwargs)
            sink.append(exporter)
            return exporter

        return _factory

    monkeypatch.setattr(otel, "OTLPLogExporter", _make(_FakeLogExporter, state.log_exporters))
    monkeypatch.setattr(otel, "OTLPSpanExporter", _make(_FakeSpanExporter, state.span_exporters))
    monkeypatch.setattr(otel, "OTLPMetricExporter", _make(_FakeMetricExporter, state.metric_exporters))
    monkeypatch.setattr(otel.atexit, "register", state.atexit_calls.append)

    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield state
    # configure が触った root logger を戻し、送出スレッドを止める
    root.handlers = handlers
    root.setLevel(level)
    for exporter in state.log_exporters:
        exporter.fail = False
    otel.shutdown()


@pytest.fixture
def tmp_git_repo(tmp_path, monkeypatch, mon_project):
    """origin 付きの一時 git リポジトリを作成し、監視対象プロジェクトの local_path に設定する。"""
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

    # 対象リポジトリは設定の local_path で指定する（MCP は常駐プロセスで CWD を対象に使えない）
    mon_project.local_path = str(clone)
    # プロセスの CWD はリポジトリの外に置き、対象リポジトリの取り違えを検出できるようにする
    monkeypatch.chdir(tmp_path)
    return clone


@pytest.fixture(autouse=True)
def block_real_http(request, monkeypatch):
    """実 HTTP 送信を止める（Webhook へ送ろうとしたテストはその場で失敗させる）。

    通知の送出先は設定ファイル由来なので、配線を 1 箇所間違えると実際の Discord / Slack へ飛ぶ。
    テスト側で差し替えていれば後勝ちで上書きされるため、差し替え漏れだけがここで落ちる。
    """
    # 外部疎通テストは実接続の確認が目的なので対象外にする
    if "external" in Path(request.node.fspath).parts:
        return
    import httpx

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "テストから実 HTTP 送信を行おうとしました。送信先はスタブに差し替えてください"
        )

    monkeypatch.setattr(httpx, "post", _blocked)
    monkeypatch.setattr(httpx, "get", _blocked)

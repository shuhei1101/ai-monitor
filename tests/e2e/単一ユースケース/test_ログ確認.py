"""単一UC「ログ確認」の E2E テスト。"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from base64 import b64encode
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_DIR = REPO_ROOT / "plugins" / "ai-monitor"
COMPOSE_FILE = REPO_ROOT.parent / "observability" / "observability.yaml"
GRAFANA_URL = "http://localhost:3000"
GRAFANA_AUTH = b64encode(b"admin:admin").decode()

_EMIT_SCRIPT = """
import logging, sys
sys.path.insert(0, {plugin_dir!r})
from observability import configure, shutdown
configure({service_name!r})
logging.getLogger("ai_monitor.e2e").info({message!r})
shutdown()
"""


@pytest.fixture(autouse=True)
def sandbox():
    """本 UC は GitHub sandbox を使わないため、上位の autouse fixture を無効化する。"""
    return None


def _grafana(path: str, params: dict | None = None) -> dict:
    """Grafana の API を管理者認証で叩いて JSON を返す。"""
    url = f"{GRAFANA_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {GRAFANA_AUTH}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


@pytest.fixture(scope="session")
def datasource_uid() -> str:
    """Grafana に自動プロビジョニングされた Loki datasource の UID を返す。"""
    try:
        datasources = _grafana("/api/datasources")
    except (urllib.error.URLError, TimeoutError):
        pytest.skip(f"観測スタックが未起動（docker compose -f {COMPOSE_FILE} up -d）")
    loki = next((d for d in datasources if d["type"] == "loki"), None)
    if loki is None:
        pytest.fail("Loki datasource がプロビジョニングされていない")
    return loki["uid"]


@pytest.fixture
def emit_log():
    """指定サービス名のプロセスから INFO ログを 1 件送出する factory。"""

    def _emit(service_name: str, message: str) -> None:
        script = _EMIT_SCRIPT.format(
            plugin_dir=str(PLUGIN_DIR), service_name=service_name, message=message
        )
        subprocess.run(
            ["uv", "run", "python", "-c", script],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )

    return _emit


@pytest.fixture
def query_logs(datasource_uid):
    """Grafana 経由で LogQL を投げ、ヒットしたストリームを返す factory。"""

    def _query(logql: str, *, timeout_sec: int = 60) -> list[dict]:
        deadline = time.time() + timeout_sec
        while True:
            now = time.time()
            result = _grafana(
                f"/api/datasources/proxy/uid/{datasource_uid}/loki/api/v1/query_range",
                {
                    "query": logql,
                    "start": int((now - 600) * 1_000_000_000),
                    "end": int(now * 1_000_000_000),
                    "limit": 100,
                },
            )
            streams = result["data"]["result"]
            if streams or time.time() >= deadline:
                return streams
            time.sleep(2)

    return _query


@pytest.fixture
def collector_stopped():
    """OTel Collector を停止した状態を作り、テスト後に復帰させる。"""
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "stop", "otel-collector"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    yield
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "start", "otel-collector"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_normal(emit_log, query_logs):
    """モニターのログを絞り込んで表示できることを確認する（正常系）。"""
    # 準備: 一意なマーカー付きの INFO ログを送出する
    marker = f"e2e-{uuid.uuid4().hex[:12]}"
    emit_log("monitor", f"ポーリングを開始しました: marker={marker}")
    # 実行: 発生元プロセスで絞り込んで検索する
    streams = query_logs(f'{{service_name="monitor"}} |= `{marker}`')
    # 検証: 発生時刻 / 発生元プロセス / レベル / メッセージが揃っている
    assert len(streams) == 1
    stream = streams[0]
    assert stream["stream"]["service_name"] == "monitor"
    assert stream["stream"]["service_namespace"] == "ai-monitor"
    assert stream["stream"]["level"] == "INFO"
    timestamp, line = stream["values"][0]
    assert int(timestamp) > 0
    entry = json.loads(line)
    assert entry["body"] == f"ポーリングを開始しました: marker={marker}"
    assert entry["severity"] == "INFO"
    assert entry["resources"]["deployment.environment"] == "dev"


def test_error_when_collector_down(collector_stopped, emit_log, query_logs):
    """Collector 停止中のログが蓄積されないことを確認する（異常系）。"""
    # 準備: Collector を停止した状態で INFO ログを送出する
    marker = f"e2e-{uuid.uuid4().hex[:12]}"
    emit_log("monitor", f"Collector 停止中のログ: marker={marker}")
    # 実行
    streams = query_logs(f'{{service_name="monitor"}} |= `{marker}`', timeout_sec=10)
    # 検証: 該当ログなし（UI 自体は応答している）
    assert streams == []


def test_error_when_no_match(query_logs):
    """条件に一致するログがない場合を確認する（異常系）。"""
    # 実行: 存在しない発生元プロセスで絞り込む
    streams = query_logs('{service_name="does-not-exist"}', timeout_sec=10)
    # 検証: 該当ログなし
    assert streams == []

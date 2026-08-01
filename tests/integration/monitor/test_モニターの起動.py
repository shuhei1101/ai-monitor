"""「モニターの起動」の結合テスト（実プロセスを起動して確認する）。

エージェントも GitHub も登場しないため、E2E ハーネスではなく実プロセスの起動 / 停止で検証する。
GitHub へは繋がないので、ポーリングは 1 周目で失敗しても待受とポート公開には影響しない。
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from ai_monitor.shared.settings import _AGENT_NAMES

REPO_ROOT = Path(__file__).resolve().parents[3]
WAIT_SEC = 40


def _settings_doc(port, state_path: Path) -> dict:
    """起動用の設定内容を組み立てる（監視対象なし = GitHub を叩かない）。"""
    return {
        "github_token": "github_pat_test",
        "ai_monitor_wiki_base": "https://example.com/ai-monitor-wiki",
        "port": port,
        "state_path": str(state_path),
        "agents": {name: {"model": "sonnet"} for name in _AGENT_NAMES},
        "projects": [],
        "watchdog": {"enabled": False},
    }


def _wait_until(predicate, *, timeout_sec: int = WAIT_SEC):
    """条件が真値を返すまで短い間隔で待つ。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.3)
    return None


def _listening(port: int) -> bool:
    """指定ポートへ接続できるかを返す。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(1)
    try:
        probe.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


@pytest.fixture
def launch(tmp_path):
    """設定を書き出してモニターを実プロセスとして起動する factory（終了時に停止する）。"""
    started: list[subprocess.Popen] = []

    def _launch(port, *, name: str = "run"):
        config_dir = tmp_path / name
        config_dir.mkdir(parents=True, exist_ok=True)
        data_dir = config_dir / "data"
        state_path = data_dir / "state.yaml"
        (config_dir / "settings.yaml").write_text(
            yaml.safe_dump(_settings_doc(port, state_path), allow_unicode=True), encoding="utf-8"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        env["XDG_CONFIG_HOME"] = str(config_dir)  # 参照されない環境向けの保険
        env.pop("AI_MONITOR_ENV", None)
        log = (config_dir / "monitor.out").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [
                sys.executable, "-c",
                # 設定の読み先を差し替え、外部疎通チェックは通ったことにする（検証対象は待受ポートの確定）
                "import logging, pathlib, sys;"
                "logging.basicConfig(level=logging.INFO, stream=sys.stdout);"
                "import ai_monitor.shared.settings as s;"
                f"s.CONFIG_DIR = pathlib.Path({str(config_dir)!r});"
                "import ai_monitor.main as m;"
                "m.check_dependencies = lambda *a, **k: [];"
                "sys.exit(m.main())",
            ],
            cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
        )
        started.append(proc)
        return proc, data_dir / "monitor.port", config_dir / "monitor.out"

    yield _launch
    for proc in started:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_normal(launch):
    """ポート自動確定と公開を実プロセスで確認する（正常系・ポート自動確定）。"""
    # 準備・実行: port=0 で起動する
    proc, port_path, _out = launch(0)
    # 検証: ポートファイルが書かれ、その番号で待受している
    assert _wait_until(lambda: port_path.exists() and port_path.read_text(encoding="utf-8").strip()), (
        "ポートファイルが作成されない"
    )
    port = int(port_path.read_text(encoding="utf-8").strip())
    assert port >= 1
    assert _wait_until(lambda: _listening(port)), f"確定ポート {port} で待受していない"
    assert proc.poll() is None, "プロセスが落ちている"


def test_normal_when_second_instance(launch):
    """2 本目を同時起動しても衝突しないことを確認する（正常系・2 本目の同時起動）。"""
    # 準備・実行: 別ディレクトリで 2 本とも port=0 で起動する
    proc1, port_path1, _o1 = launch(0, name="first")
    assert _wait_until(lambda: port_path1.exists() and port_path1.read_text(encoding="utf-8").strip())
    proc2, port_path2, _o2 = launch(0, name="second")
    assert _wait_until(lambda: port_path2.exists() and port_path2.read_text(encoding="utf-8").strip())
    # 検証: 別々のポートで両方が待受している
    port1 = int(port_path1.read_text(encoding="utf-8").strip())
    port2 = int(port_path2.read_text(encoding="utf-8").strip())
    assert port1 != port2, f"同じポートを取り合っている: {port1}"
    # ポートファイルの書き出しと待受開始にはラグがあるため、待受が始まるまで待つ
    assert _wait_until(lambda: _listening(port1)), f"1 本目が待受していない: {port1}"
    assert _wait_until(lambda: _listening(port2)), f"2 本目が待受していない: {port2}"
    assert proc1.poll() is None and proc2.poll() is None


def test_error_when_port_in_use(launch):
    """指定ポートが使用中のときに起動を中止することを確認する（異常シナリオ）。"""
    # 準備: 対象ポートを占有しておく
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    occupied = holder.getsockname()[1]
    try:
        # 実行: 占有済みポートを指定して起動する
        proc, port_path, out_path = launch(occupied)
        code = _wait_until(lambda: proc.poll() is not None and proc.poll())
        # 検証: 非 0 終了で、ポートファイルを作っていない
        assert code, f"非 0 終了になっていない: {proc.poll()}"
        assert not port_path.exists(), "起動失敗なのにポートファイルが作られている"
        log = out_path.read_text(encoding="utf-8")
        assert str(occupied) in log, f"ログに該当ポート番号が出ていない: {log[-500:]}"
    finally:
        holder.close()

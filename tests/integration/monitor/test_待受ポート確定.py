"""「待受ポート確定」の結合テスト。"""
from __future__ import annotations

import socket

import pytest

from ai_monitor.server.listen import bind_listen_socket


def _settings(port: int):
    """待受ポートだけを差し替えた実物の Settings を作る。"""
    from ai_monitor.shared.settings import _AGENT_NAMES, AgentSettings, Settings

    return Settings(
        github_token="github_pat_test",
        ai_monitor_wiki_base="https://example.com/ai-monitor-wiki",
        agents={name: AgentSettings(model="sonnet") for name in _AGENT_NAMES},
        projects=[],
        port=port,
    )


def _listening(port: int) -> bool:
    """指定ポートへ接続できるかを返す。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(2)
    try:
        probe.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def test_normal(tmp_path):
    """自動割り当てでの確定・書き戻し・公開を確認する（正常系）。"""
    # 準備
    settings = _settings(0)
    port_path = tmp_path / "monitor.port"
    # 実行
    sock = bind_listen_socket(settings, port_path)
    # 検証
    try:
        port = sock.getsockname()[1]
        assert port >= 1
        assert settings.port == port
        assert port_path.read_text(encoding="utf-8") == str(port)
        # 返ったソケットがそのまま listen できる状態にある
        sock.listen(1)
        assert _listening(port)
    finally:
        sock.close()


def test_normal_when_fixed_port(tmp_path):
    """指定ポートの尊重を確認する（正常系）。"""
    # 準備: 一度 bind して閉じ、空いている番号を得る
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    fixed = probe.getsockname()[1]
    probe.close()
    settings = _settings(fixed)
    port_path = tmp_path / "monitor.port"
    # 実行
    sock = bind_listen_socket(settings, port_path)
    # 検証
    try:
        assert sock.getsockname()[1] == fixed
        assert port_path.read_text(encoding="utf-8") == str(fixed)
    finally:
        sock.close()


def test_error_when_port_in_use(tmp_path):
    """使用中ポート指定時に状態を変えずに中止することを確認する（異常系）。"""
    # 準備: 対象ポートを占有しておく
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    occupied = holder.getsockname()[1]
    settings = _settings(occupied)
    port_path = tmp_path / "monitor.port"
    port_path.write_text("9999", encoding="utf-8")
    # 実行・検証
    try:
        with pytest.raises(OSError) as excinfo:
            bind_listen_socket(settings, port_path)
        assert excinfo.value.errno is not None
        assert settings.port == occupied
        assert port_path.read_text(encoding="utf-8") == "9999"
    finally:
        holder.close()

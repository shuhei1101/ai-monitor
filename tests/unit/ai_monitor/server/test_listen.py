"""`src/ai_monitor/server/listen.py` の単体テスト。"""
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


@pytest.fixture
def occupied_port():
    """使用中のポートを 1 つ払い出す（テスト終了まで占有し続ける）。"""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    yield holder.getsockname()[1]
    holder.close()


@pytest.fixture
def free_port():
    """空いているポート番号を 1 つ返す（払い出し後に解放する）。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_bind_listen_socket(tmp_path):
    """自動割り当てでの確定と公開を確認する（正常系）。"""
    # 準備
    settings = _settings(0)
    port_path = tmp_path / "monitor.port"
    # 実行
    sock = bind_listen_socket(settings, port_path)
    # 検証
    try:
        resolved = sock.getsockname()[1]
        assert resolved >= 1
        assert settings.port == resolved
        assert port_path.read_text(encoding="utf-8") == str(resolved)
    finally:
        sock.close()


def test_bind_listen_socket_when_fixed(tmp_path, free_port):
    """指定ポートの尊重を確認する（正常系）。"""
    # 準備
    settings = _settings(free_port)
    port_path = tmp_path / "monitor.port"
    # 実行
    sock = bind_listen_socket(settings, port_path)
    # 検証
    try:
        assert sock.getsockname()[1] == free_port
        assert settings.port == free_port
        assert port_path.read_text(encoding="utf-8") == str(free_port)
    finally:
        sock.close()


def test_bind_listen_socket_when_in_use(tmp_path, occupied_port):
    """使用中ポート指定時の中止を確認する（異常系）。"""
    # 準備
    settings = _settings(occupied_port)
    port_path = tmp_path / "monitor.port"
    port_path.write_text("9999", encoding="utf-8")
    # 実行・検証
    with pytest.raises(OSError):
        bind_listen_socket(settings, port_path)
    assert settings.port == occupied_port, "確定前の設定が書き換わっている"
    assert port_path.read_text(encoding="utf-8") == "9999", "公開ファイルが上書きされている"


def test_bind_listen_socket_when_dir_missing(tmp_path):
    """公開先の親ディレクトリが無いときの作成を確認する（正常系）。"""
    # 準備
    settings = _settings(0)
    port_path = tmp_path / "nested" / "dir" / "monitor.port"
    # 実行
    sock = bind_listen_socket(settings, port_path)
    # 検証
    try:
        assert port_path.exists()
        assert port_path.read_text(encoding="utf-8") == str(settings.port)
    finally:
        sock.close()

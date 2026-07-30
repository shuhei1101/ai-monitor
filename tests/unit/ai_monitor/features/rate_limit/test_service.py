"""`src/ai_monitor/features/rate_limit/service.py` の単体テスト。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

import ai_monitor.features.rate_limit.service as service
import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.features.agents.service import RESUME_TEXT
from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.features.sessions.types import AgentSession

JST = ZoneInfo("Asia/Tokyo")
SESSION = "ai-monitor-sandbox-1069-epic-conductor"
LIMIT_TEXT = "You've hit your session limit · resets 2:30am (Asia/Tokyo)"
OLD_SEEN_AT = "2026-07-20T00:00:00+09:00"


def _line(text: str, *, error: str = "rate_limit") -> str:
    """会話ログ 1 行分の JSON 文字列を組み立てる。"""
    return json.dumps({"error": error, "message": {"content": [{"text": text}]}})


@pytest.fixture
def tmp_transcript(tmp_path):
    """一時ファイルに会話ログ（jsonl）を書いてパスを返す factory。"""

    def _create(lines: list[str]):
        path = tmp_path / "transcript.jsonl"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    return _create


@pytest.fixture
def tmux_mocks(monkeypatch):
    """tmux 操作を MagicMock に差し替える。"""
    mocks = MagicMock()
    mocks.has_session.return_value = True
    monkeypatch.setattr(service, "has_session", mocks.has_session)
    monkeypatch.setattr(service, "send_keys", mocks.send_keys)
    return mocks


@pytest.fixture
def registry(tmp_state_path, monkeypatch):
    """生存時刻の更新先となる台帳を返す（永続化はしない）。"""
    monkeypatch.setattr(registry_mod, "save_sessions", MagicMock())
    registry = registry_mod.SessionRegistry(tmp_state_path)
    registry.register(
        AgentSession(
            session_name=SESSION,
            project="sandbox",
            agent_name="epic-conductor",
            primary_number=1069,
            last_seen_at=OLD_SEEN_AT,
        )
    )
    return registry


def test_resolve_reset_at(tmp_transcript):
    """時刻の解決を確認する（正常系）。"""
    # 準備
    path = tmp_transcript([_line(LIMIT_TEXT)])
    now = datetime(2026, 7, 29, 1, 0, tzinfo=JST)
    # 実行
    resets_at = service.resolve_reset_at(path, now)
    # 検証
    assert resets_at == datetime(2026, 7, 29, 2, 30, tzinfo=JST)


def test_resolve_reset_at_when_next_day(tmp_transcript):
    """翌日への補完を確認する（正常系）。"""
    # 準備: 現在時刻がリセット時刻より後
    path = tmp_transcript([_line(LIMIT_TEXT)])
    now = datetime(2026, 7, 29, 3, 0, tzinfo=JST)
    # 実行
    resets_at = service.resolve_reset_at(path, now)
    # 検証
    assert resets_at == datetime(2026, 7, 30, 2, 30, tzinfo=JST)


def test_resolve_reset_at_when_no_record(tmp_transcript):
    """到達レコード不在を確認する（正常系）。"""
    # 準備
    path = tmp_transcript([_line("通常の応答", error="")])
    # 実行
    resets_at = service.resolve_reset_at(path, datetime(2026, 7, 29, 1, 0, tzinfo=JST))
    # 検証
    assert resets_at is None


def test_resolve_reset_at_when_unparsable(tmp_transcript, caplog):
    """書式不一致を確認する（正常系）。"""
    # 準備
    path = tmp_transcript([_line("You've hit your session limit")])
    # 実行
    with caplog.at_level(logging.WARNING):
        resets_at = service.resolve_reset_at(path, datetime(2026, 7, 29, 1, 0, tzinfo=JST))
    # 検証: 既定の待機時間へ切り替える経路
    assert resets_at is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_resolve_reset_at_when_missing_file(tmp_path):
    """会話ログ不在を確認する（異常系）。"""
    # 実行・検証: 例外表「会話ログが存在しない」に対応
    with pytest.raises(FileNotFoundError):
        service.resolve_reset_at(tmp_path / "absent.jsonl", datetime(2026, 7, 29, 1, 0, tzinfo=JST))


def test_find_latest_record(tmp_transcript):
    """最新レコードの取得を確認する（正常系）。"""
    # 準備: 到達レコードが 2 件
    path = tmp_transcript([_line("resets 1:00am (Asia/Tokyo)"), _line(LIMIT_TEXT)])
    # 実行
    record = service._find_latest_record(path)
    # 検証: 後ろのレコードを返す
    assert record["message"]["content"][0]["text"] == LIMIT_TEXT


def test_find_latest_record_when_absent(tmp_transcript):
    """到達レコード不在を確認する（正常系）。"""
    # 準備
    path = tmp_transcript([_line("通常の応答", error="")])
    # 実行
    record = service._find_latest_record(path)
    # 検証
    assert record is None


def test_find_latest_record_when_broken_line(tmp_transcript):
    """壊れた行の読み飛ばしを確認する（正常系）。"""
    # 準備: 末尾に書き込み途中の行がある
    path = tmp_transcript([_line(LIMIT_TEXT), '{"error": "rate_li'])
    # 実行
    record = service._find_latest_record(path)
    # 検証: その手前のレコードを返す
    assert record["message"]["content"][0]["text"] == LIMIT_TEXT


def test_resume_blocked_sessions(tmux_mocks, registry):
    """解除後の再開送信を確認する（正常系）。"""
    # 準備
    gate = RateLimitGate()
    now = datetime.now(timezone.utc).astimezone()
    gate.block(SESSION, now - timedelta(minutes=1))
    # 実行
    resumed = service.resume_blocked_sessions(gate, registry=registry, now=now)
    # 検証: 応答と定型文が順に送られ、生存時刻が更新される
    assert resumed == [SESSION]
    assert [c.args for c in tmux_mocks.send_keys.call_args_list] == [
        (SESSION, "Enter"),
        (SESSION, RESUME_TEXT),
    ]
    assert registry.sessions[0].last_seen_at != OLD_SEEN_AT


def test_resume_blocked_sessions_when_blocked(tmux_mocks, registry):
    """待機中は送らないことを確認する（正常系）。"""
    # 準備
    gate = RateLimitGate()
    now = datetime.now(timezone.utc).astimezone()
    gate.block(SESSION, now + timedelta(minutes=30))
    # 実行
    resumed = service.resume_blocked_sessions(gate, registry=registry, now=now)
    # 検証
    assert resumed == []
    tmux_mocks.send_keys.assert_not_called()


def test_resume_blocked_sessions_when_session_gone(tmux_mocks, registry):
    """実体消失の読み飛ばしを確認する（正常系）。"""
    # 準備: 解放済みセッション
    tmux_mocks.has_session.return_value = False
    gate = RateLimitGate()
    now = datetime.now(timezone.utc).astimezone()
    gate.block(SESSION, now - timedelta(minutes=1))
    # 実行
    resumed = service.resume_blocked_sessions(gate, registry=registry, now=now)
    # 検証: 送信も生存時刻の更新も行わない
    assert resumed == []
    tmux_mocks.send_keys.assert_not_called()
    assert registry.sessions[0].last_seen_at == OLD_SEEN_AT

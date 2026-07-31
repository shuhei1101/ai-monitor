"""「レートリミット通知」の結合テスト。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import ai_monitor.server.app as app_mod
from ai_monitor.main import build_agents

JST = ZoneInfo("Asia/Tokyo")
LIMIT_TEXT = "You've hit your session limit · resets 2:30am (Asia/Tokyo)"


def _line(text: str) -> str:
    """会話ログ 1 行分の到達レコードを組み立てる。"""
    return json.dumps({"error": "rate_limit", "message": {"content": [{"text": text}]}})


@pytest.fixture
def transcript(tmp_path):
    """一時ファイルに会話ログ（jsonl）を書いてパスを返す factory。"""

    def _create(text: str) -> str:
        path = tmp_path / "transcript.jsonl"
        path.write_text(_line(text), encoding="utf-8")
        return str(path)

    return _create


@pytest.fixture
def gate_box(monkeypatch) -> list:
    """アプリが生成した関門を取り出せるように生成を記録する。"""
    created: list = []
    original = app_mod.RateLimitGate

    def factory():
        gate = original()
        created.append(gate)
        return gate

    monkeypatch.setattr(app_mod, "RateLimitGate", factory)
    return created


@pytest.fixture
def client(mon_settings, mon_registry, label_settings, agent_settings, monkeypatch, gate_box):
    """到達通知を受けるアプリのテストクライアントを返す。"""
    import ai_monitor.main as main_mod

    # lifespan が起動するポーリングループを空回しにする
    monkeypatch.setattr(
        main_mod, "run_cycle", lambda *args, **kwargs: ({}, "1970-01-01T00:00:00+00:00")
    )
    agents = build_agents(label_settings, agent_settings=agent_settings)
    app = app_mod.create_app(mon_settings, registry=mon_registry, agents=agents, label_settings=label_settings)
    with TestClient(app, base_url="http://localhost:8765") as client:
        yield client


def test_normal(client, gate_box, transcript, session_factory):
    """会話ログから読んだ時刻での待機開始を確認する（正常系）。"""
    # 準備
    session = session_factory("epic-conductor", 1069)
    # 実行
    response = client.post(
        "/rate_limit",
        json={
            "project": "sandbox",
            "agent_name": "epic-conductor",
            "number": 1069,
            "transcript_path": transcript(LIMIT_TEXT),
        },
    )
    # 検証: 会話ログのリセット時刻が解除時刻になっている
    assert response.status_code == 200
    resets_at = datetime.fromisoformat(response.json()["resets_at"])
    assert resets_at.astimezone(JST).strftime("%H:%M") == "02:30"
    assert resets_at > datetime.now(timezone.utc)
    # 検証: 対象セッションが再開待ちとして記録されている
    assert gate_box[0].take_resumable(resets_at + timedelta(seconds=1)) == [session.session_name]


def test_normal_when_unparsable(client, gate_box, transcript, session_factory, mon_settings, caplog):
    """時刻を読めない場合の既定の待機時間を確認する（正常系）。"""
    # 準備
    session = session_factory("epic-conductor", 1069)
    before = datetime.now(timezone.utc)
    # 実行
    with caplog.at_level(logging.WARNING):
        response = client.post(
            "/rate_limit",
            json={
                "project": "sandbox",
                "agent_name": "epic-conductor",
                "number": 1069,
                "transcript_path": transcript("You've hit your session limit"),
            },
        )
    # 検証: 受信時刻 + rate_limit_fallback_min が解除時刻になっている
    assert response.status_code == 200
    resets_at = datetime.fromisoformat(response.json()["resets_at"])
    fallback = timedelta(minutes=mon_settings.rate_limit_fallback_min)
    assert before + fallback <= resets_at <= datetime.now(timezone.utc) + fallback
    # 検証: 解析できなかったことが警告ログに残り、対象は再開待ちになっている
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert gate_box[0].take_resumable(resets_at + timedelta(seconds=1)) == [session.session_name]


def test_error_when_session_missing(client, gate_box, transcript):
    """台帳に無いセッションからの通知を拒否する（異常系）。"""
    # 実行
    response = client.post(
        "/rate_limit",
        json={
            "project": "sandbox",
            "agent_name": "epic-conductor",
            "number": 999,
            "transcript_path": transcript(LIMIT_TEXT),
        },
    )
    # 検証: 404 が返り待機が開始されていない
    assert response.status_code == 404
    assert gate_box[0].take_resumable(datetime.now(timezone.utc) + timedelta(days=1)) == []

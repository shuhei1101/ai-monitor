"""「レートリミット時の待機と再開」の E2E テスト。

上限への到達は Claude Code の `StopFailure` フックが検知する。
本テストは実際に枠を使い切る代わりに、そのフックスクリプトを Claude Code と同じ入力
（`transcript_path` + `AI_MONITOR_*` 環境変数）で起動して到達を再現する。

待機はアカウント単位でモニター全体に効くため、本テストの実行中は他の E2E の
セッション起動も止まる。並列実行するときは待機時間ぶんの余裕を見込む。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = REPO_ROOT / "plugins" / "ai-monitor" / "hooks" / "stop-failure" / "notify_rate_limit.py"
JST = ZoneInfo("Asia/Tokyo")

INTAKE_TITLE = "タスクの並び替え機能"
INTAKE_BODY = """タスク一覧をドラッグで並び替えられるようにしたいです。

- 並び順はユーザーごとに保持したい
- 並び替えの結果は再訪時にも残っていてほしい
"""
EPIC_TITLE = "タスクの並び替え機能"

FEEDBACK = """横断要件に「並び順の更新は 1 リクエストで完結すること」を追記してください。
"""
FEEDBACK_MARKER = "1 リクエストで完結"

# 待機が効いていることを確かめるための観察時間（ポーリング周期 15 秒の 3 周期ぶん）
BLOCKED_OBSERVE_SEC = 45


def _session_name(state_path: Path, epic_number: int) -> str | None:
    """モニター台帳から epic-conductor のセッション名を返す。"""
    if not state_path.exists():
        return None
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        if entry["agent_name"] == "epic-conductor" and entry["primary_number"] == epic_number:
            return entry["session_name"]
    return None


def _tmux_sessions() -> set[str]:
    """起動中の tmux セッション名の集合を返す。"""
    listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
    return set(listed.stdout.split())


def _session_created_at(session_name: str) -> str:
    """tmux セッションの作成時刻（epoch 秒）を返す。"""
    created = subprocess.run(
        ["tmux", "display-message", "-p", "-t", session_name, "#{session_created}"],
        capture_output=True, text=True, check=True,
    )
    return created.stdout.strip()


def _write_transcript(path: Path, resets_at: datetime) -> None:
    """上限到達のレコードを持つ会話ログを書き出す。"""
    hour12 = resets_at.hour % 12 or 12
    ampm = "am" if resets_at.hour < 12 else "pm"
    text = (
        f"You've hit your session limit · resets {hour12}:{resets_at.minute:02d}{ampm} (Asia/Tokyo)"
    )
    record = {"error": "rate_limit", "message": {"content": [{"text": text}]}}
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _fire_hook(transcript: Path, *, project: str, agent_name: str, number: int, port: int):
    """StopFailure フックを Claude Code と同じ入力で起動する。"""
    env = os.environ | {
        "AI_MONITOR_PROJECT": project,
        "AI_MONITOR_AGENT": agent_name,
        "AI_MONITOR_NUMBER": str(number),
        "AI_MONITOR_PORT": str(port),
    }
    payload = {
        "hook_event_name": "StopFailure",
        "error_type": "rate_limit",
        "transcript_path": str(transcript),
    }
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload), env=env, capture_output=True, text=True, check=False,
    )


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path, e2e_settings_path,
    sandbox, tmp_path,
):
    """上限到達での待機とリセット後の自動再開を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    port = yaml.safe_load(e2e_settings_path.read_text(encoding="utf-8")).get("port", 8765)

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    def _labels(number) -> set[str]:
        return {label.name for label in _get(number).labels}

    # 準備: 本文空 + 確認:epic-conductor の epic Issue（親 intake 付き）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 要件確定（初回）の完了を待つ（議論中 + assignee=ユーザー の待機状態）
    def _first_turn_done():
        data = _get(epic.number)
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    data = wait_until(
        _first_turn_done, timeout_sec=1200, message="要件確定（初回）の完了（議論中 + assignee）"
    )
    session_name = _session_name(e2e_state_path, epic.number)
    assert session_name, "台帳に epic-conductor のセッションがない"
    created_at = _session_created_at(session_name)
    sessions_before = _tmux_sessions()

    # 実行: 上限への到達を通知する（リセット時刻は 2 分後 = 分の切り捨てで 60〜120 秒後）
    transcript = tmp_path / "rate_limit.jsonl"
    _write_transcript(transcript, datetime.now(JST) + timedelta(minutes=2))
    result = _fire_hook(
        transcript, project=sandbox["name"], agent_name="epic-conductor",
        number=epic.number, port=port,
    )

    # 検証: モニターが到達通知を受理している
    assert result.returncode == 0, f"到達通知が受理されていない: {result.stderr}"

    # 実行: 待機中に起動条件を満たす（フィードバック + assignee 外し）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic.number, body=FEEDBACK
    )
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=epic.number, assignees=[assignee.login]
        )

    # 検証: 待機中は起動しない（処理中ラベルが付かず tmux セッションも増えない）
    time.sleep(BLOCKED_OBSERVE_SEC)
    assert "処理中:epic-conductor" not in _labels(epic.number), "待機中にエージェントへ送信している"
    assert _tmux_sessions() == sessions_before, "待機中に新しい tmux セッションが作成されている"

    # 検証: リセット到達後に再開して応答ループが完了する（assignee 再設定）
    def _reply_turn_done():
        data = _get(epic.number)
        return data if data.assignees else None

    data = wait_until(
        _reply_turn_done, timeout_sec=1200, message="再開後の応答ループの完了（assignee 再設定）"
    )

    # 検証: 同じセッションのまま再開している（kill されていない）
    assert session_name in _tmux_sessions(), "再開時にセッションが解放されている"
    assert _session_created_at(session_name) == created_at, "セッションが作り直されている"

    # 検証: 中断した手順の続きが実行されている（フィードバックが本文に反映されている）
    body = (data.body or "").replace("\r\n", "\n")
    assert FEEDBACK_MARKER in body, "再開後のターンでフィードバックが本文に反映されていない"


def test_error_when_session_released(monitor, e2e_settings_path, sandbox, tmp_path):
    """解放済みセッションからの到達通知を拒否することを実環境で確認する（異常系）。"""
    # 準備: 台帳に無い番号（epic 完了などで解放された後を再現）
    port = yaml.safe_load(e2e_settings_path.read_text(encoding="utf-8")).get("port", 8765)
    transcript = tmp_path / "rate_limit.jsonl"
    _write_transcript(transcript, datetime.now(JST) + timedelta(minutes=2))
    # 実行
    result = _fire_hook(
        transcript, project=sandbox["name"], agent_name="epic-conductor", number=999999, port=port,
    )
    # 検証: 404 で拒否されている
    assert result.returncode != 0, "台帳に無いセッションからの通知が受理されている"
    assert "404" in result.stderr, f"404 以外で失敗している: {result.stderr}"
    # 検証: モニターが落ちていない（待受ポートが開いたまま）
    time.sleep(1)
    socket.create_connection(("127.0.0.1", port), timeout=5).close()

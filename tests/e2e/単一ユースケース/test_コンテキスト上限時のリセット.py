"""「コンテキスト上限時のリセット」の E2E テスト。"""
from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

INTAKE_TITLE = "タスクの並び替え機能"
INTAKE_BODY = """タスク一覧をドラッグで並び替えられるようにしたいです。

- 並び順はユーザーごとに保持したい
- 並び替えの結果は再訪時にも残っていてほしい
"""
EPIC_TITLE = "タスクの並び替え機能"

FEEDBACK = """横断要件に「並び順の更新は 1 リクエストで完結すること」を追記してください。
"""
FEEDBACK_MARKER = "1 リクエストで完結"


def _session_name(state_path: Path, epic_number: int) -> str | None:
    """モニター台帳から epic-conductor セッション名を返す。"""
    if not state_path.exists():
        return None
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        if entry["agent_name"] == "epic-conductor" and entry["primary_number"] == epic_number:
            return entry["session_name"]
    return None


def _count_compact_boundaries() -> int:
    """sandbox の全会話ログに含まれるコンパクト境界レコードの総数を返す。"""
    # 過去実行のログにも境界が残るため、実行前後の差分で判定する
    root = Path.home() / ".claude" / "projects"
    return sum(
        path.read_text(encoding="utf-8", errors="ignore").count("compact_boundary")
        for path in root.glob("*ai-monitor-e2e*/*.jsonl")
    )


def _post_context_reset(port: int, project: str, agent_name: str, number: int) -> int:
    """モニターへリセット要求を送り、ステータスコードを返す。"""
    body = json.dumps({"project": project, "agent_name": agent_name, "number": number}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/context_reset",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_normal(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, tmp_path):
    """コンパクトをブロックしてリセットし、手順どおりに応答することを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

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

    # 実行: 稼働中セッションへ /compact を送って PreCompact を発火させる
    session_name = _session_name(tmp_path / "state.yaml", epic.number)
    assert session_name, "台帳に epic-conductor のセッションがない"
    boundaries_before = _count_compact_boundaries()
    subprocess.run(["tmux", "send-keys", "-t", session_name, "/compact", "Enter"], check=True)

    # フックのブロックとモニターの 中断 → /clear → ドキュメント送信を待つ
    def _document_resent():
        pane = subprocess.run(
            ["tmux", "capture-pane", "-p", "-S", "-3000", "-t", session_name],
            capture_output=True, text=True, check=True,
        ).stdout
        return pane if "## 参考資料" in pane else None

    pane = wait_until(
        _document_resent, timeout_sec=300, message="リセット後のエージェントドキュメント送信"
    )

    # 検証: 送信内容にフェーズ本文・参考資料の見出しが含まれている
    assert "## フェーズ" in pane, "送信内容にフェーズ見出しがない"
    assert "## 参考資料" in pane, "送信内容に参考資料見出しがない"

    # 検証: 中断で入力欄に戻った /compact が後続の送信文に連結されていない
    assert "/compact /clear" not in pane, "入力欄がクリアされずコマンドが連結されている"

    # 検証: コンパクトが行われていない（会話履歴に要約の境界が増えていない）
    assert _count_compact_boundaries() == boundaries_before, "コンパクトがブロックされていない"

    # 検証: 議論中 が保持されたまま（リセットが承認扱いにならない）
    labels = {label.name for label in _get(epic.number).labels}
    assert "議論中" in labels, "リセットで 議論中 が失われている"

    # 実行: リセット後にフィードバックを返す（コメント + assignee 外し）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic.number, body=FEEDBACK
    )
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=epic.number, assignees=[assignee.login]
        )

    # 応答ループの完了を待つ（assignee 再設定）
    def _reply_turn_done():
        data = _get(epic.number)
        return data if data.assignees else None

    data = wait_until(
        _reply_turn_done, timeout_sec=1200, message="リセット後の応答ループの完了（assignee 再設定）"
    )

    # 検証: 手順どおりにフィードバックが本文へ反映されている
    body = (data.body or "").replace("\r\n", "\n")
    assert FEEDBACK_MARKER in body, "フィードバックが本文に反映されていない"
    # 検証: 議論中 は保持されたまま再待機に入っている
    labels = {label.name for label in _get(epic.number).labels}
    assert "議論中" in labels, "応答ループで 議論中 が失われている"


def test_error_when_session_released(monitor, e2e_settings_path, sandbox):
    """解放済みセッションからのリセット要求を拒否することを実環境で確認する（異常系）。"""
    # 準備: 台帳に無いエージェント名 + 番号（epic 完了などで解放された後を再現）
    port = yaml.safe_load(e2e_settings_path.read_text(encoding="utf-8")).get("port", 8765)
    socket.create_connection(("127.0.0.1", port), timeout=5).close()
    # 実行
    status = _post_context_reset(port, sandbox["name"], "epic-conductor", 999999)
    # 検証: 404 が返り、モニターが落ちていない
    assert status == 404
    time.sleep(1)
    assert monitor.poll() is None, "モニターが落ちている"

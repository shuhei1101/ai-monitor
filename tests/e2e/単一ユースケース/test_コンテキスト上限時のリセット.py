"""「コンテキスト上限時のリセット」の E2E テスト。"""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import yaml

INTAKE_TITLE = "タスク並び替え機能"
INTAKE_BODY = "タスク一覧をドラッグで並び替えられるようにする。"

EPIC_TITLE = "タスク並び替え機能"
EPIC_BODY = """## 前提条件

なし

## 概要

タスク一覧の表示順をユーザーが任意に並び替えられるようにする。

## 背景

現状は作成日時の固定順で、優先度の高いタスクを上に置けない。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| タスク並び替え | 一覧をドラッグして表示順を保存する | 起票済み |

## 横断要件

- 並び順はユーザーごとに保持する
"""

STORY_TITLE = "タスク並び替え"
STORY_BODY_TEMPLATE = """## 前提条件

なし

## 概要

ユーザーが一覧をドラッグして表示順を保存する。

## 背景

親 epic #{epic_number} の UC「タスク並び替え」に対応。

## ユースケース要件

| 要件 | 補足 |
| --- | --- |
| 一覧をドラッグして並び替えられる | - |
| 並び順が保存され再訪時に復元される | - |

## 実装分担

| 順序 | 対象システム | 担当範囲 | 子 subsystem |
| --- | --- | --- | --- |
| 1 | バックエンド | 並び順の保存 API | 起票済み |
| 2 | フロントエンド | ドラッグ操作と保存導線 | 未起票 |
"""

SUBSYSTEM_TITLE = "タスク並び替え バックエンド"

FEEDBACK = """非機能要件に「並び順の更新は 1 リクエストで完結すること」を追記してください。
"""
FEEDBACK_MARKER = "1 リクエストで完結"


def _count_compact_boundaries() -> int:
    """sandbox の全会話ログに含まれるコンパクト境界レコードの総数を返す。"""
    # 過去実行のログにも境界が残るため、実行前後の差分で判定する
    root = Path.home() / ".claude" / "projects"
    return sum(
        path.read_text(encoding="utf-8", errors="ignore").count("compact_boundary")
        for path in root.glob("*ai-monitor-e2e*/*.jsonl")
    )


def _session_name(state_path, subsystem_number: int) -> str | None:
    """モニター台帳から subsystem-conductor セッション名を返す。"""
    if not state_path.exists():
        return None
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        if entry["agent_name"] == "subsystem-conductor" and entry["primary_number"] == subsystem_number:
            return entry["session_name"]
    return None


def _post_context_reset(port: int, project: str, agent_name: str, number: int) -> int:
    """モニターへリセット要求を送り、ステータスコードを返す。"""
    import json
    import urllib.error
    import urllib.request

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


def test_normal(
    monitor,
    gh_live,
    repo_ctx,
    sandbox,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    subsystem_issue_factory,
    wait_until,
    tmp_path,
):
    """コンパクトをブロックしてリセットし、手順どおりに応答することを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: epic / story / subsystem の一式（subsystem-conductor が待機に入る状態を作る）
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY,
        epic_labels=["layer:epic", "type:feat"],
    )
    epic_branch = f"feat/epic/task-sort-{epic.number}"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number), labels=["layer:story"],
    )
    story_branch = f"feat/story/task-sort-{story.number}"
    draft_pr_factory(
        story_branch, STORY_TITLE, f"## 紐づく Issue\n\n- #{story.number}\n", base_branch=epic_branch
    )
    subsystem = subsystem_issue_factory(story.number, SUBSYSTEM_TITLE)

    # 要件確定（初回）の完了を待つ（議論中 + assignee=ユーザー の待機状態）
    def _first_turn_done():
        data = _get(subsystem.number)
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    data = wait_until(
        _first_turn_done, timeout_sec=1800, message="要件確定（初回）の完了（議論中 + assignee）"
    )

    # 実行: 稼働中セッションへ /compact を送って PreCompact を発火させる
    session_name = _session_name(tmp_path / "state.yaml", subsystem.number)
    assert session_name, "台帳に subsystem-conductor のセッションがない"
    boundaries_before = _count_compact_boundaries()
    subprocess.run(["tmux", "send-keys", "-t", session_name, "/compact", "Enter"], check=True)

    # フックのブロックとモニターの /clear + ドキュメント送信を待つ
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

    # 検証: コンパクトが行われていない（会話履歴に要約の境界が増えていない）
    assert _count_compact_boundaries() == boundaries_before, "コンパクトがブロックされていない"

    # 検証: 議論中 が保持されたまま（リセットが承認扱いにならない）
    labels = {label.name for label in _get(subsystem.number).labels}
    assert "議論中" in labels, "リセットで 議論中 が失われている"

    # 実行: コンパクト後にフィードバックを返す（コメント + assignee 外し）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=subsystem.number, body=FEEDBACK
    )
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=subsystem.number, assignees=[assignee.login]
        )

    # 応答ループの完了を待つ（assignee 再設定）
    def _reply_turn_done():
        data = _get(subsystem.number)
        return data if data.assignees else None

    data = wait_until(
        _reply_turn_done, timeout_sec=1800, message="リセット後の応答ループの完了（assignee 再設定）"
    )

    # 検証: 手順どおりにフィードバックが本文へ反映されている
    body = (data.body or "").replace("\r\n", "\n")
    assert FEEDBACK_MARKER in body, "フィードバックが本文に反映されていない"
    # 検証: 議論中 は保持されたまま再待機に入っている
    labels = {label.name for label in _get(subsystem.number).labels}
    assert "議論中" in labels, "応答ループで 議論中 が失われている"


def test_error_when_session_released(monitor, e2e_settings_path, sandbox):
    """解放済みセッションからのリセット要求を拒否することを実環境で確認する（異常系）。"""
    # 準備: 台帳に無いエージェント名 + 番号（epic 完了などで解放された後を再現）
    port = yaml.safe_load(e2e_settings_path.read_text(encoding="utf-8")).get("port", 8765)
    socket.create_connection(("127.0.0.1", port), timeout=5).close()
    # 実行
    status = _post_context_reset(port, sandbox["name"], "subsystem-conductor", 999999)
    # 検証: 404 が返り、モニターが落ちていない
    assert status == 404
    time.sleep(1)
    assert monitor.poll() is None, "モニターが落ちている"

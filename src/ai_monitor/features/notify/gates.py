"""ユーザー確認ゲートの開通検知と重複しない通知。"""
from __future__ import annotations

import logging
from typing import Protocol

from ai_monitor.features.notify.types import NotifyFn
from ai_monitor.features.sessions.types import AgentSession

logger = logging.getLogger(__name__)


class _Gateable(Protocol):
    """ゲート判定に使う監視対象の最小形。"""

    number: int
    labels: list[str]
    assignees: list[str]


def notify_open_gates(
    targets: list[_Gateable],
    sessions: list[AgentSession],
    *,
    discussion_label: str,
    notify: NotifyFn,
) -> None:
    """ユーザーの番になった対象を、セッションごとに 1 度だけ通知する。

    ゲートは開いたまま毎周期観測されるため、通知済みの番号を台帳に持って重複を防ぐ。
    ゲートが閉じたら記録を落とし、次に開いたときは再び通知する。
    """
    # 議論中 + assignee が揃った対象がユーザーの番
    open_numbers = {
        t.number for t in targets if discussion_label in t.labels and t.assignees
    }
    for session in sessions:
        watched = {session.primary_number, *session.watch_numbers}
        # 閉じたゲートの記録を落とす（次に開いたときに再通知できるようにする）
        session.notified_gates = [n for n in session.notified_gates if n in open_numbers]
        # 自セッションの監視面のうち、まだ通知していない番号を送る
        for number in sorted(watched & open_numbers - set(session.notified_gates)):
            notify(
                "user_gate",
                f"#{number} がユーザーの確認待ちになりました",
                f"担当: {session.agent_name}\n対象: #{number}",
            )
            session.notified_gates.append(number)
            logger.info(
                "ユーザー確認ゲートを通知しました: project=%s agent_name=%s number=%s",
                session.project,
                session.agent_name,
                number,
            )

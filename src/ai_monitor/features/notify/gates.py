"""ユーザー確認ゲートの開通検知と重複しない通知。"""
from __future__ import annotations

import logging
from typing import Protocol

from ai_monitor.features.notify.types import NotifyFn

logger = logging.getLogger(__name__)

# 確認ラベルが付いていない面の担当表示
_UNASSIGNED = "未割当"


class _Gateable(Protocol):
    """ゲート判定に使う監視対象の最小形。"""

    number: int
    labels: list[str]
    assignees: list[str]


def notify_open_gates(
    targets: list[_Gateable],
    *,
    notified: set[int],
    project: str,
    discussion_label: str,
    confirm_prefix: str,
    repo: str,
    notify: NotifyFn,
) -> None:
    """ユーザーの番になった対象を、プロジェクトごとに 1 度だけ通知する。

    ゲートは開いたまま毎周期観測されるため、通知済みの番号を持って重複を防ぐ。
    1 つの面を複数セッションが監視面に持つため、記録はセッションではなくプロジェクト単位で持つ。
    ゲートが閉じたら記録を落とし、次に開いたときは再び通知する。
    """
    # 議論中 + assignee が揃った対象がユーザーの番
    open_targets = {t.number: t for t in targets if discussion_label in t.labels and t.assignees}
    # 閉じたゲートの記録を落とす（次に開いたときに再通知できるようにする）
    notified.intersection_update(open_targets)
    # まだ通知していない番号を送る
    for number in sorted(open_targets.keys() - notified):
        agent_name = _confirm_agent(open_targets[number], confirm_prefix)
        # 受け取った側が対象へ直接飛べるよう、リポジトリと番号も渡す
        notify(
            "user_gate",
            f"#{number} がユーザーの確認待ちになりました",
            f"担当: {agent_name}",
            repo=repo,
            number=number,
        )
        notified.add(number)
        logger.info(
            "ユーザー確認ゲートを通知しました: project=%s agent_name=%s number=%s",
            project,
            agent_name,
            number,
        )


def _confirm_agent(target: _Gateable, confirm_prefix: str) -> str:
    """面の確認ラベルから手番を持つ担当名を求める。"""
    # 手番の持ち主は面に付いた 確認:* が示す（規約上 1 面 1 件だが、増えていたら全部見せる）
    names = [
        label.removeprefix(confirm_prefix)
        for label in target.labels
        if label.startswith(confirm_prefix)
    ]
    return " / ".join(names) if names else _UNASSIGNED

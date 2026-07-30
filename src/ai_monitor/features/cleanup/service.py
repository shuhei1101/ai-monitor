"""周期の検知 4 種（intake 自動クローズ・一括解放・個別解放・タイムアウト回収）。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from githubkit.exception import RequestFailed

from ai_monitor.features.agents.types import Agent
from ai_monitor.features.notify.types import NotifyFn
from ai_monitor.integrations.github.issues import (
    close_issue,
    get_issue,
    get_parent_number,
    list_sub_issue_numbers,
)
from ai_monitor.integrations.github.labels import remove_label
from ai_monitor.integrations.tmux.ops import has_session, kill_session
from ai_monitor.shared.settings import MonitoredProject
from ai_monitor.shared.types import Issue, MonitorTarget, PullRequest

if TYPE_CHECKING:
    from ai_monitor.features.rate_limit.gate import RateLimitGate
    from ai_monitor.features.sessions.registry import SessionRegistry

logger = logging.getLogger(__name__)

def close_completed_intakes(
    project: MonitoredProject, targets: list[MonitorTarget], *, intake_label: str
) -> None:
    """全 Sub-issue closed の intake Issue をクローズする。"""
    for target in targets:
        if not isinstance(target, Issue) or intake_label not in target.labels:
            continue
        # total > 0 かつ completed == total のものをクローズする
        if target.sub_issues_total > 0 and target.sub_issues_completed == target.sub_issues_total:
            close_issue(project, target.number)
            logger.info(
                "intake Issue をクローズしました: project=%s number=%s sub_issues=%s",
                project.name,
                target.number,
                target.sub_issues_total,
            )


def release_closed_roots(
    project: MonitoredProject,
    targets: list[MonitorTarget],
    prev_targets: list[MonitorTarget],
    *,
    registry: SessionRegistry,
    intake_label: str,
    confirm_prefix: str,
    notify: NotifyFn,
) -> None:
    """前周期との差分で最上位 Issue のクローズを検知し、配下の全セッションを一括解放する。"""
    open_numbers = {t.number for t in targets}
    for closed in prev_targets:
        # 前周期に居て今周期に居ない Issue をクローズ候補にする
        if not isinstance(closed, Issue) or closed.number in open_numbers:
            continue
        # 単体取得で closed を確認する（open は一覧の取りこぼし）
        if get_issue(project, closed.number).state != "closed":
            logger.debug(
                "一覧から消えましたが open のため見送ります: project=%s number=%s",
                project.name,
                closed.number,
            )
            continue
        # 上位レイヤーが残っている Issue は解放しない（最上位の close まで配下を常駐させる）
        if not _is_root(project, closed.number, intake_label=intake_label):
            logger.info(
                "上位レイヤーが残っているため解放を見送ります: project=%s number=%s",
                project.name,
                closed.number,
            )
            continue
        logger.info("最上位 Issue のクローズを検知しました: project=%s number=%s", project.name, closed.number)
        family = _collect_family_numbers(project, closed.number)
        family_set = set(family)
        # 配下の Issue / 紐づく PR に 確認:* が残っていれば解放しない（次周期で再判定）
        remaining = None
        for candidate in targets:
            related = candidate.number in family_set or (
                isinstance(candidate, PullRequest)
                and any(n in family_set for n in candidate.linked_issue_numbers)
            )
            if related and any(label.startswith(confirm_prefix) for label in candidate.labels):
                remaining = candidate.number
                break
        if remaining is not None:
            logger.info(
                "確認ラベルが残っているため解放を見送ります: project=%s number=%s remaining=%s",
                project.name,
                closed.number,
                remaining,
            )
            continue
        # 配下番号の全セッションを台帳から解放して kill する
        released = []
        for number in family:
            for session in registry.release_by_number(project.name, number):
                kill_session(session.session_name)
                released.append(session.session_name)
        logger.info(
            "配下のセッションを解放しました: project=%s number=%s sessions=%s",
            project.name,
            closed.number,
            released,
        )
        notify(
            "epic_done",
            f"#{closed.number} が完了しました",
            f"プロジェクト: {project.name}\n解放したセッション: {len(released)} 本",
        )


def _is_root(project: MonitoredProject, number: int, *, intake_label: str) -> bool:
    """報告先の conductor を持つ親がない（= 最上位）かを返す。"""
    parent = get_parent_number(project, number)
    # 親なしは最上位
    if parent is None:
        return True
    # intake は起票専用で以降の会話を持たないため、親であっても最上位として扱う
    return intake_label in get_issue(project, parent).labels


def _collect_family_numbers(project: MonitoredProject, root_number: int) -> list[int]:
    """最上位配下（全子孫）と親 intake の Issue 番号を収集する。"""
    numbers = [root_number]
    # Sub-issue の子番号を再帰取得して集める
    stack = [root_number]
    while stack:
        for child in list_sub_issue_numbers(project, stack.pop()):
            if child not in numbers:
                numbers.append(child)
                stack.append(child)
    # 親 Issue（intake）を加える（親なしは加えない）
    parent = get_parent_number(project, root_number)
    if parent is not None and parent not in numbers:
        numbers.append(parent)
    return numbers


def release_closed_standalone(
    project: MonitoredProject,
    targets: list[MonitorTarget],
    *,
    registry: SessionRegistry,
    standalone_names: set[str],
) -> None:
    """独立系エージェントのセッションを担当面の close / merge 検知で解放する。"""
    open_numbers = {t.number for t in targets}
    sessions = [
        s for s in registry.sessions if s.project == project.name and s.agent_name in standalone_names
    ]
    for session in sessions:
        # 主番号が open 一覧に無いものを候補にする
        if session.primary_number in open_numbers:
            continue
        # 単体取得で closed / merged を確認する（open は一覧の取りこぼし）
        if get_issue(project, session.primary_number).state != "closed":
            logger.debug(
                "一覧から消えましたが open のため見送ります: project=%s number=%s",
                project.name,
                session.primary_number,
            )
            continue
        registry.remove(session.session_name)
        kill_session(session.session_name)
        logger.info(
            "独立系セッションを解放しました: project=%s agent_name=%s number=%s",
            project.name,
            session.agent_name,
            session.primary_number,
        )


def reap_timed_out_sessions(
    project: MonitoredProject,
    targets: list[MonitorTarget],
    *,
    registry: SessionRegistry,
    agents: list[Agent],
    timeout_min: int,
    gate: RateLimitGate,
    notify: NotifyFn,
) -> None:
    """処理中のまま超過したセッションを kill して回収し、実体消失の台帳を修復する。"""
    processing_by_agent = {agent.name: agent.processing_label for agent in agents}
    targets_by_number = {t.number: t for t in targets}
    now = datetime.now(timezone.utc)
    alive = []
    for session in [s for s in registry.sessions if s.project == project.name]:
        # tmux に実体が無いセッションは台帳から除去する（実行中セッションの SoT は tmux）
        if not has_session(session.session_name):
            registry.remove(session.session_name)
            logger.warning(
                "tmux 実体が無いセッションを台帳から除去しました: project=%s session_name=%s",
                project.name,
                session.session_name,
            )
            continue
        alive.append(session)
    # レートリミットの待機中は回収しない（止まっているのはハングではない）
    if gate.is_blocked(now):
        return
    for session in alive:
        # last_seen_at の超過を判定する
        elapsed = now - datetime.fromisoformat(session.last_seen_at)
        if elapsed < timedelta(minutes=timeout_min):
            continue
        # 処理中ラベルが付いた対象だけを回収する（待機中は対象外）
        target = targets_by_number.get(session.primary_number)
        processing_label = processing_by_agent.get(session.agent_name)
        if target is None or processing_label is None or processing_label not in target.labels:
            continue
        # ラベル除去 → kill → 台帳除去（除去失敗は見送り、次周期で再試行）
        try:
            remove_label(project, session.primary_number, processing_label)
        except RequestFailed:
            logger.warning(
                "処理中ラベルの除去に失敗したため回収を見送ります: project=%s number=%s",
                project.name,
                session.primary_number,
                exc_info=True,
            )
            continue
        kill_session(session.session_name)
        registry.remove(session.session_name)
        elapsed_min = int(elapsed.total_seconds() // 60)
        logger.warning(
            "タイムアウトしたセッションを kill しました: project=%s session_name=%s elapsed_min=%s",
            project.name,
            session.session_name,
            elapsed_min,
        )
        notify(
            "timeout_kill",
            f"#{session.primary_number} のセッションをタイムアウトで停止しました",
            f"セッション: {session.session_name}\n経過: {elapsed_min} 分",
        )

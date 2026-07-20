"""プロジェクト × エージェントの対ごとのポーリング。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ai_monitor.features.agents.types import Agent
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.integrations.github.labels import add_label
from ai_monitor.integrations.tmux.ops import create_session, send_keys
from ai_monitor.shared.settings import MonitoredProject
from ai_monitor.shared.types import Issue, MonitorTarget, PullRequest

if TYPE_CHECKING:
    from ai_monitor.features.sessions.registry import SessionRegistry

RESUME_TEXT = "状態が変化しました。最新の Issue/PR 状態と自分宛の未解決コメントを取得し、起動判定からやり直してください。"

_PRIORITY_RANKS = {"優先度:急ぎ": 0, "優先度:いつでも": 2}


def poll(
    project: MonitoredProject, agent: Agent, targets: list[MonitorTarget], *, registry: SessionRegistry
) -> None:
    """対象の絞り込みから送信までのポーリング 1 周期を実行する。"""
    # 確認ラベルあり + assignee なしの対象を絞り込む
    matched = [t for t in targets if agent.confirm_label in t.labels and not t.assignees]
    # 処理中ラベルが付いた対象を除外する（send-keys 済みで報告待ち）
    matched = [t for t in matched if agent.processing_label not in t.labels]
    # 優先度順にソートして 1 件ずつ処理する
    for target in sorted(matched, key=_sort_key):
        _process_one(project, agent, target, open_targets=targets, registry=registry)


def build_skill_command(agent: Agent, number: int) -> str:
    """`/ai-monitor:{name} {number}` を組み立てて返す。"""
    return f"/ai-monitor:{agent.name} {number}"


def _process_one(
    project: MonitoredProject,
    agent: Agent,
    target: MonitorTarget,
    *,
    open_targets: list[MonitorTarget],
    registry: SessionRegistry,
) -> None:
    """対象 1 件のセッション解決と send-keys 送信を行う。"""
    # セッションを解決する（無ければ新規作成して台帳へ登録）
    session = registry.find(project.name, agent.name, target.number)
    is_new = session is None
    if session is None:
        session = AgentSession(
            session_name=f"ai-monitor-{project.name}-{target.number}-{agent.name}",
            project=project.name,
            agent_name=agent.name,
            primary_number=target.number,
        )
        create_session(session.session_name, project.local_path)
        registry.register(session)
    # 送信前に処理中ラベルを付与する（除去は作業完了報告の受信時）
    add_label(project, target.number, agent.processing_label)
    # 送信文を組み立てて send-keys で送信する（スナップショットを添付）
    snapshot = build_context_snapshot(target, open_targets)
    if is_new:
        # 新規セッションは shell に対して claude コマンドで skill を起動する
        text = f'claude --dangerously-skip-permissions "{build_skill_command(agent, target.number)}\n\n{snapshot}"'
    else:
        # 既存セッションは稼働中の claude への入力として再開の定型文を送る
        text = f"{RESUME_TEXT}\n\n{snapshot}"
    send_keys(session.session_name, text)


def _sort_key(target: MonitorTarget) -> tuple[int, int]:
    """優先度ソートのキーを求める。"""
    # 優先度ラベルをランクに変換する（急ぎ = 0 / なし = 1 / いつでも = 2）
    rank = 1
    for label in target.labels:
        if label in _PRIORITY_RANKS:
            rank = _PRIORITY_RANKS[label]
    # タプルの辞書順比較でランク昇順 → 同ランクは番号昇順になる
    return (rank, target.number)


def build_context_snapshot(target: MonitorTarget, open_targets: list[MonitorTarget]) -> str:
    """対象と紐づく open PR を state / ラベル / assignee 付きのツリー文字列に整形する。"""
    # 基準の Issue を確定する（PR の場合は紐づく Issue を open 一覧から探す）
    base: MonitorTarget = target
    if isinstance(target, PullRequest):
        linked = [
            t for t in open_targets if isinstance(t, Issue) and t.number in target.linked_issue_numbers
        ]
        base = linked[0] if linked else target
    lines = [_node_line(base)]
    # 基準 Issue の番号を紐づく Issue に含む PR をぶら下げる
    if isinstance(base, Issue):
        for candidate in open_targets:
            if isinstance(candidate, PullRequest) and base.number in candidate.linked_issue_numbers:
                lines.append("  └ " + _node_line(candidate))
    return "\n".join(lines)


def _node_line(target: MonitorTarget) -> str:
    """ツリーの 1 ノードを整形する。"""
    # 種別は layer ラベルがあればその値を使う
    kind = "PR" if isinstance(target, PullRequest) else "Issue"
    for label in target.labels:
        if label.startswith("layer:"):
            kind = label.removeprefix("layer:")
    return f"{kind} #{target.number} [{target.state}] labels={target.labels} assignees={target.assignees}"

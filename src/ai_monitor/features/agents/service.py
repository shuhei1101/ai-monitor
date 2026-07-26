"""プロジェクト × エージェントの対ごとのポーリング。"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ai_monitor.features.agents.docs import build_agent_docs
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.integrations.github.labels import add_label
from ai_monitor.integrations.tmux.ops import create_session, kill_session, send_keys
from ai_monitor.shared.settings import MonitoredProject, TelemetrySettings
from ai_monitor.shared.types import Issue, MonitorTarget, PullRequest

if TYPE_CHECKING:
    from ai_monitor.features.sessions.registry import SessionRegistry

logger = logging.getLogger(__name__)

RESUME_TEXT = "状態が変化しました。最新の Issue/PR 状態と自分宛の未解決コメントを取得し、起動判定からやり直してください。"

RESET_SNAPSHOT = "コンテキスト上限に達したためセッションを作り直しました。最新の Issue/PR 状態は初期処理で取得してください。"

_PRIORITY_RANKS = {"優先度:急ぎ": 0, "優先度:いつでも": 2}


def poll(
    project: MonitoredProject,
    agent: Agent,
    targets: list[MonitorTarget],
    *,
    registry: SessionRegistry,
    telemetry: TelemetrySettings | None,
    port: int,
    ai_monitor_wiki_base: str,
) -> None:
    """対象の絞り込みから送信までのポーリング 1 周期を実行する。"""
    # 確認ラベルあり + assignee なしの対象を絞り込む
    matched = [t for t in targets if agent.confirm_label in t.labels and not t.assignees]
    # 処理中ラベルが付いた対象を除外する（send-keys 済みで報告待ち）
    matched = [t for t in matched if agent.processing_label not in t.labels]
    # 優先度順にソートして 1 件ずつ処理する
    for target in sorted(matched, key=_sort_key):
        _process_one(
            project,
            agent,
            target,
            open_targets=targets,
            registry=registry,
            telemetry=telemetry,
            port=port,
            ai_monitor_wiki_base=ai_monitor_wiki_base,
        )


def build_launch_prompt(
    agent: Agent,
    number: int,
    project: MonitoredProject,
    snapshot: str,
    *,
    ai_monitor_wiki_base: str,
) -> str:
    """新規セッションに渡す起動プロンプトを組み立てて返す。"""
    # エージェントドキュメント（フェーズ + 参考資料 + Wiki 索引）を組み立てる
    agent_docs = build_agent_docs(
        agent.name, project, ai_monitor_wiki_base=ai_monitor_wiki_base
    )
    # 役割の宣言・入力・ドキュメント・スナップショットの順に連結する
    return (
        f"あなたは {agent.name} です。\n\n"
        f"## 入力\n\n"
        f"- 対象番号: {number}\n\n"
        f"{agent_docs}\n\n"
        f"## 対象の状態\n\n"
        f"{snapshot}\n"
    )


def build_launch_command(
    session_name: str,
    agent: Agent,
    number: int,
    project: MonitoredProject,
    snapshot: str,
    *,
    telemetry: TelemetrySettings | None,
    port: int,
    ai_monitor_wiki_base: str,
) -> str:
    """claude を起動する shell コマンドを組み立てて返す。"""
    # 起動プロンプトを一時ファイルへ書き出し、コマンド置換で claude に渡す
    # （数万文字を send-keys の引数に直接埋めず、本文のバッククォート・$ の再展開も防ぐ）
    launch_env = build_launch_env(telemetry, project, agent, number, port)
    prompt = build_launch_prompt(
        agent, number, project, snapshot, ai_monitor_wiki_base=ai_monitor_wiki_base
    )
    prompt_path = Path(tempfile.gettempdir()) / f"{session_name}.prompt"
    prompt_path.write_text(prompt, encoding="utf-8")
    return (
        f"{launch_env}claude --model {agent.model} "
        f'--dangerously-skip-permissions "$(cat {prompt_path})"'
    )


def reset_session(
    session: AgentSession,
    project: MonitoredProject,
    agent: Agent,
    *,
    telemetry: TelemetrySettings | None,
    port: int,
    ai_monitor_wiki_base: str,
) -> None:
    """tmux セッションを作り直し、起動時と同じプロンプトで claude を立ち上げ直す。"""
    # セッションごと落として同じ名前で作り直す（会話履歴が消え、起動直後と同じ状態になる）
    kill_session(session.session_name)
    create_session(session.session_name, project.local_path)
    # 起動コマンドを送る（対象の最新状態はエージェントが初期処理で取得し直す）
    text = build_launch_command(
        session.session_name,
        agent,
        session.primary_number,
        project,
        RESET_SNAPSHOT,
        telemetry=telemetry,
        port=port,
        ai_monitor_wiki_base=ai_monitor_wiki_base,
    )
    send_keys(session.session_name, text)
    logger.info(
        "セッションを作り直しました: project=%s agent_name=%s number=%s session_name=%s",
        project.name,
        agent.name,
        session.primary_number,
        session.session_name,
    )


def build_launch_env(
    telemetry: TelemetrySettings | None,
    project: MonitoredProject,
    agent: Agent,
    number: int,
    port: int,
) -> str:
    """claude 起動コマンドに前置する環境変数の並びを組み立てて返す。"""
    # フックとの共有変数（MCP のプロジェクト識別子 + フックが自分の素性と宛先を知る経路）
    shared = (
        f"AI_MONITOR_PROJECT={project.name}",
        f"AI_MONITOR_AGENT={agent.name}",
        f"AI_MONITOR_NUMBER={number}",
        f"AI_MONITOR_PORT={port}",
    )
    project_env = " ".join(shared)
    # telemetry の設定を持たない環境では共有変数だけを前置する
    if telemetry is None:
        return project_env + " "
    # どの対象のどのエージェントが出した telemetry かを後から引くための識別子
    resource_attributes = ",".join(
        (
            f"ai_monitor.project={project.name}",
            f"ai_monitor.agent={agent.name}",
            f"ai_monitor.number={number}",
        )
    )
    variables = (
        project_env,
        "CLAUDE_CODE_ENABLE_TELEMETRY=1",
        # トレースと OTEL_LOG_TOOL_CONTENT は beta ゲートの内側にある
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1",
        "OTEL_LOGS_EXPORTER=otlp",
        "OTEL_TRACES_EXPORTER=otlp",
        "OTEL_METRICS_EXPORTER=otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL=grpc",
        f"OTEL_EXPORTER_OTLP_ENDPOINT={telemetry.otlp_endpoint}",
        "OTEL_LOG_USER_PROMPTS=1",
        "OTEL_LOG_ASSISTANT_RESPONSES=1",
        "OTEL_LOG_TOOL_DETAILS=1",
        "OTEL_LOG_TOOL_CONTENT=1",
        f"OTEL_RESOURCE_ATTRIBUTES={resource_attributes}",
    )
    return " ".join(variables) + " "


def _process_one(
    project: MonitoredProject,
    agent: Agent,
    target: MonitorTarget,
    *,
    open_targets: list[MonitorTarget],
    registry: SessionRegistry,
    telemetry: TelemetrySettings | None,
    port: int,
    ai_monitor_wiki_base: str,
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
        logger.info(
            "エージェントセッションを新規作成しました: project=%s agent_name=%s number=%s session_name=%s model=%s",
            project.name,
            agent.name,
            target.number,
            session.session_name,
            agent.model,
        )
    # 送信前に処理中ラベルを付与する（除去は作業完了報告の受信時）
    add_label(project, target.number, agent.processing_label)
    # 送信文を組み立てて send-keys で送信する（スナップショットを添付）
    snapshot = build_context_snapshot(target, open_targets)
    if is_new:
        # 新規セッションは claude の起動コマンドを送る
        text = build_launch_command(
            session.session_name,
            agent,
            target.number,
            project,
            snapshot,
            telemetry=telemetry,
            port=port,
            ai_monitor_wiki_base=ai_monitor_wiki_base,
        )
    else:
        # 既存セッションは稼働中の claude への入力として再開の定型文を送る
        text = f"{RESUME_TEXT}\n\n{snapshot}"
    send_keys(session.session_name, text)
    logger.info(
        "エージェントへ送信しました: project=%s agent_name=%s number=%s session_name=%s kind=%s",
        project.name,
        agent.name,
        target.number,
        session.session_name,
        "新規起動" if is_new else "再開",
    )


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

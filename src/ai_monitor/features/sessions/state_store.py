"""セッション台帳ファイルの読み書き。"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import yaml

from ai_monitor.features.sessions.types import AgentSession


def load_sessions(path: Path) -> list[AgentSession]:
    """YAML からセッション一覧を復元する。"""
    # ファイルが無ければ空リストを返す
    if not path.exists():
        return []
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    # 各エントリを AgentSession に変換して返す
    return [AgentSession(**entry) for entry in entries]


def save_sessions(path: Path, sessions: list[AgentSession]) -> None:
    """tmp ファイルに書いて rename する（アトミック書き）。"""
    # sessions を YAML にして同フォルダの tmp ファイルへ書き込む
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        yaml.safe_dump([asdict(session) for session in sessions], allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    # tmp ファイルを path へ rename する
    tmp_path.replace(path)

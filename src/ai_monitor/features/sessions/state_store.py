"""セッション台帳ファイルの読み書き。"""
from __future__ import annotations

import logging
from dataclasses import asdict, fields
from pathlib import Path

import yaml

from ai_monitor.features.sessions.types import AgentSession

logger = logging.getLogger(__name__)


def load_sessions(path: Path) -> list[AgentSession]:
    """YAML からセッション一覧を復元する。"""
    # ファイルが無ければ空リストを返す
    if not path.exists():
        return []
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    # 旧版が書いたキーは読み飛ばす（台帳は実行時の記録なので、項目を減らした版で起動できなくしない）
    known = {f.name for f in fields(AgentSession)}
    dropped = sorted({key for entry in entries for key in entry if key not in known})
    if dropped:
        logger.warning("台帳の未知の項目を読み飛ばしました: path=%s keys=%s", path, dropped)
    # 各エントリを AgentSession に変換して返す
    sessions = [
        AgentSession(**{key: value for key, value in entry.items() if key in known})
        for entry in entries
    ]
    logger.info("セッション台帳を復元しました: path=%s count=%s", path, len(sessions))
    return sessions


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

"""再起動の記録の読み書き（再起動をまたいで数えるためファイルに持つ）。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# 記録を保持する期間の余裕（上限期間の何倍まで残すか）
_KEEP_FACTOR = 2


def _load(path: Path) -> list[dict]:
    """記録ファイルを読む（読めなければ空として扱う）。"""
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        # 記録の欠損で監視そのものを止めない
        logger.warning("再起動の記録を読めませんでした: path=%s", path, exc_info=True)
        return []
    return loaded if isinstance(loaded, list) else []


def count_recent_restarts(path: Path, name: str, *, now: datetime, window_min: int) -> int:
    """指定期間内に記録された、対象ごとの再起動回数を返す。"""
    since = now - timedelta(minutes=window_min)
    count = 0
    # 対象名が一致し、記録時刻が期間内のものだけを数える
    for entry in _load(path):
        if not isinstance(entry, dict) or entry.get("name") != name:
            continue
        try:
            at = datetime.fromisoformat(str(entry.get("at")))
        except ValueError:
            continue
        if at >= since:
            count += 1
    return count


def record_restart(path: Path, name: str, *, now: datetime, window_min: int) -> None:
    """再起動を 1 件追記する。"""
    entries = _load(path)
    entries.append({"name": name, "at": now.isoformat()})
    # 期間の判定に使わなくなった古い記録を落とす（ファイルが無限に伸びないようにする）
    keep_since = now - timedelta(minutes=window_min * _KEEP_FACTOR)
    kept = []
    for entry in entries:
        try:
            at = datetime.fromisoformat(str(entry.get("at")))
        except ValueError:
            continue
        if at >= keep_since:
            kept.append(entry)
    # 一時ファイルへ書いてから rename で置き換える
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(kept, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp.replace(path)

"""会話ログからのリセット時刻解決と、解除後の再開送信。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from ai_monitor.features.agents.service import RESUME_TEXT
from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.integrations.tmux.ops import has_session, send_keys

if TYPE_CHECKING:
    from ai_monitor.features.sessions.registry import SessionRegistry

logger = logging.getLogger(__name__)

# `You've hit your session limit · resets 2:30am (Asia/Tokyo)` から 12 時間表記の時刻とタイムゾーン名を取り出す
_RESET_PATTERN = re.compile(r"resets\s+(\d{1,2}):(\d{2})\s*(am|pm)\s*\(([^)]+)\)", re.IGNORECASE)

# 上限に当たったセッションが止まっている確認ダイアログを、既定選択のまま確定して閉じるキー
_DIALOG_CONFIRM_KEY = "Enter"


def resolve_reset_at(transcript_path: Path, now: datetime) -> datetime | None:
    """会話ログの最新の到達レコードから、上限のリセット時刻を読む。"""
    # 会話ログから最新の到達レコードを取る
    record = _find_latest_record(transcript_path)
    if record is None:
        return None
    # 本文からリセット時刻とタイムゾーン名を取り出す
    blocks = record.get("message", {}).get("content", [])
    text = " ".join(block.get("text", "") for block in blocks if isinstance(block, dict))
    matched = _RESET_PATTERN.search(text)
    if matched is None:
        logger.warning(
            "リセット時刻を読めませんでした: transcript_path=%s text=%s", transcript_path, text
        )
        return None
    # 12 時間表記を 24 時間表記へ直す（12am = 0 時 / 12pm = 12 時）
    hour = int(matched.group(1)) % 12
    if matched.group(3).lower() == "pm":
        hour += 12
    # 現在時刻を基準に日付を補完する（本文には時刻しか入らない）
    base = now.astimezone(ZoneInfo(matched.group(4)))
    resets_at = base.replace(hour=hour, minute=int(matched.group(2)), second=0, microsecond=0)
    if resets_at < base:
        resets_at += timedelta(days=1)
    return resets_at


def _find_latest_record(transcript_path: Path) -> dict | None:
    """会話ログを末尾から辿り、最初に見つかった到達レコードを返す。"""
    for line in reversed(transcript_path.read_text(encoding="utf-8").splitlines()):
        # 書き込み途中の行があり得るので JSON として読めない行は飛ばす
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("error") == "rate_limit":
            return record
    return None


def resume_blocked_sessions(
    gate: RateLimitGate, *, registry: SessionRegistry, now: datetime
) -> list[str]:
    """待機が解除されていれば、止まっているセッションへ応答と再開の定型文を送る。"""
    # 関門から再開対象を取り出す
    resumed = []
    for session_name in gate.take_resumable(now):
        # tmux に実体が無い対象は飛ばす（解放済みセッション）
        if not has_session(session_name):
            continue
        # 確認ダイアログを閉じてから、ターンを再開させる定型文を送る
        send_keys(session_name, _DIALOG_CONFIRM_KEY)
        send_keys(session_name, RESUME_TEXT)
        logger.info("レートリミットから再開しました: session_name=%s", session_name)
        resumed.append(session_name)
    # 待機で古くなった生存時刻を更新する（同じ周期のタイムアウト回収に kill されないようにする）
    for session_name in resumed:
        registry.touch(session_name)
    return resumed

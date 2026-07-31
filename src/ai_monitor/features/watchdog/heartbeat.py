"""最終周回時刻の書き出し。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def touch_heartbeat(path: Path, *, now: datetime) -> None:
    """最終周回時刻を書き出す。"""
    # 親ディレクトリが無ければ作る
    path.parent.mkdir(parents=True, exist_ok=True)
    # 一時ファイルへ書いてから rename で置き換える（書き込み中の内容を読ませない）
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(now.isoformat(), encoding="utf-8")
    tmp.replace(path)

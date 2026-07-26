#!/usr/bin/env python3
"""コンパクト発生をモニターへ通知する PostCompact フック。"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

# tmux 起動時にモニターが渡した環境変数（フックのプロセスが継承する）
_REQUIRED_ENV = ("AI_MONITOR_PROJECT", "AI_MONITOR_AGENT", "AI_MONITOR_NUMBER", "AI_MONITOR_PORT")


def main() -> int:
    """環境変数から自セッションの素性を組み立て、モニターへ POST する。"""
    # 4 変数を読む（欠けていればモニター起動でないセッションなので何もしない）
    values = {name: os.environ.get(name) for name in _REQUIRED_ENV}
    if not all(values.values()):
        return 0

    # モニターのコンパクト通知エンドポイントへ POST する
    body = json.dumps(
        {
            "project": values["AI_MONITOR_PROJECT"],
            "agent_name": values["AI_MONITOR_AGENT"],
            "number": int(values["AI_MONITOR_NUMBER"]),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{values['AI_MONITOR_PORT']}/compaction",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # 通信に失敗しても握りつぶす（再送が届かないだけで、次の状態変化で再開できる）
    try:
        with urllib.request.urlopen(request):
            pass
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

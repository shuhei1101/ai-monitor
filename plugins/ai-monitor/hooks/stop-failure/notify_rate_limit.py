#!/usr/bin/env python3
"""利用上限への到達をモニターへ通知する StopFailure フック。"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

# tmux 起動時にモニターが渡した環境変数（フックのプロセスが継承する）
_REQUIRED_ENV = ("AI_MONITOR_PROJECT", "AI_MONITOR_AGENT", "AI_MONITOR_NUMBER", "AI_MONITOR_PORT")


def main() -> int:
    """会話ログのパスを添えてモニターへ到達を通知する。"""
    # 4 変数を読む（欠けていればモニター起動でないセッションなので何もしない）
    values = {name: os.environ.get(name) for name in _REQUIRED_ENV}
    if not all(values.values()):
        return 0

    # フック入力から会話ログのパスを取り出す（リセット時刻はモニターがここから読む）
    transcript_path = json.load(sys.stdin).get("transcript_path")
    if not transcript_path:
        return 0

    # モニターのレートリミット通知エンドポイントへ POST する
    body = json.dumps(
        {
            "project": values["AI_MONITOR_PROJECT"],
            "agent_name": values["AI_MONITOR_AGENT"],
            "number": int(values["AI_MONITOR_NUMBER"]),
            "transcript_path": transcript_path,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{values['AI_MONITOR_PORT']}/rate_limit",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

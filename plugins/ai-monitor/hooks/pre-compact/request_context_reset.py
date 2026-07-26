#!/usr/bin/env python3
"""コンパクトをブロックし、モニターへコンテキストリセットを要求する PreCompact フック。"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

# tmux 起動時にモニターが渡した環境変数（フックのプロセスが継承する）
_REQUIRED_ENV = ("AI_MONITOR_PROJECT", "AI_MONITOR_AGENT", "AI_MONITOR_NUMBER", "AI_MONITOR_PORT")


def main() -> int:
    """モニターへリセットを要求し、コンパクトをブロックする指示を標準出力に書く。"""
    # 4 変数を読む（欠けていればモニター起動でないセッションなのでコンパクトを通常どおり行わせる）
    values = {name: os.environ.get(name) for name in _REQUIRED_ENV}
    if not all(values.values()):
        return 0

    # モニターのコンテキストリセットエンドポイントへ POST する
    body = json.dumps(
        {
            "project": values["AI_MONITOR_PROJECT"],
            "agent_name": values["AI_MONITOR_AGENT"],
            "number": int(values["AI_MONITOR_NUMBER"]),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{values['AI_MONITOR_PORT']}/context_reset",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request):
            pass
    except Exception:
        # リセットが届かないのにコンパクトも止めると、コンテキストが溢れたまま進んでしまう
        return 0

    # 要求が届いたのでコンパクトをブロックする（モニターが /clear + ドキュメント送信で復元する）
    print(json.dumps({"decision": "block", "reason": "モニターがコンテキストをリセットします"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

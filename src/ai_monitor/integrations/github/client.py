"""githubkit クライアントの生成・共有。"""
from __future__ import annotations

from githubkit import GitHub

from ai_monitor.shared.settings import Settings

_client: GitHub | None = None


def get_client(settings: Settings | None = None) -> GitHub:
    """githubkit クライアントを生成してモジュール内で共有する。"""
    global _client
    # 初回呼び出し時に生成してモジュール内に保持する
    if _client is None:
        if settings is None:
            raise RuntimeError("初回の get_client には settings が必要")
        _client = GitHub(settings.github_token.get_secret_value())
    # 2 回目以降は保持済みの同一インスタンスを返す
    return _client

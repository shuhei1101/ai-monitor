"""githubkit クライアントの生成・共有。"""
from __future__ import annotations

import logging

from githubkit import GitHub
from githubkit.exception import GitHubException

from ai_monitor.shared.settings import Settings

logger = logging.getLogger(__name__)

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


def check_github() -> str:
    """認証ユーザーを取得してトークンが有効かを確かめる（失敗理由を返し、成功時は空文字）。"""
    try:
        user = get_client().rest.users.get_authenticated().parsed_data
    except GitHubException as exc:
        # 応答異常も通信断も同じ扱いで理由に落とす（起動可否の判断は呼び出し側）
        status = getattr(getattr(exc, "response", None), "status_code", None)
        reason = f"{status}" if status else f"{type(exc).__name__}: {exc}"
        logger.error("GitHub API へ疎通できなかった", extra={"reason": reason})
        return reason
    logger.info("GitHub API へ疎通した", extra={"login": user.login})
    return ""

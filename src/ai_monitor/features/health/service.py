"""起動時の依存確認。"""
from __future__ import annotations

import logging
from collections.abc import Callable

from ai_monitor.features.health.types import CheckFn, CheckResult
from ai_monitor.shared.settings import NotifySettings

logger = logging.getLogger(__name__)

# 必須依存の表示名（繋がらなければ起動できない）
GITHUB_NAME = "GitHub API"


def check_dependencies(
    notifies: list[NotifySettings],
    *,
    check_github_fn: CheckFn,
    check_webhook_fn: Callable[[str], str],
) -> list[CheckResult]:
    """設定に書かれた依存を順に確認し、結果の一覧を返す（起動可否の判断は呼び出し側）。"""
    # 必須依存を確認する
    reason = check_github_fn()
    results = [CheckResult(name=GITHUB_NAME, required=True, ok=not reason, reason=reason)]
    if reason:
        # 必須が繋がらない時点で以降の確認に意味がないので打ち切る
        logger.error("必須依存へ繋がらなかった", extra={"dependency": GITHUB_NAME, "reason": reason})
        return results
    # 補助依存（通知の送信先）を確認する
    for settings in notifies:
        # 無効にした送信先は確認しない
        if not settings.enabled:
            continue
        name = settings.name or f"{settings.type}:{settings.kind}"
        reason = check_webhook_fn(settings.webhook_url.get_secret_value())
        if reason:
            # 1 件失敗しても後続の送信先を確認し続ける（補助依存なので起動は止めない）
            logger.warning("送信先へ繋がらなかった", extra={"dependency": name, "reason": reason})
        results.append(CheckResult(name=name, required=False, ok=not reason, reason=reason))
    return results

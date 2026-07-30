"""通知の送出判断と本文組み立て。"""
from __future__ import annotations

import logging
from functools import partial
from typing import assert_never

from ai_monitor.features.notify.types import (
    NotifyEvent,
    NotifyFn,
    SendResult,
    SendTarget,
    TargetResult,
)
from ai_monitor.integrations.webhook.client import post_webhook
from ai_monitor.shared.settings import NotifySettings

logger = logging.getLogger(__name__)

# Webhook 側の上限に収めるための本文の合計上限
MAX_LENGTH = 2000

# モニターが送る通知の送信元名（エージェント名と区別する）
MONITOR_SENDER = "monitor"


def build_message(
    sender: str,
    title: str,
    body: str,
    *,
    repo: str | None = None,
    number: int | None = None,
) -> str:
    """送信元・見出し・本文・対象リンクを 1 本のテキストにする。"""
    # 送信元と見出しを 1 行目にする
    lines = [f"**[{sender}] {title}**", body]
    # 対象が特定できる場合だけ末尾にリンクを足す
    if repo and number:
        lines.append(f"https://github.com/{repo}/issues/{number}")
    text = "\n".join(lines)
    # 上限を超える場合は末尾を切る
    return text[:MAX_LENGTH]


def build_targets(settings_list: list[NotifySettings]) -> list[SendTarget]:
    """有効な設定から送出先の一覧を作る（送信先を束ねて本文だけ受ける形にする）。"""
    targets: list[SendTarget] = []
    for settings in settings_list:
        # 無効にした送信先は候補から外す
        if not settings.enabled:
            continue
        # 送出方式で実装を選ぶ（方式を増やしたら分岐を足す。漏れは assert_never が型検査で弾く）
        match settings.type:
            case "webhook":
                send = partial(
                    post_webhook, settings.webhook_url.get_secret_value(), settings.kind
                )
                name = settings.name or f"{settings.type}:{settings.kind}"
            case _:
                assert_never(settings.type)
        targets.append(SendTarget(name=name, send=send))
    return targets


def send_notification(
    sender: str,
    title: str,
    body: str,
    *,
    targets: list[SendTarget],
    repo: str | None = None,
    number: int | None = None,
) -> SendResult:
    """全ての送出先へ同じ本文を送る（送出の失敗は例外にせず結果で返す）。"""
    # 送出先が無い場合: 送らずに空の結果を返す（設定漏れを握り潰さない）
    if not targets:
        logger.debug("有効な送出先が無いため送信しなかった", extra={"sender": sender})
        return SendResult(sent=False)
    # 本文を組み立てて送出先へ順に送る（失敗しても後続へ送り続ける）
    text = build_message(sender, title, body, repo=repo, number=number)
    results = []
    for target in targets:
        reason = target.send(text)
        if reason:
            logger.warning(
                "送信先への送出に失敗した", extra={"target": target.name, "reason": reason}
            )
        results.append(TargetResult(target=target.name, sent=not reason, reason=reason))
    return SendResult(sent=any(r.sent for r in results), results=results)


def notify_event(
    event: NotifyEvent,
    title: str,
    body: str,
    settings_list: list[NotifySettings],
    *,
    targets: list[SendTarget],
    repo: str | None = None,
    number: int | None = None,
) -> SendResult:
    """モニターが検知した契機を、その契機が有効な送出先へ定型文で送る。"""
    # 契機を無効にしている送出先を除く（events に無いキーは有効として扱う）
    enabled = [
        target
        for settings, target in zip(settings_list, targets, strict=True)
        if settings.events.get(event, True)
    ]
    # 送る先が無い場合: 送らずに空の結果を返す
    if not enabled:
        logger.debug("当該契機を送る送出先が無いため送信しなかった", extra={"event": event})
        return SendResult(sent=False)
    return send_notification(
        MONITOR_SENDER, title, body, targets=enabled, repo=repo, number=number
    )


def build_notifier(settings_list: list[NotifySettings]) -> NotifyFn:
    """設定から送出先を組み立てた契機通知の関数を返す（composition root で 1 回だけ呼ぶ）。"""
    # 有効な設定だけを送出先にし、契機の判定に使う設定も同じ並びで束ねる
    enabled_settings = [s for s in settings_list if s.enabled]
    targets = build_targets(settings_list)
    return partial(notify_event, settings_list=enabled_settings, targets=targets)

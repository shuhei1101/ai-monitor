"""Webhook（Discord / Slack）へ HTTP で送る境界層。"""
from __future__ import annotations

import logging

import httpx

from ai_monitor.features.notify.types import WebhookKind

logger = logging.getLogger(__name__)

# 通知の遅延がエージェントのターンを止めないようにする
TIMEOUT_SEC = 10

# 送信先サービスごとの本文キー
_BODY_KEYS: dict[str, str] = {"discord": "content", "slack": "text"}


def build_payload(kind: WebhookKind, text: str) -> dict[str, str]:
    """送信先サービスに合わせた POST ボディを作る。"""
    return {_BODY_KEYS[kind]: text}


def check_webhook(webhook_url: str) -> str:
    """送信先へ到達できるかを確かめる（失敗理由を返し、成功時は空文字）。

    起動のたびにチャットが鳴らないよう、メッセージは送らずに URL へ到達できるかだけを見る。
    """
    try:
        response = httpx.get(webhook_url, timeout=TIMEOUT_SEC)
    except httpx.HTTPError as exc:
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning("送信先へ到達できなかった", extra={"error": type(exc).__name__})
        return reason
    # 応答が 2xx なら到達できたとみなす
    if response.is_success:
        logger.info("送信先へ疎通した", extra={"status_code": response.status_code})
        return ""
    return f"{response.status_code} {response.reason_phrase}".strip()


def post_webhook(webhook_url: str, kind: WebhookKind, text: str) -> str:
    """Webhook へ 1 回だけ POST する（失敗理由を返し、成功時は空文字）。"""
    # ペイロードを組み立てる
    payload = build_payload(kind, text)
    # タイムアウト付きで 1 回だけ送る（通知は補助手段なのでリトライしない）
    try:
        response = httpx.post(webhook_url, json=payload, timeout=TIMEOUT_SEC)
    except httpx.HTTPError as exc:
        # 通信に失敗した場合: 送出側へ例外を伝播させず理由として返す
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning("Webhook への送信に失敗した", extra={"kind": kind, "error": type(exc).__name__})
        return reason
    # 応答が 2xx なら成功、それ以外は応答コードを理由にする
    if response.is_success:
        logger.info("Webhook へ通知を送った", extra={"kind": kind, "length": len(text)})
        return ""
    reason = f"{response.status_code} {response.reason_phrase}".strip()
    logger.warning(
        "Webhook が失敗応答を返した", extra={"kind": kind, "status_code": response.status_code}
    )
    return reason

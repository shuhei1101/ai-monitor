"""通知ドメインの型定義。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

# モニターが自分で検知して送る契機
type NotifyEvent = Literal["rate_limit", "user_gate", "timeout_kill", "epic_done"]

# 送信先サービス（ペイロードのキーが変わる）
type WebhookKind = Literal["discord", "slack"]

# 組み立て済みの本文を送る関数（失敗理由を返し、成功時は空文字）
# 送信先は build_sender が束ねるため、本型は本文だけを受ける
type SendMessage = Callable[[str], str]

# 契機を検知した側が呼ぶ通知関数（設定と送出先は composition root で束ねる）
type NotifyFn = Callable[[NotifyEvent, str, str], "SendResult"]


@dataclass(frozen=True, slots=True, kw_only=True)
class SendTarget:
    """送出先 1 件分（識別名と、送信先を束ね済みの送出関数）。"""

    name: str
    send: SendMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetResult:
    """1 送信先に対する送出の成否と理由。"""

    target: str
    sent: bool
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class SendResult:
    """全体の成否と、送信先ごとの結果。"""

    sent: bool
    results: list[TargetResult] = field(default_factory=list)

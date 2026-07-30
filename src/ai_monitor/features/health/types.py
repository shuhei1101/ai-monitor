"""起動チェックの型定義。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# 依存へ疎通する関数（失敗理由を返し、成功時は空文字）
type CheckFn = Callable[[], str]


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckResult:
    """1 依存に対する疎通確認の結果。"""

    name: str
    required: bool
    ok: bool
    reason: str = ""

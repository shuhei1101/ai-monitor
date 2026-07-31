"""モニターのドメインモデル。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NewType

LabelName = NewType("LabelName", str)

# claude --effort が受け付ける値の列挙（列挙外は設定の読み込み時に弾く）
type EffortLevel = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True, slots=True, kw_only=True)
class Issue:
    """GitHub Issue のスナップショット。"""

    number: int
    state: Literal["open", "closed"] = "open"
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    sub_issues_total: int = 0
    sub_issues_completed: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class PullRequest:
    """GitHub PR のスナップショット。"""

    number: int
    state: Literal["open", "closed", "merged"] = "open"
    draft: bool = True
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    linked_issue_numbers: list[int] = field(default_factory=list)


type MonitorTarget = Issue | PullRequest

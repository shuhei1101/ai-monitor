"""モニターのドメインモデル。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NewType

LabelName = NewType("LabelName", str)


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

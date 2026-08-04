"""Issue の状態更新と単体取得。"""
from __future__ import annotations


from ai_monitor.integrations.github.client import get_client
from ai_monitor.integrations.github.search import to_target
from ai_monitor.shared.settings import MonitoredProject
from ai_monitor.shared.types import Issue, PullRequest

_PER_PAGE = 100


def close_issue(project: MonitoredProject, number: int) -> None:
    """Issue を completed でクローズする。"""
    owner, repo = project.repo.split("/")
    get_client().rest.issues.update(
        owner=owner, repo=repo, issue_number=number, state="closed", state_reason="completed"
    )


def get_issue(project: MonitoredProject, number: int) -> Issue:
    """Issue / PR を 1 件取得してドメインモデルで返す。"""
    owner, repo = project.repo.split("/")
    item = get_client().rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data
    target = to_target(item)
    # PR も Issue として返す（merged は closed になる）
    if isinstance(target, PullRequest):
        return Issue(
            number=target.number,
            state="closed" if target.state != "open" else "open",
            labels=target.labels,
            assignees=target.assignees,
        )
    return target


def get_parent_number(project: MonitoredProject, number: int, targets: list[PullRequest]) -> int | None:
    """親 PR の番号を返す（base を head に持つ PR。無ければ None）。"""
    target = next((t for t in targets if t.number == number), None)
    if target is None or not target.base_ref:
        return None
    parent = next((t for t in targets if t.head_ref and t.head_ref == target.base_ref), None)
    return parent.number if parent else None


def list_child_numbers(number: int, targets: list[PullRequest]) -> list[int]:
    """base に自分の head を持つ子 PR の番号一覧を返す（1 段のみ）。"""
    target = next((t for t in targets if t.number == number), None)
    if target is None or not target.head_ref:
        return []
    return [t.number for t in targets if t.base_ref == target.head_ref]

"""Issue の状態更新と単体取得。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

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


def get_parent_number(project: MonitoredProject, number: int) -> int | None:
    """Sub-issue リンクの親 Issue 番号を取得する（親なしは None）。"""
    owner, repo = project.repo.split("/")
    try:
        parent = get_client().rest.issues.get_parent(owner=owner, repo=repo, issue_number=number).parsed_data
    except RequestFailed as exc:
        # 親なしの 404 は None を返す
        if exc.response.status_code == 404:
            return None
        raise
    return parent.number


def list_sub_issue_numbers(project: MonitoredProject, number: int) -> list[int]:
    """Sub-issue リンクの子 Issue 番号一覧を取得する（1 段のみ）。"""
    owner, repo = project.repo.split("/")
    numbers: list[int] = []
    # 子 Issue 一覧をページネーションで全件取得する
    page = 1
    while True:
        items = get_client().rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=number, per_page=_PER_PAGE, page=page
        ).parsed_data
        numbers.extend(item.number for item in items)
        if len(items) < _PER_PAGE:
            break
        page += 1
    return numbers

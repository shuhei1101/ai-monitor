"""GitHub の Stacked Pull Requests の読み書き。

`gh stack` CLI は底の PR の base をデフォルトブランチへ書き換えるため使わず、REST / GraphQL を直接呼ぶ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ai_monitor.integrations.github.client import get_client
from ai_monitor.shared.settings import MonitoredProject

_STACK_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      stackEntry { position }
      stack {
        number
        entries(first: 50) { nodes { position pullRequest { number state } } }
      }
    }
  }
}
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class Stack:
    """PR のスタック所属。"""

    number: int
    position: int
    # 下から上の順に並んだ構成 PR 番号
    pull_requests: list[int] = field(default_factory=list)
    # 自分より下でまだ open な PR 番号（空でない間は着手できない）
    below_open: list[int] = field(default_factory=list)


def get_stack(project: MonitoredProject, pr_number: int) -> Stack | None:
    """PR のスタック所属を返す（未所属は None）。"""
    owner, repo = project.repo.split("/")
    data = get_client().graphql(_STACK_QUERY, {"owner": owner, "repo": repo, "number": pr_number})
    pr = data["repository"]["pullRequest"]
    # PR が解決できない / スタックに属していない場合は未所属として扱う
    if pr is None or pr.get("stack") is None:
        return None
    position = pr["stackEntry"]["position"]
    nodes = sorted(pr["stack"]["entries"]["nodes"], key=lambda n: n["position"])
    return Stack(
        number=pr["stack"]["number"],
        position=position,
        pull_requests=[n["pullRequest"]["number"] for n in nodes],
        # 自分より下（position が小さい）で open のものだけ集める
        below_open=[
            n["pullRequest"]["number"]
            for n in nodes
            if n["position"] < position and n["pullRequest"]["state"].upper() == "OPEN"
        ],
    )


def create_stack(project: MonitoredProject, pull_requests: list[int]) -> int:
    """PR 番号の並び（下から上）からスタックを作り、スタック番号を返す。"""
    owner, repo = project.repo.split("/")
    response = get_client().request(
        "POST", f"/repos/{owner}/{repo}/stacks", json={"pull_requests": pull_requests}
    )
    return int(response.json()["number"])


def add_to_stack(project: MonitoredProject, stack_number: int, pull_requests: list[int]) -> None:
    """既存スタックの上端へ PR を積む。"""
    owner, repo = project.repo.split("/")
    get_client().request(
        "POST",
        f"/repos/{owner}/{repo}/stacks/{stack_number}/add",
        json={"pull_requests": pull_requests},
    )


def dissolve_stack(project: MonitoredProject, stack_number: int, pull_requests: list[int]) -> None:
    """スタックを解散する（1 件指定でもスタック全体が解散する）。"""
    owner, repo = project.repo.split("/")
    get_client().request(
        "POST",
        f"/repos/{owner}/{repo}/stacks/{stack_number}/unstack",
        json={"pull_requests": pull_requests},
    )

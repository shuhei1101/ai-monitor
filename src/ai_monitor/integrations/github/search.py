"""open 対象の列挙と PR 本文の解析。"""
from __future__ import annotations

import re
from dataclasses import replace

from ai_monitor.integrations.github.client import get_client
from ai_monitor.shared.settings import MonitoredProject
from ai_monitor.shared.types import Issue, MonitorTarget, PullRequest

_PER_PAGE = 100


def list_open_targets(project: MonitoredProject) -> list[MonitorTarget]:
    """open の Issue / PR を全件取得してドメインモデルで返す。"""
    client = get_client()
    owner, repo = project.repo.split("/")
    targets: list[MonitorTarget] = []
    # state=open の一覧をページネーションで全件取得する
    page = 1
    while True:
        items = client.rest.issues.list_for_repo(
            owner=owner, repo=repo, state="open", per_page=_PER_PAGE, page=page
        ).parsed_data
        targets.extend(to_target(item) for item in items)
        if len(items) < _PER_PAGE:
            break
        page += 1
    # Issue 一覧は PR の base / head を持たないため、PR 一覧から補う
    # （base の連鎖を辿る処理が周期内で追加の API を呼ばずに済む）
    refs = _list_pr_refs(project)
    return [
        replace(t, base_ref=refs[t.number][0], head_ref=refs[t.number][1])
        if isinstance(t, PullRequest) and t.number in refs
        else t
        for t in targets
    ]


def _list_pr_refs(project: MonitoredProject) -> dict[int, tuple[str, str]]:
    """open PR の番号 → (base ブランチ, head ブランチ) を全件取得する。"""
    client = get_client()
    owner, repo = project.repo.split("/")
    refs: dict[int, tuple[str, str]] = {}
    page = 1
    while True:
        items = client.rest.pulls.list(
            owner=owner, repo=repo, state="open", per_page=_PER_PAGE, page=page
        ).parsed_data
        for item in items:
            refs[item.number] = (item.base.ref, item.head.ref)
        if len(items) < _PER_PAGE:
            break
        page += 1
    return refs


def to_target(item: object) -> MonitorTarget:
    """API 応答の 1 要素をドメインモデルに変換する。"""
    labels = [getattr(label, "name", label) for label in (item.labels or [])]
    assignees = [assignee.login for assignee in (item.assignees or [])]
    # pull_request キーを持つ場合、本文から linked_issue_numbers を抽出して PR にする
    # （githubkit は欠損フィールドを UNSET（偽値）にするため真偽値で判定する）
    if getattr(item, "pull_request", None):
        base = getattr(item, "base", None)
        return PullRequest(
            number=item.number,
            state=item.state,
            draft=bool(getattr(item, "draft", True)),
            labels=labels,
            assignees=assignees,
            linked_issue_numbers=_parse_linked_issue_numbers(item.body or ""),
            # 一覧 API は base を持たないため、単体取得の応答でだけ値が入る
            base_ref=getattr(base, "ref", "") if base else "",
        )
    return Issue(number=item.number, state=item.state, labels=labels, assignees=assignees)


def _parse_linked_issue_numbers(body: str) -> list[int]:
    """PR 本文の `## 紐づく Issue` セクションから Issue 番号を抽出する。"""
    # セクションを取り出す（無い場合は空リストを返す）
    match = re.search(r"^## 紐づく Issue\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
    if match is None:
        return []
    # #N 参照を重複なし・出現順で抽出する
    numbers: list[int] = []
    for raw in re.findall(r"#(\d+)", match.group(1)):
        number = int(raw)
        if number not in numbers:
            numbers.append(number)
    return numbers

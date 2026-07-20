"""処理中ラベルの付け外し。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

from ai_monitor.integrations.github.client import get_client
from ai_monitor.shared.settings import MonitoredProject
from ai_monitor.shared.types import LabelName


def add_label(project: MonitoredProject, number: int, label: LabelName) -> None:
    """対象へラベルを 1 つ付与する。"""
    owner, repo = project.repo.split("/")
    get_client().rest.issues.add_labels(owner=owner, repo=repo, issue_number=number, labels=[label])


def remove_label(project: MonitoredProject, number: int, label: LabelName) -> None:
    """対象からラベルを 1 つ除去する（未付与は無視する冪等操作）。"""
    owner, repo = project.repo.split("/")
    try:
        get_client().rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name=label)
    except RequestFailed as exc:
        # 未付与による 404 は無視する
        if exc.response.status_code != 404:
            raise

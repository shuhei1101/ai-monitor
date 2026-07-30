"""githubkit でラベル API を叩く薄いラッパー。"""
from __future__ import annotations

from ai_monitor.integrations.github.client import get_client
from ai_monitor.setup_labels.sync import LABELS_PER_PAGE, LabelSpec


def list_labels(repo: str) -> list[LabelSpec]:
    """リポジトリのラベルをページングを解決して全件取得する。"""
    # repo を owner と name に分割する
    owner, name = repo.split("/", 1)
    specs: list[LabelSpec] = []
    page = 1
    # ラベル一覧 API を 100 件ずつページングしながら全件取得する
    while True:
        labels = get_client().rest.issues.list_labels_for_repo(
            owner=owner, repo=name, per_page=LABELS_PER_PAGE, page=page
        ).parsed_data
        # 各ラベルを LabelSpec に変換する（説明が None なら空文字にする）
        specs.extend(
            LabelSpec(name=label.name, color=label.color, description=label.description or "")
            for label in labels
        )
        # 1 ページ分に満たなければ最終ページ
        if len(labels) < LABELS_PER_PAGE:
            return specs
        page += 1


def create_label(repo: str, spec: LabelSpec) -> None:
    """ラベルを 1 件作成する。"""
    # repo を owner と name に分割する
    owner, name = repo.split("/", 1)
    # ラベル作成 API に名前・色・説明を渡して呼ぶ
    get_client().rest.issues.create_label(
        owner=owner, repo=name, name=spec.name, color=spec.color, description=spec.description
    )


def update_label(repo: str, spec: LabelSpec) -> None:
    """既存ラベルの色と説明を更新する。"""
    # repo を owner と name に分割する
    owner, name = repo.split("/", 1)
    # ラベル更新 API に spec.name を対象として色と説明を渡して呼ぶ（名前は変更しない）
    get_client().rest.issues.update_label(
        owner=owner, repo=name, name=spec.name, color=spec.color, description=spec.description
    )

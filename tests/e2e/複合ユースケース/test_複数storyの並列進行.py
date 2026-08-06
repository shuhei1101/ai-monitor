"""複合UC「複数storyの並列進行」の E2E テスト。"""
from __future__ import annotations

from pathlib import Path

import yaml

from tests.e2e.エスカレーション import approve, issue, label_names, waiting_for_user

INTAKE_TITLE = "タスク管理の操作追加"
INTAKE_BODY = "タスクの編集と削除をできるようにする。"

EPIC_TITLE = "タスク管理の操作追加"
EPIC_BODY = """## 概要

一覧のタスクに対して、編集と削除の操作を提供する。

## 背景

現状はタスクの新規作成のみで、登録後の修正も取り消しもできない。

## ユースケース一覧

| ユースケース | 変更種別 | 概要 | 対応 story | 補足 |
| --- | --- | --- | --- | --- |
| タスク編集 | 変更 | 一覧から編集画面へ遷移して編集内容を保存する | 作成済み | - |
| タスク削除 | 変更 | 一覧から対象タスクを選んで削除する | 作成済み | - |

## 横断要件

- 保存・削除とも既存 API を利用する
"""

STORY_TITLES = ["タスク編集", "タスク削除"]
SECTIONS = ["## 前提条件", "## 概要", "## 背景", "## ユースケース要件"]


def _conductor_sessions(state_path: Path) -> list[int]:
    """モニター台帳にある story-conductor セッションの主番号一覧を返す。"""
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    return [e["primary_number"] for e in entries if e["agent_name"] == "story-conductor"]


def _story_pr(gh_live, owner: str, repo: str, story_number: int):
    """story に紐づく open PR のうち `確認:single-scenario-writer` が付いたものを返す。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    for pr in pulls:
        if f"#{story_number}" not in (pr.body or ""):
            continue
        if "確認:single-scenario-writer" in {label.name for label in pr.labels}:
            return pr
    return None


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, story_issue_factory,
    wait_until, e2e_state_path,
):
    """2 story の同時起票から双方の Draft PR 到達までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: ユースケース一覧に 2 UC を持つ epic + epic Draft PR
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-ops-{epic.number}/base"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    # 準備: 衝突面が重ならない story を 2 件同時に起票する（2 セッションの同時起動を誘発）
    stories = [story_issue_factory(epic.number, title) for title in STORY_TITLES]

    # 実行: 2 件とも要件確定の待機（議論中 + assignee=ユーザー）に入るのを待つ
    def _both_waiting():
        snapshots = [issue(gh_live, owner, repo, story.number) for story in stories]
        return snapshots if all(waiting_for_user(data) for data in snapshots) else None

    snapshots = wait_until(
        _both_waiting, timeout_sec=3600, message="2 story とも要件確定の完了（議論中 + assignee）"
    )

    # 検証: story-conductor のセッションが 2 件並んでいる（同時稼働）
    registered = _conductor_sessions(e2e_state_path)
    for story in stories:
        assert story.number in registered, f"story #{story.number} のセッションが台帳にない: {registered}"

    # 検証: 2 story とも本文に 4 セクションが揃い、背景に親 epic と対応 UC が入っている
    for data, title in zip(snapshots, STORY_TITLES):
        body = (data.body or "").replace("\r\n", "\n")
        for section in SECTIONS:
            assert section in body, f"story #{data.number} の本文に {section} がない"
        assert f"#{epic.number}" in body, f"story #{data.number} の背景に親 epic の番号がない"
        assert title in body, f"story #{data.number} の背景に対応する UC 名がない"

    # 実行: 2 件ともユーザー承認（議論中 除去 + assignee 外し）
    for data in snapshots:
        approve(gh_live, owner, repo, data.number, data.assignees)

    # 実行: 2 件とも完了処理（story Draft PR 作成 + 確認:single-scenario-writer 付与）を待つ
    def _both_drafted():
        prs = []
        for story in stories:
            # 差し戻し中（確認:story-conductor が残っている）は未完了として扱う
            if "確認:story-conductor" in label_names(issue(gh_live, owner, repo, story.number)):
                return None
            pr = _story_pr(gh_live, owner, repo, story.number)
            if pr is None:
                return None
            prs.append(pr)
        return prs

    prs = wait_until(
        _both_drafted, timeout_sec=3600, message="2 story とも Draft PR の作成（確認:single-scenario-writer）"
    )

    # 検証: どちらの PR も Draft で base が epic ブランチ
    assert [pr.draft for pr in prs] == [True, True], "story PR が Draft でない"
    for pr in prs:
        assert pr.base.ref == epic_branch, f"base が親 epic ブランチでない: {pr.base.ref}"
    assert len({pr.number for pr in prs}) == 2, "2 story が同じ PR を指している"

"""「実現可能性PoC検証」の E2E テスト。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

import server

INTAKE_TITLE = "Python pathlib での一時ファイル生成 PoC"
INTAKE_BODY = "epic の成立に必要な一時ファイル生成機構を検証する。"

EPIC_TITLE = "一時ファイル生成機構"
EPIC_BODY = """## 前提条件

なし

## 概要

Python 標準ライブラリで一時ファイルを生成・書き込み・読み戻しできることを確認する。

## 背景

外部依存を最小化するため、標準ライブラリのみで一時ファイルを扱う技術基盤の成立を検証する。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| 一時ファイル生成 | pathlib で一時ファイルを生成する | 未起票 |

## 横断要件

- 標準ライブラリのみで実装できること

## PoC 結果

（未記入）
"""

INSTRUCTION_BODY = """> from: @epic-conductor
> to: @epic-poc-runner

epic の実現可能性 PoC を発注します。

**検証テーマ:** Python `pathlib.Path` を使った一時ファイルの生成・書き込み・読み戻しが Python 3.12 標準ライブラリのみで成立するか。

**成立条件の想定:**
- `Path.write_text()` で一時ファイルへ文字列を書き込める
- `Path.read_text()` で書き込んだ文字列を復元できる
- 外部依存パッケージなし
"""


def test_normal(monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, wait_until, tmp_path):
    """方針固め → 承認 → 検証実行 → 承認 → 完了処理までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get_issue(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: 5 セクション + `## PoC 結果`（空）を持つ epic Issue（確認ラベルなし）+ 親 intake
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic"]
    )
    # 準備: PoC Draft PR（本文は `## 紐づく Issue` のみ）を作成
    pr = epic_pr_factory(
        branch=f"poc/epic/tempfile-{epic.number}",
        title=f"PoC: 一時ファイル生成機構（epic #{epic.number}）",
        body=f"## 紐づく Issue\n\n- #{epic.number}\n",
    )
    # 準備: epic-conductor の指示コメントを投稿してから確認ラベルを付ける
    instruction = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr.number, body=INSTRUCTION_BODY
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:epic-poc-runner"]
    )

    # 実行: モニターの polling 検知 → 方針固めの完了（議論中 + assignee）を待つ
    def _plan_done():
        data = _get_issue(pr.number)
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    pr_data = wait_until(_plan_done, timeout_sec=1200, message="方針固めの完了（議論中 + assignee）")

    # 検証: PoC PR 本文に 3 セクションが揃い、指示コメントは未 Resolve のまま
    body = (pr_data.body or "").replace("\r\n", "\n")
    for section in ("## リスク仮説", "## 検証構成", "## 成功条件"):
        assert section in body, f"PR 本文に {section} がない"

    # 実行: 検証構成のユーザー承認を再現（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in pr_data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    # 実行: 検証実行の完了（結果報告 + 議論中 + assignee 再セット）を待つ
    def _result_reported():
        data = _get_issue(pr.number)
        labels = {label.name for label in data.labels}
        body_now = (data.body or "").replace("\r\n", "\n")
        if "議論中" in labels and data.assignees and "## 検証結果" in body_now:
            return data
        return None

    pr_data = wait_until(_result_reported, timeout_sec=1800, message="検証実行の完了（検証結果記入 + 議論中 + assignee）")

    # 検証: PoC PR 本文に検証結果と最小再現コードが揃っている
    body = (pr_data.body or "").replace("\r\n", "\n")
    assert "## 検証結果" in body
    assert "## 最小再現コード" in body

    # 実行: 結果のユーザー承認を再現（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in pr_data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    # 実行: 完了処理の完了（PoC PR の 確認:epic-poc-runner 除去）を待つ
    def _wrapped_up():
        data = _get_issue(pr.number)
        labels = {label.name for label in data.labels}
        return data if not any(name.startswith("確認:") for name in labels) else None

    wait_until(_wrapped_up, timeout_sec=1200, message="完了処理の完了（PoC PR の 確認:* 除去）")

    # 検証: PoC PR は open のまま自ラベルだけ除去されている
    pr_data = _get_issue(pr.number)
    assert pr_data.state == "open"

    # 検証: 親 epic Issue 本文の `## PoC 結果` に検証構成 / 成功条件 / 結果 / PoC PR リンクが記録されている
    epic_data = _get_issue(epic.number)
    epic_body = (epic_data.body or "").replace("\r\n", "\n")
    assert "## PoC 結果" in epic_body
    # 「未記入」から記入済みへ更新されている（プレースホルダーが残っていない）
    poc_section = epic_body.split("## PoC 結果", 1)[1]
    assert "（未記入）" not in poc_section
    assert f"#{pr.number}" in poc_section, "PoC PR リンクが記載されていない"

    # 検証: 親 epic Issue に 確認:epic-conductor + @epic-conductor 宛の完了報告コメント（未 Resolve）が付与・投稿されている
    epic_labels = {label.name for label in epic_data.labels}
    assert "確認:epic-conductor" in epic_labels
    epic_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=epic.number).parsed_data
    completion = [c for c in epic_comments if "> to: @epic-conductor" in c.body]
    assert completion, "@epic-conductor 宛の完了報告コメントが投稿されていない"
    assert not server._is_minimized(completion[-1].node_id), "完了報告が Resolve されてしまっている"

    # 検証: PoC PR の自分宛コメント（指示コメント + 自身の投稿）が全て Resolve 済み
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    for comment in pr_comments:
        assert server._is_minimized(comment.node_id), f"PoC PR コメント {comment.html_url} が未 Resolve"
    # 指示コメント（instruction）も Resolve 対象に含まれていることを念のため確認
    assert server._is_minimized(instruction.node_id), "指示コメントが未 Resolve"

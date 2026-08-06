"""「Issue分解と子PR作成」の E2E テスト。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server

INTAKE_TITLE = "通知機能の追加 + README の typo 修正"
INTAKE_BODY = """タスクの期限が近づいたらメールで通知する機能を追加したいです。

- 通知の on/off はユーザー設定で切り替えたい
- 通知タイミング（1 日前 / 1 時間前）も選べるようにしたい

あと README のセットアップ手順に typo があるので、ついでに直しておいてください。
"""


def _issue(gh_live, owner, repo, number):
    """Issue / PR の最新状態を返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def _labels(data) -> set[str]:
    """ラベル名の集合を返す。"""
    return {label.name for label in data.labels}


def _comments(gh_live, owner, repo, number) -> list:
    """コメント一覧を返す。"""
    return list(
        gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=number).parsed_data
    )


def _child_prs(gh_live, owner, repo, number) -> list:
    """本文で指定番号を参照している open PR を返す（分解で作られた子 PR）。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    return [pr for pr in pulls if f"#{number}" in (pr.body or "")]


def _approve(gh_live, owner, repo, number, assignees) -> None:
    """ユーザー承認を再現する（議論中 除去 + assignee 外し）。"""
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name="議論中")
    except RequestFailed:
        pass
    for assignee in assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def test_normal(monitor, gh_live, repo_ctx, intake_issue_factory, wait_until, nonce):
    """Issue 起票 → 分解 → 承認 → 子 PR 作成の一連を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: ユーザー起票の intake Issue（確認ラベル付き・assignee なし）
    issue = intake_issue_factory(title=f"{INTAKE_TITLE}（{nonce}）", body=INTAKE_BODY)

    # 実行: モニターの検知 → 分解判定（初回）の完了（議論中 + assignee）を待つ
    def _first_turn_done():
        data = _issue(gh_live, owner, repo, issue.number)
        return data if "議論中" in _labels(data) and data.assignees else None

    data = wait_until(_first_turn_done, timeout_sec=1200, message="分解判定（初回）の完了")

    # 検証: 分解案の投稿と待機状態（layer / type ラベル・本文は不変）
    labels = _labels(data)
    assert "layer:intake" in labels
    assert any(name.startswith("type:") for name in labels)
    assert _comments(gh_live, owner, repo, issue.number), "分解案コメントが投稿されていない"
    assert data.body.replace("\r\n", "\n") == INTAKE_BODY

    # 実行: ユーザー承認を再現して 子PR作成（完了処理）の完了（確認:* 除去）を待つ
    _approve(gh_live, owner, repo, issue.number, data.assignees)

    def _completed():
        data = _issue(gh_live, owner, repo, issue.number)
        if any(name.startswith("確認:") for name in _labels(data)):
            return None
        children = _child_prs(gh_live, owner, repo, issue.number)
        return (data, children) if children else None

    data, children = wait_until(
        _completed, timeout_sec=1800, message="子PR作成（完了処理）の完了（確認:* 除去 + 子 PR）"
    )

    # 検証: 承認された案と同数のブランチと Draft PR が master の上に作られている
    confirmed = [
        pr for pr in children
        if "確認:epic-conductor" in _labels(_issue(gh_live, owner, repo, pr.number))
    ]
    assert confirmed, "確認:epic-conductor が付いた PR が 1 件も無い"
    for pr in children:
        assert pr.draft, f"#{pr.number} が Draft でない"
        assert pr.base.ref == "master", f"#{pr.number} の base が master でない: {pr.base.ref}"
        assert f"#{issue.number}" in (pr.body or ""), f"#{pr.number} の 紐づく Issue に intake がない"
        pr_labels = _labels(_issue(gh_live, owner, repo, pr.number))
        assert "layer:epic" in pr_labels, f"#{pr.number} に layer:epic がない: {sorted(pr_labels)}"

    # 検証: 確認ラベルが付いていない PR に着手の痕跡が無い（着手順は確認ラベルで表す）
    for pr in children:
        pr_now = _issue(gh_live, owner, repo, pr.number)
        if "確認:epic-conductor" in _labels(pr_now):
            continue
        assert "議論中" not in _labels(pr_now), f"#{pr.number} に着手の痕跡（議論中）がある"
        assert not pr_now.assignees, f"#{pr.number} に着手の痕跡（assignee）がある"

    # 検証: intake Issue は本文不変のまま layer:intake + type:* が残り open のまま
    labels = _labels(data)
    assert "layer:intake" in labels
    assert any(name.startswith("type:") for name in labels)
    assert data.body.replace("\r\n", "\n") == INTAKE_BODY
    assert data.state == "open"

    # 検証: エージェント投稿の自分宛コメントが全て Resolve 済み
    agent_comments = [
        c for c in _comments(gh_live, owner, repo, issue.number) if c.body.lstrip().startswith("> from:")
    ]
    assert agent_comments, "エージェントのコメントが見つからない"
    for comment in agent_comments:
        assert server._is_minimized(comment.node_id), f"コメント {comment.html_url} が未 Resolve"


DUPLICATE_TITLE = "タスク期限のメール通知を追加したい"
EXISTING_BODY = """タスクの期限が近づいたらメールで通知する機能を追加したいです。

- 通知の on/off はユーザー設定で切り替えたい
"""
DUPLICATE_BODY = """期限が近いタスクをメールで知らせてほしいです。

- 通知タイミング（1 日前 / 1 時間前）も選べるようにしたい
"""

# 統合先にだけ現れる固有内容（転記されたことの目印）
DUPLICATE_MARKER = "1 時間前"


def _assert_closed_as_duplicate(gh_live, owner, repo, number, target_number, data) -> None:
    """重複クローズの共通検証（not_planned + 統合先リンク + ユーザー確認なし）。"""
    assert data.state == "closed"
    assert data.state_reason == "not_planned", f"クローズ理由が not_planned でない: {data.state_reason}"
    own = _comments(gh_live, owner, repo, number)
    assert any(f"#{target_number}" in c.body for c in own), (
        f"統合先 #{target_number} へのリンクが残っていない"
    )
    assert "議論中" not in _labels(data)
    assert not data.assignees


def test_normal_when_duplicated_pr(
    monitor, gh_live, repo_ctx, intake_issue_factory, issue_factory, epic_pr_factory, wait_until,
    nonce,
):
    """目的が重複する既存 PR への統合とクローズを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: 同じ目的で進行中の既存 epic PR（担当エージェントの確認ラベル付き）
    title = f"{DUPLICATE_TITLE}（{nonce}）"
    seed = issue_factory(title=title, body=EXISTING_BODY, labels=["layer:intake", "type:feat"])
    existing = epic_pr_factory(
        f"feat/epic/task-notify-{seed.number}/base", title,
        f"## 紐づく Issue\n\n- #{seed.number}\n",
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=existing.number,
        labels=["layer:epic", "確認:epic-conductor"],
    )
    existing_labels_before = _labels(_issue(gh_live, owner, repo, existing.number))

    # 準備: 同じ目的の intake Issue（確認ラベル付き・assignee なし）
    issue = intake_issue_factory(title=title, body=DUPLICATE_BODY)

    # 実行: 統合判定によるクローズを待つ（ユーザーの確認は挟まれない）
    def _merged():
        data = _issue(gh_live, owner, repo, issue.number)
        return data if data.state == "closed" else None

    data = wait_until(_merged, timeout_sec=1200, message="既存 PR への統合（intake Issue の closed）")

    # 検証: 子 PR が作られていない
    assert not _child_prs(gh_live, owner, repo, issue.number), "子 PR が作られている"

    # 検証: 重複クローズの形（not_planned + 統合先リンク + ユーザー確認なし）
    _assert_closed_as_duplicate(gh_live, owner, repo, issue.number, existing.number, data)

    # 検証: 既存 PR に固有内容と出典が転記されている
    transferred = [
        c for c in _comments(gh_live, owner, repo, existing.number)
        if c.body.lstrip().startswith("> from:")
    ]
    assert transferred, "統合先に転記コメントが投稿されていない"
    joined = "\n".join(c.body for c in transferred)
    assert DUPLICATE_MARKER in joined, f"固有内容が転記されていない: {joined[:200]}"
    assert f"#{issue.number}" in joined, "出典（intake Issue 番号）が書かれていない"

    # 検証: 既存 PR のラベルと担当が変わっていない
    after = _issue(gh_live, owner, repo, existing.number)
    assert _labels(after) == existing_labels_before
    assert not after.assignees


RULE_PAGE = "docs/rules/markdown/マークダウン編集.md"
RULE_EXCERPT = "テーブルの No / # カラムについて: 連番だけの No / # カラムは付けない"
RULE_TITLE = "連番の No 列を付けない規約が実態と合っていない"
RULE_POINT = "Issue / PR 番号を載せる表まで No 列を落としてしまい、参照ができなくなっています。"


def _rule_issue_body(agent: str, repo: str, number: int) -> str:
    """ルール改修 Issue の本文を組み立てる（MCP ツールが作る形と同じ）。"""
    return (
        "## 報告元\n\n"
        "| 項目 | 値 |\n| --- | --- |\n"
        "| プロジェクト | ai-monitor-e2e |\n"
        f"| エージェント | {agent} |\n"
        f"| 対象 | {repo}#{number} |\n\n"
        f"## 対象ルール\n\n- `{RULE_PAGE}`\n\n> {RULE_EXCERPT}\n\n"
        f"## 指摘の内容\n\n{RULE_POINT}\n"
    )


def test_normal_when_duplicated_issue(
    monitor, gh_live, repo_ctx, issue_factory, wait_until, nonce
):
    """同じ内容の既存ルール改修 Issue への統合（転記なし）を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    slug = f"{owner}/{repo}"

    # 準備: 同じ対象ルール・同じ指摘の既存ルール改修 Issue（報告元だけが違う）
    existing = issue_factory(
        title=f"{RULE_TITLE}（{nonce}）", body=_rule_issue_body("architect", slug, 101),
        labels=["AI不具合報告"],
    )
    existing_labels_before = _labels(_issue(gh_live, owner, repo, existing.number))

    # 準備: ユーザーがトリアージへ回した同内容のルール改修 Issue
    target = issue_factory(
        title=f"{RULE_TITLE}（{nonce}）", body=_rule_issue_body("tester", slug, 202),
        labels=["AI不具合報告", "確認:intake-issue-triager"],
    )

    # 実行: 重複判定によるクローズを待つ
    def _closed():
        data = _issue(gh_live, owner, repo, target.number)
        return data if data.state == "closed" else None

    data = wait_until(_closed, timeout_sec=1200, message="既存 Issue への統合（対象 Issue の closed）")

    # 検証: 子 PR が作られていない
    assert not _child_prs(gh_live, owner, repo, target.number), "子 PR が作られている"

    # 検証: 重複クローズの形
    _assert_closed_as_duplicate(gh_live, owner, repo, target.number, existing.number, data)

    # 検証: 転記する内容が無いので既存 Issue にコメントが投稿されていない
    assert not _comments(gh_live, owner, repo, existing.number), (
        "追加情報が無いのに既存 Issue へコメントが投稿されている"
    )

    # 検証: 既存 Issue のラベルと担当が変わっていない
    after = _issue(gh_live, owner, repo, existing.number)
    assert _labels(after) == existing_labels_before
    assert not after.assignees


DEFECT_PAGE = "エージェント/single-scenario-writer/フェーズ/統合テスト割り当て.md"
DEFECT_TITLE = "統合テスト割り当ての手順が存在しない MCP ツールを指している"
DEFECT_EVENT = "`### テストの割り当て` が MCP `assign_tests` を呼ぶよう書かれていますが、そのツールがありません。"

# 対象 Issue にだけある追加情報（転記されたことの目印）
DEFECT_WORKAROUND = "comment で担当へ依頼し add_labels で確認ラベルを付けて代替しました。"


def _defect_issue_body(agent: str, repo: str, number: int, workaround: str) -> str:
    """不具合 Issue の本文を組み立てる（MCP ツールが作る形と同じ）。"""
    return (
        "## 報告元\n\n"
        "| 項目 | 値 |\n| --- | --- |\n"
        "| プロジェクト | ai-monitor-e2e |\n"
        f"| エージェント | {agent} |\n"
        f"| 対象 | {repo}#{number} |\n\n"
        f"## 該当ページ\n\n- `{DEFECT_PAGE}`\n\n"
        f"## 事象\n\n{DEFECT_EVENT}\n\n"
        f"## 回避策\n\n{workaround}\n"
    )


def test_normal_when_duplicated_issue_with_extra(
    monitor, gh_live, repo_ctx, issue_factory, wait_until, nonce
):
    """追加情報を持つ重複不具合 Issue の追記統合を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    slug = f"{owner}/{repo}"

    # 準備: 同じ事象で回避策を持たない既存の不具合 Issue
    existing = issue_factory(
        title=f"{DEFECT_TITLE}（{nonce}）",
        body=_defect_issue_body("single-scenario-writer", slug, 303, "なし（回避できず作業を中断した）"),
        labels=["AI不具合報告"],
    )
    existing_labels_before = _labels(_issue(gh_live, owner, repo, existing.number))

    # 準備: 同じ事象で回避策を持つ不具合 Issue（追加情報ありの分岐を誘発）
    target = issue_factory(
        title=f"{DEFECT_TITLE}（{nonce}）",
        body=_defect_issue_body("complex-scenario-writer", slug, 404, DEFECT_WORKAROUND),
        labels=["AI不具合報告", "確認:intake-issue-triager"],
    )

    # 実行: 重複判定によるクローズを待つ
    def _closed():
        data = _issue(gh_live, owner, repo, target.number)
        return data if data.state == "closed" else None

    data = wait_until(_closed, timeout_sec=1200, message="既存 Issue への統合（対象 Issue の closed）")

    # 検証: 子 PR が作られていない
    assert not _child_prs(gh_live, owner, repo, target.number), "子 PR が作られている"

    # 検証: 重複クローズの形
    _assert_closed_as_duplicate(gh_live, owner, repo, target.number, existing.number, data)

    # 検証: 既存 Issue に追加情報と出典が追記されている
    transferred = [
        c for c in _comments(gh_live, owner, repo, existing.number)
        if c.body.lstrip().startswith("> from:")
    ]
    assert transferred, "統合先に追記コメントが投稿されていない"
    joined = "\n".join(c.body for c in transferred)
    assert "回避策" in joined or "add_labels" in joined, f"追加情報が転記されていない: {joined[:200]}"
    assert f"#{target.number}" in joined, "出典（対象 Issue 番号）が書かれていない"

    # 検証: 既存 Issue のラベルと担当が変わっていない
    after = _issue(gh_live, owner, repo, existing.number)
    assert _labels(after) == existing_labels_before
    assert not after.assignees

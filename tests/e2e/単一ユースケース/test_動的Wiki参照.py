"""「動的Wiki参照」の E2E テスト。"""
from __future__ import annotations

INTAKE_TITLE = "顧客一覧に絞り込みを追加したい"
INTAKE_BODY = """顧客一覧画面で条件を指定して絞り込めるようにしたいです。

- 会社名・担当者名で絞り込みたい
- 絞り込み条件は URL に残して共有できるようにしたい
"""

# 事前注入されない Wiki ページにだけ書かれている検証用フレーズ
MARKER = "分解根拠:"

FEEDBACK = """この分解案について、プロジェクトの Wiki に分解時の決まりごとが書かれているはずなので、
関連する Wiki ページを探して読んだうえで案を修正してください。
"""


def test_normal(monitor, gh_live, repo_ctx, intake_issue_factory, wait_until):
    """索引経由で事前注入外の Wiki を読み、応答へ反映する一連を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _list_comments():
        return gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=issue.number).parsed_data

    # 準備: ユーザー起票の intake Issue（確認ラベル付き・assignee なし）
    issue = intake_issue_factory(title=INTAKE_TITLE, body=INTAKE_BODY)

    # 分解判定（初回）の完了を待つ（議論中 + assignee=ユーザー の待機状態）
    def _first_turn_done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=issue.number).parsed_data
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    data = wait_until(_first_turn_done, timeout_sec=1200, message="分解判定（初回）の完了（議論中 + assignee）")

    # 実行: Wiki パスを伝えずに「関連 Wiki を参照して修正」とだけ指示し、assignee を外す
    gh_live.rest.issues.create_comment(owner=owner, repo=repo, issue_number=issue.number, body=FEEDBACK)
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=issue.number, assignees=[assignee.login]
        )

    # 応答ループの再待機を待つ（返信は既存コメントへの追記なので assignee 再設定で検知する）
    def _replied():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=issue.number).parsed_data
        return data if data.assignees else None

    wait_until(_replied, timeout_sec=1200, message="応答ループの完了（assignee 再設定）")

    # 検証: エージェントの返信に対象 Wiki ページの検証用フレーズが含まれている
    agent_bodies = [c.body for c in _list_comments() if c.body.lstrip().startswith("> from:")]
    assert agent_bodies, "エージェントのコメントが見つからない"
    assert any(MARKER in body for body in agent_bodies), (
        f"返信に Wiki の検証用フレーズ {MARKER!r} が含まれていない"
    )

    # 検証: 議論中 のまま assignee=ユーザー で再待機に入っている
    data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=issue.number).parsed_data
    labels = {label.name for label in data.labels}
    assert "議論中" in labels
    assert data.assignees

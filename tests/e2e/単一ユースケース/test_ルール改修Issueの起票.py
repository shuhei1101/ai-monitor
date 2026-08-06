"""「ルール改修Issueの起票」の E2E テスト。

ルール起因の指摘を決定的に作るため、intake-issue-triager が分解案を投稿して待機した後に
「ルールの記述と反対の書き方」を求めるユーザーコメントを入れる。

起票先（my-plugins / ai-monitor）はどちらも sandbox へ上書きして実行するため、
どちらのツールを選んだかは起票された本文の `## 対象ルール` のページパスで判定する
（`docs/rules/` 配下なら my-plugins・`docs/wiki/` 配下なら ai-monitor）。
"""
from __future__ import annotations

import pytest

from tests.e2e.エスカレーション import issue, label_names, me

# 起票されるのはテストデータなので、起票先を sandbox へ上書きした別実行で回す
pytestmark = pytest.mark.defect_report

INTAKE_TITLE = "タスクの並び替え機能を追加したい"
INTAKE_BODY = """一覧のタスクをドラッグで並び替えられるようにしたいです。

- 並び順はユーザーごとに保存したい
"""

# マークダウン編集規約（my-plugins の `docs/rules/` 配下）の記述と反対を求めるフィードバック
FEEDBACK_RULE_WRONG = """分解案の表ですが、行を参照しやすいように連番の No 列を先頭に付けてください。
以降もこの書き方で統一してください。
"""

# ai-monitor の手順書に規定が無い書き方を求めるフィードバック
FEEDBACK_RULE_MISSING = """分解案の表に、各作業単位の想定工数（人日）の列も足してください。
工数が分からないと着手順を判断できません。
"""

# 規約どおりに書かれている内容を求めるフィードバック（ルール起因ではない）
FEEDBACK_NOT_RULE_CAUSED = """分解案の説明文は 1 文ごとに改行してください。
長い 1 行になっていると読みにくいです。
"""


def _ai_report_numbers(gh_live, owner: str, repo: str) -> set[int]:
    """sandbox の open な `AI不具合報告` Issue の番号集合を返す。"""
    listed = gh_live.rest.issues.list_for_repo(
        owner=owner, repo=repo, state="open", labels="AI不具合報告", per_page=100
    ).parsed_data
    return {data.number for data in listed if data.pull_request is None}


def _drive_to_waiting(gh_live, owner, repo, intake_issue_factory, wait_until, nonce):
    """intake Issue を分解判定の応答ループ待機（議論中 + assignee=ユーザー）まで進める。"""
    issue_data = intake_issue_factory(title=f"{INTAKE_TITLE}（{nonce}）", body=INTAKE_BODY)

    def _waiting():
        data = issue(gh_live, owner, repo, issue_data.number)
        return data if "議論中" in label_names(data) and data.assignees else None

    wait_until(_waiting, timeout_sec=1200, message="分解判定（初回）の待機入り")
    return issue_data


def _send_feedback(gh_live, owner, repo, number, body, login) -> None:
    """ユーザーのフィードバックコメント投稿 + assignee 外しを再現する。"""
    gh_live.rest.issues.create_comment(owner=owner, repo=repo, issue_number=number, body=body)
    gh_live.rest.issues.remove_assignees(
        owner=owner, repo=repo, issue_number=number, assignees=[login]
    )


def _wait_reported(gh_live, owner, repo, before, wait_until, *, message):
    """新しく起票された `AI不具合報告` Issue を 1 件返す。"""

    def _appeared():
        added = _ai_report_numbers(gh_live, owner, repo) - before
        return added or None

    added = wait_until(_appeared, timeout_sec=1200, message=message)
    return gh_live.rest.issues.get(
        owner=owner, repo=repo, issue_number=sorted(added)[0]
    ).parsed_data


def _assert_report_shape(gh_live, owner, repo, reported, intake_number, login) -> None:
    """ルール改修 Issue の共通の形を検証する。"""
    labels = label_names(reported)
    assert "AI不具合報告" in labels, f"AI不具合報告 ラベルがない: {sorted(labels)}"
    assert not [name for name in labels if name.startswith("確認:")], (
        f"確認ラベルが付いている（承認前に改修フローが動き出す）: {sorted(labels)}"
    )
    assert [a.login for a in reported.assignees] == [login], (
        f"assignee がユーザーでない: {[a.login for a in reported.assignees]}"
    )
    body = (reported.body or "").replace("\r\n", "\n")
    assert "## 報告元" in body, f"報告元セクションがない: {body[:200]}"
    assert "## 対象ルール" in body, f"対象ルールセクションがない: {body[:200]}"
    assert "## 指摘の内容" in body, f"指摘の内容セクションがない: {body[:200]}"
    assert f"#{intake_number}" in body, "報告元に担当している Issue の番号が入っていない"


def _rule_page(body: str) -> str:
    """`## 対象ルール` に書かれたページパスを返す。"""
    section = (body or "").replace("\r\n", "\n").split("## 対象ルール", 1)[1].split("\n## ", 1)[0]
    for line in section.splitlines():
        if line.strip().startswith("-"):
            return line.strip().lstrip("- ").strip("`")
    return ""


def _assert_loop_continued(gh_live, owner, repo, number, wait_until) -> None:
    """本来の作業（応答ループ）が止まらず待機へ戻ることを確認する。"""

    def _replied():
        data = issue(gh_live, owner, repo, number)
        return data if data.assignees and "議論中" in label_names(data) else None

    wait_until(_replied, timeout_sec=1200, message="指摘を反映した応答ループの継続")


def test_normal_when_rule_wrong(
    monitor, gh_live, repo_ctx, intake_issue_factory, wait_until, nonce
):
    """ルールの記述が誤っている指摘から my-plugins へ起票する（正常系）。"""
    owner, repo = repo_ctx
    login = me(gh_live)

    # 準備: 応答ループ待機まで進めた intake Issue と、起票前の AI不具合報告 一覧
    target = _drive_to_waiting(gh_live, owner, repo, intake_issue_factory, wait_until, nonce)
    before = _ai_report_numbers(gh_live, owner, repo)

    # 実行: 規約の記述と反対を求めるフィードバックを送る
    _send_feedback(gh_live, owner, repo, target.number, FEEDBACK_RULE_WRONG, login)
    reported = _wait_reported(
        gh_live, owner, repo, before, wait_until, message="ルール改修 Issue の起票"
    )

    # 検証: 起票された Issue の形と、起票先の判断（言語 / フレームワークの規約側）
    _assert_report_shape(gh_live, owner, repo, reported, target.number, login)
    page = _rule_page(reported.body or "")
    assert page.startswith("docs/rules/"), f"起票先の判断が my-plugins 側になっていない: {page!r}"

    # 検証: 本来の作業が止まっていない
    _assert_loop_continued(gh_live, owner, repo, target.number, wait_until)


def test_normal_when_rule_missing(
    monitor, gh_live, repo_ctx, intake_issue_factory, wait_until, nonce
):
    """ルールに記述が無い指摘から ai-monitor へ起票する（正常系）。"""
    owner, repo = repo_ctx
    login = me(gh_live)

    # 準備: 応答ループ待機まで進めた intake Issue と、起票前の AI不具合報告 一覧
    target = _drive_to_waiting(gh_live, owner, repo, intake_issue_factory, wait_until, nonce)
    before = _ai_report_numbers(gh_live, owner, repo)

    # 実行: 手順書に規定が無い書き方を求めるフィードバックを送る
    _send_feedback(gh_live, owner, repo, target.number, FEEDBACK_RULE_MISSING, login)
    reported = _wait_reported(
        gh_live, owner, repo, before, wait_until, message="ルール改修 Issue の起票"
    )

    # 検証: 起票された Issue の形と、起票先の判断（手順書 / 規約 / テンプレート側）
    _assert_report_shape(gh_live, owner, repo, reported, target.number, login)
    page = _rule_page(reported.body or "")
    assert not page.startswith("docs/rules/"), f"起票先の判断が ai-monitor 側になっていない: {page!r}"

    # 検証: 本来の作業が止まっていない
    _assert_loop_continued(gh_live, owner, repo, target.number, wait_until)


def test_normal_when_not_rule_caused(
    monitor, gh_live, repo_ctx, intake_issue_factory, wait_until, nonce
):
    """ルール起因でない指摘では起票しない（正常系）。"""
    owner, repo = repo_ctx
    login = me(gh_live)

    # 準備: 応答ループ待機まで進めた intake Issue と、起票前の AI不具合報告 一覧
    target = _drive_to_waiting(gh_live, owner, repo, intake_issue_factory, wait_until, nonce)
    before = _ai_report_numbers(gh_live, owner, repo)

    # 実行: 規約どおりの内容を求めるフィードバックを送る
    _send_feedback(gh_live, owner, repo, target.number, FEEDBACK_NOT_RULE_CAUSED, login)

    # 検証: 応答ループが 1 往復して待機へ戻る
    _assert_loop_continued(gh_live, owner, repo, target.number, wait_until)

    # 検証: ルール改修 Issue が起票されていない
    added = _ai_report_numbers(gh_live, owner, repo) - before
    assert not added, f"ルール起因でないのに起票されている: {sorted(added)}"

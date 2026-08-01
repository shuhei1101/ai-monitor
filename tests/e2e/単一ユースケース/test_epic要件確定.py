"""「epic要件確定」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.epic起動 import (
    EPIC_SECTIONS,
    assert_comments_resolved,
    assert_linked_issue_only_body,
    drive_requirements,
)
from tests.e2e.ゲート応答 import open_prs_for
from tests.e2e.システム import watch_numbers
from tests.e2e.システム import SYSTEM_ISSUE_BODY, SYSTEM_TITLE
from tests.e2e.エスカレーション import comments

INTAKE_TITLE = "タスク期限のメール通知機能"
INTAKE_BODY = """タスクの期限が近づいたらメールで通知する機能を追加したいです。

- 通知の on/off はユーザー設定で切り替えたい
- 通知タイミング（1 日前 / 1 時間前）も選べるようにしたい
"""
EPIC_TITLE = "タスク期限のメール通知機能"


def _assert_requirements(gh_live, owner, repo, epic_number: int, first) -> None:
    """初回ターンの成果（本文 5 セクション・対応 story 未起票・確認質問コメント）を検証する。"""
    body = (first.body or "").replace("\r\n", "\n")
    for section in EPIC_SECTIONS:
        assert section in body, f"本文に {section} がない"
    assert "未起票" in body
    assert comments(gh_live, owner, repo, epic_number), "完了報告・確認質問コメントが投稿されていない"


def test_normal_when_no_poc_no_ui(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path):
    """epic 本文確定 → 承認 → epic Draft PR 作成 + complex-scenario-writer 引き継ぎを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 不要・画面変更なしと回答）
    first, _ = drive_requirements(
        gh_live, owner, repo, wait_until, epic.number,
        answer_body="A（PoC 不要）/ A（画面変更なし）でお願いします。",
    )
    _assert_requirements(gh_live, owner, repo, epic.number, first)

    # 検証: epic Draft PR（base=master・本文は 紐づく Issue のみ）が 1 件作成され 確認:complex-scenario-writer 付与
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True
    assert pr.base.ref == "master"
    assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:complex-scenario-writer" in pr_labels

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number)

    # 検証: エージェント投稿の自分宛コメントが全て Resolve 済み
    assert_comments_resolved(gh_live, owner, repo, epic.number)


def test_normal_when_no_poc_with_ui(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path):
    """epic 本文確定 → 承認 → epic Draft PR 作成 + mock-designer 引き継ぎと指示コメントを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 不要・画面変更ありと回答）
    first, _ = drive_requirements(
        gh_live, owner, repo, wait_until, epic.number,
        answer_body="A（PoC 不要）/ B（画面変更あり: 通知設定画面を新規作成）でお願いします。",
    )
    _assert_requirements(gh_live, owner, repo, epic.number, first)

    # 検証: epic Draft PR（base=master・本文は 紐づく Issue のみ）が 1 件作成され 確認:mock-designer 付与
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True
    assert pr.base.ref == "master"
    assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:mock-designer" in pr_labels

    # 検証: PR に @mock-designer 宛の指示コメントが未 Resolve で投稿されている
    directed = [c for c in comments(gh_live, owner, repo, pr.number) if "> to: @mock-designer" in c.body]
    assert directed, "@mock-designer 宛の指示コメントが投稿されていない"
    assert not server._is_minimized(directed[-1].node_id), "指示コメントが Resolve されてしまっている"

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number)


def test_normal_when_poc_required(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path):
    """epic 本文確定 → 承認 → PoC Draft PR 作成 + epic-poc-runner 引き継ぎ（epic Draft PR なし）を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 必要と回答）
    first, _ = drive_requirements(
        gh_live, owner, repo, wait_until, epic.number,
        answer_body="B（PoC 必要: メール一斉送信のスループット検証）/ A（画面変更なし）でお願いします。",
    )
    _assert_requirements(gh_live, owner, repo, epic.number, first)

    # 検証: PoC Draft PR のみが 1 件作成され（epic Draft PR は作成されない）確認:epic-poc-runner 付与
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"PoC Draft PR のみの 1 件でない: {[(pr.number, pr.title) for pr in prs]}"
    pr = prs[0]
    assert pr.title.startswith("PoC:"), f"タイトルが PoC: 始まりでない: {pr.title}"
    assert f"#{epic.number}" in pr.title
    assert pr.draft is True
    assert pr.base.ref == "master"
    assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:epic-poc-runner" in pr_labels

    # 検証: PR に @epic-poc-runner 宛の指示コメントが未 Resolve で投稿されている
    directed = [c for c in comments(gh_live, owner, repo, pr.number) if "> to: @epic-poc-runner" in c.body]
    assert directed, "@epic-poc-runner 宛の指示コメントが投稿されていない"
    assert not server._is_minimized(directed[-1].node_id), "指示コメントが Resolve されてしまっている"

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number)


# RE 経路の起点になる epic Issue 本文（前提条件とユースケース一覧は起票時に記入済み）
RE_EPIC_BODY = """## 前提条件

- 既存のタスク管理コードが動いている

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| タスク編集 | 一覧から編集画面へ遷移して編集内容を保存する | 未起票 |
"""

# master にある現状の複合 UC シナリオ（RE PR がマージ済みの状態）
CURRENT_COMPLEX_SCENARIO_PATH = "docs/wiki/設計図/シナリオ/複合ユースケース/タスク編集から一覧反映.md"
CURRENT_COMPLEX_SCENARIO_MD = """# タスク編集から一覧反映

現状の実装から起こした複合 UC。
タスクを編集して保存し、一覧に反映されるまでを扱う。

## 正常シナリオ

### 期待値

- 一覧に編集後のタイトルと本文が並んでいる
"""

CURRENT_MOCK_PATH = "docs/mock/pages/タスク編集画面/current/index.html"
CURRENT_MOCK_HTML = "<html><body><h1>タスク編集（現状）</h1></body></html>\n"


def test_normal_when_reverse(
    monitor, gh_live, repo_ctx, epic_issue_factory, commit_file, wait_until, e2e_state_path,
    master_baseline,
):
    """現状の設計書を入力にした epic 要件確定を実環境で確認する（正常系・リバースエンジニアリング）。"""
    owner, repo = repo_ctx
    # 準備: エピック一覧 確定済みの親 system Issue + RE 経路の epic Issue
    system, epic = epic_issue_factory(
        SYSTEM_TITLE, SYSTEM_ISSUE_BODY, EPIC_TITLE,
        epic_body=RE_EPIC_BODY,
        epic_labels=["layer:epic", "type:docs", "リバースエンジニアリング", "確認:epic-conductor"],
        parent_labels=["layer:system", "type:docs", "リバースエンジニアリング"],
    )
    # 準備: RE PR がマージ済み（現状の設計書とモックが master にある）状態を再現する
    commit_file("master", CURRENT_COMPLEX_SCENARIO_PATH, CURRENT_COMPLEX_SCENARIO_MD, "docs: 現状の複合UC シナリオを追加")
    commit_file("master", CURRENT_MOCK_PATH, CURRENT_MOCK_HTML, "docs: 現状モックを追加")

    # 実行: 要件確定フローをユーザー役として進める
    first, _ = drive_requirements(
        gh_live, owner, repo, wait_until, epic.number,
        answer_body="現状の設計書どおりで問題ありません。乖離している箇所は現状に合わせてください。",
    )
    _assert_requirements(gh_live, owner, repo, epic.number, first)

    # 検証: epic Draft PR が 1 件作成され mock-designer へ引き継がれている
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True
    assert_linked_issue_only_body(pr)
    assert "確認:mock-designer" in {label.name for label in pr.labels}

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number)

    # 検証: エージェント投稿の自分宛コメントが全て Resolve 済み
    assert_comments_resolved(gh_live, owner, repo, epic.number)
    assert system is not None and master_baseline


# 対象範囲・PoC 要否・画面変更の有無が本文から一意に定まる intake（確認事項が 0 件になる状況）
UNAMBIGUOUS_INTAKE_TITLE = "タスク一覧の並び順を期限昇順に固定する"
UNAMBIGUOUS_INTAKE_BODY = """タスク一覧の並び順を、期限の昇順に固定してください。

- 対象はタスク一覧の取得処理だけで、他の画面・API は変更しない
- 並び替えの UI は追加しない（ユーザーが並び順を選ぶ機能は作らない）
- 既存の一覧取得に ORDER BY を足すだけなので、実現方式の検証（PoC）は不要
- 画面の見た目・遷移は変わらない（並ぶ順序だけが変わる）
"""


def _question_comments(gh_live, owner, repo, number) -> list:
    """選択肢付きの確認質問コメントだけを返す（`- A. ` の行を持つもの）。"""
    import re

    return [
        c
        for c in comments(gh_live, owner, repo, number)
        if c.body.lstrip().startswith("> from:") and re.search(r"^- A\. ", c.body, re.M)
    ]


def test_normal_when_no_questions(
    monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path
):
    """論点が一意に定まるときに質問せず前提を明示して進むことを実環境で確認する（正常系）。"""
    from tests.e2e.エスカレーション import approve, issue, label_names, waiting_for_user

    owner, repo = repo_ctx
    # 準備: 論点が本文から一意に定まる親 intake + 本文空の epic Issue
    _intake, epic = epic_issue_factory(
        UNAMBIGUOUS_INTAKE_TITLE, UNAMBIGUOUS_INTAKE_BODY, UNAMBIGUOUS_INTAKE_TITLE
    )

    # 実行: 要件確定（初回）の完了を待つ（議論中 + assignee）
    def _first_turn_done():
        data = issue(gh_live, owner, repo, epic.number)
        return data if waiting_for_user(data) else None

    first = wait_until(
        _first_turn_done, timeout_sec=1200, message="要件確定（初回）の完了（議論中 + assignee）"
    )

    # 検証: 確認質問が 1 件も投稿されていない
    questions = _question_comments(gh_live, owner, repo, epic.number)
    assert not questions, f"確認質問が投稿されている: {[c.html_url for c in questions]}"

    # 検証: 本文 5 セクションが埋まり、完了報告コメントが投稿されている
    _assert_requirements(gh_live, owner, repo, epic.number, first)

    # 検証: ユーザーが確認するタイミング自体は残っている
    assert "議論中" in label_names(first)
    assert first.assignees

    # 実行: ユーザー承認（議論中 除去 + assignee 外し）
    approve(gh_live, owner, repo, epic.number, first.assignees)

    def _completed():
        data = issue(gh_live, owner, repo, epic.number)
        return data if not [n for n in label_names(data) if n.startswith("確認:")] else None

    wait_until(_completed, timeout_sec=1200, message="要件確定（完了処理）の完了（確認:* 除去）")

    # 検証: epic Draft PR が作成され complex-scenario-writer へ引き継がれている
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True
    assert_linked_issue_only_body(pr)
    assert "確認:complex-scenario-writer" in {label.name for label in pr.labels}

    # 検証: 作成した PR の番号が自セッションの監視面に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number)

    # 検証: エージェント投稿の自分宛コメントが全て Resolve 済み
    assert_comments_resolved(gh_live, owner, repo, epic.number)

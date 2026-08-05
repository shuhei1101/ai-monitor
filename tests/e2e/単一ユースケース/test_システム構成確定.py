"""「システム構成確定」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, comments_from, issue, label_names, me, waiting_for_user
from tests.e2e.システム import (
    ARCHITECTURE_MD,
    ARCHITECTURE_PATH,
    ARCHITECTURE_RE_REPORT,
    MIGRATION_TITLE,
    SYSTEM_BODY,
    SYSTEM_BODY_MIGRATION,
    SYSTEM_BODY_MINIMAL,
    SYSTEM_TITLE,
    watch_numbers,
)
from tests.e2e.実装対象 import PROJECT_FILES

SECTIONS = ["## 概要", "## 背景", "## 構成要件", "## エピック一覧"]


def _approve(gh_live, owner, repo, number, data) -> None:
    """ユーザー承認（議論中 除去 + assignee 外し）を行う。"""
    gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name="議論中")
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def _wait_drafted(gh_live, owner, repo, number, wait_until, *, message):
    """本文の草案が入り、ユーザー待ち（議論中 + assignee）になるまで待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, number)
        if not waiting_for_user(data):
            return None
        return data if all(section in (data.body or "") for section in SECTIONS) else None

    return wait_until(_done, timeout_sec=2400, message=message)


def _wait_handed_off(gh_live, owner, repo, number, wait_until, *, message):
    """完了処理（system PR 作成 + 確認:system-architect 付与）が終わるまで待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, number)
        if "確認:system-conductor" in label_names(data):
            return None
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        candidates = [p for p in pulls if f"#{number}" in (p.body or "")]
        if not candidates:
            return None
        pr = candidates[0]
        pr_labels = {label.name for label in issue(gh_live, owner, repo, pr.number).labels}
        return (data, pr) if "確認:system-architect" in pr_labels else None

    return wait_until(_done, timeout_sec=2400, message=message)


def _assert_handed_off(gh_live, owner, repo, system_number, pr, e2e_state_path) -> None:
    """system Draft PR の内容・監視面・依頼コメントを検証する。"""
    assert pr.draft is True, "system PR が Draft で作成されていない"
    assert pr.base.ref == "master", f"base が master でない: {pr.base.ref}"
    pr_body = (pr.body or "").replace("\r\n", "\n")
    assert "## 紐づく Issue" in pr_body, "PR 本文に ## 紐づく Issue がない"
    assert "## タスク一覧" in pr_body, "PR 本文に ## タスク一覧 がない"

    # 作成した PR の番号が自セッションの監視面に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "system-conductor", system_number), (
        "作成した PR の番号が監視面に登録されていない"
    )

    # 土台生成の依頼コメントが未解決で投稿されている
    requests = comments_from(gh_live, owner, repo, pr.number, "system-conductor")
    assert requests, "土台生成の依頼コメントが投稿されていない"
    assert "> to: @system-architect" in (requests[-1].body or ""), "依頼の宛先が system-architect でない"
    assert not server._is_minimized(requests[-1].node_id), "依頼コメントが Resolve されている"


def test_normal_when_new_project(
    monitor, gh_live, repo_ctx, system_issue_factory, wait_until, sandbox, e2e_state_path,
):
    """新規プロジェクトの構成要件確定と system Draft PR の作成を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    system = system_issue_factory(SYSTEM_TITLE, SYSTEM_BODY)

    # 実行: 本文の草案と確認事項の投稿を待つ
    data = _wait_drafted(
        gh_live, owner, repo, system.number, wait_until, message="構成要件の草案と確認事項の投稿",
    )

    # 検証: ユーザーが付けていない layer / type がエージェントによって付与されている
    labels = label_names(data)
    assert "layer:system" in labels, f"layer:system が付与されていない: {sorted(labels)}"
    assert "type:feat" in labels, f"type:feat が付与されていない: {sorted(labels)}"

    # 検証: エピック一覧が未作成のまま並び、着手順に重複がない
    body = (data.body or "").replace("\r\n", "\n")
    epic_rows = [
        line for line in body.split("## エピック一覧", 1)[1].splitlines()
        if line.startswith("|") and "---" not in line and "エピック名" not in line
    ]
    assert epic_rows, "エピック一覧に行がない"
    assert all("未作成" in row for row in epic_rows), f"対応 PR 列が全行 未作成 でない: {epic_rows}"
    orders = [cell.strip() for row in epic_rows for cell in row.split("|")[1:-1]]
    numeric = [cell for cell in orders if cell.isdigit()]
    assert len(numeric) == len(set(numeric)), f"着手順が重複している: {numeric}"

    # 実行: ユーザー承認 → 完了処理（PR 作成 + 引き継ぎ）を待つ
    _approve(gh_live, owner, repo, system.number, data)
    done, pr = _wait_handed_off(
        gh_live, owner, repo, system.number, wait_until, message="system Draft PR の作成と引き継ぎ",
    )

    # 検証: PR の内容・監視面・依頼コメント
    _assert_handed_off(gh_live, owner, repo, system.number, pr, e2e_state_path)

    # 検証: 確認ラベルが除去され、自分宛コメントが Resolve 済み
    assert "確認:system-conductor" not in label_names(done), "確認:system-conductor が残っている"
    for comment in comments_from(gh_live, owner, repo, system.number, "system-conductor"):
        assert server._is_minimized(comment.node_id), f"自分宛コメントが未 Resolve: {comment.html_url}"


def test_normal_when_missing_config(
    monitor, gh_live, repo_ctx, system_issue_factory, wait_until, sandbox,
):
    """技術構成に触れていない入力での不足の洗い出しを実環境で確認する（正常系・構成の情報が不足）。"""
    owner, repo = repo_ctx
    system = system_issue_factory(SYSTEM_TITLE, SYSTEM_BODY_MINIMAL)

    # 実行: 仮置きの草案と確認事項の投稿を待つ
    data = _wait_drafted(
        gh_live, owner, repo, system.number, wait_until, message="仮置きの草案と確認事項の投稿",
    )

    # 検証: 構成要件が空欄ではなく仮置きの案で埋まっている
    body = (data.body or "").replace("\r\n", "\n")
    config = body.split("## 構成要件", 1)[1].split("\n## ", 1)[0]
    config_rows = [
        line for line in config.splitlines()
        if line.startswith("|") and "---" not in line and "カテゴリ" not in line
    ]
    assert config_rows, "構成要件が空のまま質問だけ投げている"

    # 検証: 入力に無かった項目について、選択肢と推奨を含む確認事項が投稿されている
    questions = [
        c for c in comments_from(gh_live, owner, repo, system.number, "system-conductor")
        if f"@{me(gh_live)}" in (c.body or "")
    ]
    assert questions, "ユーザー宛の確認事項コメントが投稿されていない"
    assert any("推奨" in (c.body or "") for c in questions), "推奨を含む確認事項がない"

    # 検証: この時点では system Draft PR がまだ作成されていない
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    assert not [p for p in pulls if f"#{system.number}" in (p.body or "")], (
        "承認前に system Draft PR が作成されている"
    )


def test_normal_when_migration(
    monitor, gh_live, repo_ctx, system_issue_factory, commit_file, wait_until, sandbox,
    e2e_state_path, master_baseline,
):
    """既存コードと現状のアーキテクチャ図からの構成確定を実環境で確認する（正常系・既存プロジェクトの移行）。"""
    owner, repo = repo_ctx
    # 準備: RE PR がマージ済みの状態（master に実装と現状のアーキテクチャ図がある）を再現する
    for path, content in PROJECT_FILES.items():
        commit_file("master", path, content, f"chore: e2e 用に {path} を配置")
    commit_file("master", ARCHITECTURE_PATH, ARCHITECTURE_MD, "docs: 現状のアーキテクチャ図を追加")

    system = system_issue_factory(
        MIGRATION_TITLE, SYSTEM_BODY_MIGRATION,
        labels=["リバースエンジニアリング", "確認:system-conductor"],
    )
    # 準備: architecture-reverse-engineer の完了報告（エピック一覧の材料）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=system.number, body=ARCHITECTURE_RE_REPORT
    )

    # 実行: 本文の草案と確認事項の投稿を待つ
    data = _wait_drafted(
        gh_live, owner, repo, system.number, wait_until, message="現状からの構成要件の草案",
    )

    # 検証: 移行なので type:docs が付く
    labels = label_names(data)
    assert "layer:system" in labels, f"layer:system が付与されていない: {sorted(labels)}"
    assert "type:docs" in labels, f"type:docs が付与されていない: {sorted(labels)}"

    # 検証: 構成要件のサブシステム分割が現状のアーキテクチャ図と一致している
    body = (data.body or "").replace("\r\n", "\n")
    assert "バックエンド" in body, "アーキテクチャ図のサブシステムが構成要件に反映されていない"

    # 検証: 機能の洗い出しがエピック一覧に反映されている
    epics = body.split("## エピック一覧", 1)[1]
    assert any(word in epics for word in ("編集", "更新", "一覧")), (
        f"完了報告の機能がエピック一覧に反映されていない: {epics[:200]}"
    )

    # 実行: ユーザー承認 → 完了処理（PR 作成 + 引き継ぎ）を待つ
    _approve(gh_live, owner, repo, system.number, data)
    done, pr = _wait_handed_off(
        gh_live, owner, repo, system.number, wait_until, message="system Draft PR の作成と引き継ぎ",
    )

    # 検証: PR の内容・監視面・依頼コメント
    _assert_handed_off(gh_live, owner, repo, system.number, pr, e2e_state_path)
    assert "確認:system-conductor" not in label_names(done), "確認:system-conductor が残っている"
    assert comments(gh_live, owner, repo, system.number), "コメントが 1 件も残っていない"

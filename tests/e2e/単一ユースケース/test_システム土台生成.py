"""「システム土台生成」の E2E テスト。"""
from __future__ import annotations

import base64

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments_from, issue, label_names, supplement_review_comments
from tests.e2e.システム import BUILD_REQUEST, SYSTEM_ISSUE_BODY, SYSTEM_PR_BODY, SYSTEM_TITLE, system_branch
from tests.e2e.実装対象 import add_worktree

# 土台として生成されるべきページ（骨格の抜け漏れ検出用）
EXPECTED_PAGES = [
    "README.md",
    ".gitignore",
    ".claude/settings.json",
    "docs/rules.yaml",
    "docs/wiki/README.md",
    "docs/wiki/設計図/アーキテクチャ図.md",
    "docs/wiki/設計図/非機能要件.md",
    "docs/wiki/テスト/テスト実行方法.md",
    "docs/wiki/外部API/README.md",
    "docs/wiki/外部ライブラリ/README.md",
]


def _file_text(gh_live, owner, repo, path, ref) -> str | None:
    """指定 ref のファイル内容を返す（存在しなければ None）。"""
    try:
        content = gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref).parsed_data
    except RequestFailed:
        return None
    return base64.b64decode(content.content).decode("utf-8")


def test_normal(
    monitor, gh_live, repo_ctx, system_issue_factory, draft_pr_factory, wait_until, sandbox,
):
    """構成要件からの土台生成と system-conductor への引き継ぎを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    system = system_issue_factory(
        SYSTEM_TITLE, SYSTEM_ISSUE_BODY, labels=["layer:system", "type:feat"],
    )
    branch = system_branch(system.number)
    pr = draft_pr_factory(
        branch, SYSTEM_TITLE, SYSTEM_PR_BODY.format(system_number=system.number)
    )
    add_worktree(sandbox["local_path"], branch)

    # 準備: system-conductor の依頼 → 確認:system-architect 付与（起動トリガー）
    request = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr.number,
        body=BUILD_REQUEST.format(system_number=system.number),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:system-architect"]
    )

    # 実行: 土台生成の完了（議論中 + assignee のユーザー確認待ち）を待つ
    def _built():
        data = issue(gh_live, owner, repo, pr.number)
        labels = label_names(data)
        if "議論中" not in labels or not data.assignees:
            return None
        return data if _file_text(gh_live, owner, repo, "docs/rules.yaml", branch) is not None else None

    data = wait_until(_built, timeout_sec=3600, message="土台生成の完了（議論中 + assignee）")

    # 検証: 骨格のページが system ブランチに揃っている
    missing = [p for p in EXPECTED_PAGES if _file_text(gh_live, owner, repo, p, branch) is None]
    assert not missing, f"生成されていないページがある: {missing}"

    # 検証: docs/rules.yaml が空の索引で作られている
    rules = _file_text(gh_live, owner, repo, "docs/rules.yaml", branch) or ""
    assert "rules:" in rules, f"rules.yaml が索引の形になっていない: {rules[:120]}"

    # 検証: ルール索引が 3 つとも宣言されている（ユーザーが手で設定しなくても規約が注入される）
    settings = _file_text(gh_live, owner, repo, ".claude/settings.json", branch) or ""
    for index in ("my-plugins", "ai-monitor", repo):
        assert f"{index}/master/docs/rules.yaml" in settings, (
            f"INJECT_RULES_INDEXES に {index} のルール索引がない: {settings[:300]}"
        )

    # 検証: .gitignore に worktree と環境変数ファイルの除外が入っている
    ignored = _file_text(gh_live, owner, repo, ".gitignore", branch) or ""
    assert ".claude/worktrees/" in ignored, (
        f"worktree の実体が追跡対象から外れていない: {ignored[:200]}"
    )
    assert ".env" in ignored, f"環境変数ファイルが追跡対象から外れていない: {ignored[:200]}"

    # 検証: テスト実行方法は見出しだけで本文が未確定
    howto = _file_text(gh_live, owner, repo, "docs/wiki/テスト/テスト実行方法.md", branch) or ""
    assert "未確定" in howto, "テスト実行方法.md が未確定で置かれていない"

    # 検証: アーキテクチャ図が構成要件どおり（サブシステムはバックエンドのみ・外部システムなし）
    architecture = _file_text(gh_live, owner, repo, "docs/wiki/設計図/アーキテクチャ図.md", branch) or ""
    for section in ("## システム全体図", "## リポジトリ構成", "## サブシステム一覧", "## 外部システム連携"):
        assert section in architecture, f"アーキテクチャ図に {section} がない"
    assert "scope:" in architecture, "サブシステム一覧に scope 列の値がない"

    # 検証: 非機能要件の一覧と詳細セクションが対応している
    nfr = _file_text(gh_live, owner, repo, "docs/wiki/設計図/非機能要件.md", branch) or ""
    assert "## 一覧" in nfr, "非機能要件に ## 一覧 がない"
    listed = nfr.split("## 一覧", 1)[1].split("\n## ", 1)[0]
    rows = [
        line for line in listed.splitlines()
        if line.startswith("|") and "---" not in line and "カテゴリ" not in line
    ]
    assert rows, "非機能要件の一覧が空"
    assert any("](#" in row for row in rows), "一覧の項目が詳細セクションへのリンクになっていない"

    # 検証: PR 本文のタスク一覧が全てチェック済み
    pr_body = (data.body or "").replace("\r\n", "\n")
    assert "- [ ]" not in pr_body, f"タスク一覧に未チェックが残っている: {pr_body}"

    # 検証: ラベルが対象リポジトリに作成されている（一括作成の実行結果）
    label_names_all = {
        label.name for label in gh_live.rest.issues.list_labels_for_repo(
            owner=owner, repo=repo, per_page=100
        ).parsed_data
    }
    assert "確認:system-architect" in label_names_all, "ラベルの一括作成が実行されていない"

    # 検証: commit 内容に対する補足事項がインラインコメントで残っている
    assert supplement_review_comments(gh_live, owner, repo, pr.number), (
        "補足事項のインラインコメントが投稿されていない"
    )

    # 実行: ユーザー承認（議論中 除去 + assignee 外し）→ 引き継ぎを待つ
    gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    def _handed_off():
        current = issue(gh_live, owner, repo, pr.number)
        labels = label_names(current)
        if "確認:system-conductor" not in labels or "確認:system-architect" in labels:
            return None
        reports = comments_from(gh_live, owner, repo, pr.number, "system-architect")
        return (current, reports[-1]) if reports else None

    _, report = wait_until(_handed_off, timeout_sec=2400, message="system-conductor への引き継ぎ")

    # 検証: 完了報告は未解決（受領は system-conductor）で、依頼コメントは Resolve 済み
    assert not server._is_minimized(report.node_id), "完了報告が Resolve されている"
    assert server._is_minimized(request.node_id), "土台生成の依頼コメントが未 Resolve"

"""「子epicPR作成」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments_from, issue, label_names
from tests.e2e.システム import setup_system_with_foundation

# SYSTEM_PR_BODY_CONFIRMED の `## エピック一覧` に並べた epic の件数
EPIC_COUNT = 2

# ユースケース一覧の 変更種別 列に入りうる値
CHANGE_KINDS = ("新規", "変更", "削除")


def _section(body: str, heading: str) -> str:
    """本文から指定見出しのセクションを取り出す。"""
    return (body or "").replace("\r\n", "\n").split(heading, 1)[1].split("\n## ", 1)[0]


def _data_rows(section: str, header_word: str) -> list[str]:
    """表のデータ行（ヘッダーと区切りを除いた行）を返す。"""
    return [
        line for line in section.splitlines()
        if line.startswith("|") and "---" not in line and header_word not in line
    ]


def _open_children(gh_live, owner: str, repo: str, base_branch: str) -> list:
    """指定ブランチを base にした open PR を返す。"""
    return list(
        gh_live.rest.pulls.list(
            owner=owner, repo=repo, state="open", base=base_branch, per_page=100
        ).parsed_data
    )


def test_normal(
    monitor, gh_live, repo_ctx, system_issue_factory, layer_pr_factory, commit_file,
    wait_until,
):
    """エピック一覧からの子 epic PR 一括作成と先頭 epic だけの起動を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: 要件確定済みの system PR + マージ済みの土台生成成果物 PR
    ctx = setup_system_with_foundation(
        gh_live, owner, repo, system_issue_factory, layer_pr_factory, commit_file,
        pr_labels=["layer:system", "type:feat", "確認:system-conductor"],
    )
    system_pr = ctx["system_pr"]
    branch = ctx["branch"]

    # 実行: 子 epic PR の一括作成と system PR の確認ラベル除去を待つ
    def _done():
        data = issue(gh_live, owner, repo, system_pr.number)
        if [name for name in label_names(data) if name.startswith("確認:")]:
            return None
        children = _open_children(gh_live, owner, repo, branch)
        return (data, children) if len(children) >= EPIC_COUNT else None

    data, children = wait_until(_done, timeout_sec=2400, message="子 epic PR の一括作成")

    # 検証: エピック一覧と同数の epic PR が system ブランチの上に作られている
    assert len(children) == EPIC_COUNT, f"epic PR の件数がエピック一覧と一致しない: {len(children)}"
    for pr in children:
        assert pr.base.ref == branch, f"#{pr.number} の base が system ブランチでない: {pr.base.ref}"
        assert pr.draft, f"#{pr.number} が Draft でない"

    # 検証: ラベル・ユースケース一覧・変更種別
    started = []
    for pr in children:
        pr_now = issue(gh_live, owner, repo, pr.number)
        labels = label_names(pr_now)
        assert "layer:epic" in labels, f"#{pr.number} に layer:epic がない: {sorted(labels)}"
        assert "type:feat" in labels, f"#{pr.number} に type:feat がない: {sorted(labels)}"
        assert "リバースエンジニアリング" not in labels, (
            f"#{pr.number} に親に無い リバースエンジニアリング が付いている"
        )
        body = (pr_now.body or "").replace("\r\n", "\n")
        assert "## ユースケース一覧" in body, f"#{pr.number} に ## ユースケース一覧 がない"
        uc_rows = _data_rows(_section(body, "## ユースケース一覧"), "ユースケース")
        assert uc_rows, f"#{pr.number} のユースケース一覧が空"
        for row in uc_rows:
            assert "未作成" in row, f"#{pr.number} の 対応 story 列が 未作成 でない: {row}"
            assert any(kind in row for kind in CHANGE_KINDS), (
                f"#{pr.number} の 変更種別 列が埋まっていない: {row}"
            )
        if "確認:epic-conductor" in labels:
            started.append(pr.number)

    # 検証: 着手は直列なので確認ラベルは先頭 1 件だけ
    assert len(started) == 1, f"確認:epic-conductor が先頭 1 件に絞られていない: {started}"

    # 検証: 着手順 2 番目以降には確認ラベルが無く、着手の痕跡も無い
    others = [pr.number for pr in children if pr.number not in started]
    for number in others:
        follower = issue(gh_live, owner, repo, number)
        follower_labels = label_names(follower)
        assert "確認:epic-conductor" not in follower_labels, (
            f"#{number} に確認ラベルが付いている（着手順の先頭は #{started[0]}）"
        )
        assert "議論中" not in follower_labels, f"#{number} に着手の痕跡（議論中）がある"
        assert not follower.assignees, f"#{number} に着手の痕跡（assignee）がある"
        assert not comments_from(gh_live, owner, repo, number, "epic-conductor"), (
            f"#{number} に epic-conductor の投稿がある"
        )

    # 検証: エピック一覧の 対応 PR 列が全行 #N に更新されている
    rows = _data_rows(_section(data.body or "", "## エピック一覧"), "エピック")
    assert rows, "エピック一覧の行がない"
    assert not any("未作成" in row for row in rows), f"未作成 が残っている: {rows}"
    for number in [pr.number for pr in children]:
        assert any(f"#{number}" in row for row in rows), f"対応 PR 列に #{number} がない: {rows}"

    # 検証: 自分宛コメントが全て Resolve 済み
    for comment in comments_from(gh_live, owner, repo, system_pr.number, "system-conductor"):
        assert server._is_minimized(comment.node_id), f"自分宛コメントが未 Resolve: {comment.html_url}"

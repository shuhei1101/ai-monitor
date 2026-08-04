"""「子epicPR作成」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments_from, issue, label_names
from tests.e2e.システム import SYSTEM_ISSUE_BODY, SYSTEM_TITLE

# SYSTEM_ISSUE_BODY の `## エピック一覧` に並べた epic の件数
EPIC_COUNT = 2


def _epic_rows(body: str) -> list[str]:
    """system Issue 本文のエピック一覧のデータ行を返す。"""
    section = (body or "").replace("\r\n", "\n").split("## エピック一覧", 1)[1]
    return [
        line for line in section.splitlines()
        if line.startswith("|") and "---" not in line and "エピック名" not in line
    ]


def _wait_issued(gh_live, owner, repo, number, wait_until, *, message):
    """子 epic の起票と system Issue の確認ラベル除去が終わるまで待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, number)
        if [name for name in label_names(data) if name.startswith("確認:")]:
            return None
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=number
        ).parsed_data
        return (data, subs) if len(subs) >= EPIC_COUNT else None

    return wait_until(_done, timeout_sec=2400, message=message)


def test_normal(monitor, gh_live, repo_ctx, system_issue_factory, wait_until, sandbox):
    """エピック一覧からの子 epic 一括起票と先頭 epic だけの起動を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    system = system_issue_factory(
        SYSTEM_TITLE, SYSTEM_ISSUE_BODY,
        labels=["layer:system", "type:feat", "確認:system-conductor"],
    )

    # 実行: 子 epic の一括起票を待つ
    data, subs = _wait_issued(
        gh_live, owner, repo, system.number, wait_until, message="子 epic の一括起票",
    )

    # 検証: エピック一覧と同数の epic が紐づいている
    assert len(subs) == EPIC_COUNT, f"epic の件数がエピック一覧と一致しない: {len(subs)}"

    # 検証: 全 epic に layer / type が付き、親に無い リバースエンジニアリング は引き継がれない
    started = []
    for sub in subs:
        sub_now = issue(gh_live, owner, repo, sub.number)
        sub_labels = label_names(sub_now)
        assert "layer:epic" in sub_labels, f"#{sub.number} に layer:epic がない: {sorted(sub_labels)}"
        assert "type:feat" in sub_labels, f"#{sub.number} に type:feat がない: {sorted(sub_labels)}"
        assert "リバースエンジニアリング" not in sub_labels, (
            f"#{sub.number} に親に無い リバースエンジニアリング が付いている"
        )
        # ユースケース一覧が埋まり、対応 story 列は全行 未起票
        sub_body = (sub_now.body or "").replace("\r\n", "\n")
        assert "## ユースケース一覧" in sub_body, f"#{sub.number} に ## ユースケース一覧 がない"
        uc_section = sub_body.split("## ユースケース一覧", 1)[1].split("\n## ", 1)[0]
        uc_rows = [
            line for line in uc_section.splitlines()
            if line.startswith("|") and "---" not in line and "UC" not in line
        ]
        assert uc_rows, f"#{sub.number} のユースケース一覧が空"
        assert all("未起票" in row for row in uc_rows), f"#{sub.number} の対応 story 列が未起票でない"
        if "確認:epic-conductor" in sub_labels:
            started.append(sub.number)

    # 検証: 着手は直列なので確認ラベルは 1 つだけ
    assert len(started) == 1, f"確認:epic-conductor が先頭 1 件に絞られていない: {started}"

    # 検証: 後続 epic の前提条件に先行 epic が未完了として載っている
    others = [s.number for s in subs if s.number not in started]
    for number in others:
        body = (issue(gh_live, owner, repo, number).body or "").replace("\r\n", "\n")
        premise = body.split("## 前提条件", 1)[1].split("\n## ", 1)[0]
        assert "未完了" in premise, f"#{number} の前提条件に先行 epic の未完了が書かれていない: {premise[:120]}"

    # 検証: エピック一覧の 対応 Issue 列が全行 #N に更新されている
    rows = _epic_rows(data.body or "")
    assert rows, "エピック一覧の行がない"
    assert all("#" in row for row in rows), f"対応 Issue 列が未起票のまま: {rows}"
    assert not any("未起票" in row for row in rows), f"未起票 が残っている: {rows}"

    # 検証: 自分宛コメントが全て Resolve 済み
    for comment in comments_from(gh_live, owner, repo, system.number, "system-conductor"):
        assert server._is_minimized(comment.node_id), f"自分宛コメントが未 Resolve: {comment.html_url}"

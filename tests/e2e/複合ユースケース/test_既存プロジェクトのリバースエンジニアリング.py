"""「既存プロジェクトのリバースエンジニアリング」の E2E テスト。

system Issue の起票から先頭 epic の master マージまでを 1 本で通す最長経路。
実行時間が長いため、対象コードは `実装対象.PROJECT_FILES` の最小構成（エンドポイント相当の関数 3 つ）に絞る。
"""
from __future__ import annotations

import subprocess

from githubkit.exception import RequestFailed

from tests.e2e.ゲート応答 import drive_gates
from tests.e2e.エスカレーション import issue, label_names
from tests.e2e.システム import MIGRATION_TITLE, SYSTEM_BODY_MIGRATION
from tests.e2e.実装対象 import PROJECT_FILES

# 全レイヤーの確認ラベル（ゲートが開いたら承認だけ返す）
CONFIRM_LABELS = [
    "確認:system-conductor",
    "確認:system-architect",
    "確認:architecture-reverse-engineer",
    "確認:epic-conductor",
    "確認:mock-designer",
    "確認:mock-reverse-engineer",
    "確認:complex-scenario-writer",
    "確認:complex-scenario-reverse-engineer",
    "確認:complex-scenario-tester",
    "確認:story-conductor",
    "確認:single-scenario-writer",
    "確認:single-scenario-reverse-engineer",
    "確認:single-scenario-tester",
    "確認:subsystem-conductor",
    "確認:ss-design-reverse-engineer",
    "確認:architect",
    "確認:tester",
    "確認:implementer",
]

# 先頭 epic の範囲について master に揃うべき設計書の階層
EXPECTED_DESIGN_DIRS = [
    "docs/wiki/設計図/シナリオ/複合ユースケース",
    "docs/wiki/設計図/シナリオ/単一ユースケース",
    "docs/wiki/設計図/モジュール構成",
]


def _exists(gh_live, owner, repo, path: str, ref: str) -> bool:
    """指定 ref にパスが存在するかを返す。"""
    try:
        gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref)
        return True
    except RequestFailed:
        return False


def _issue_tree(gh_live, owner, repo, number: int) -> list[int]:
    """Sub-issue を再帰的に辿って Issue 番号を集める。"""
    numbers = [number]
    try:
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=number
        ).parsed_data
    except RequestFailed:
        return numbers
    for sub in subs:
        numbers.extend(_issue_tree(gh_live, owner, repo, sub.number))
    return numbers


def test_normal(
    monitor, gh_live, repo_ctx, system_issue_factory, commit_file, wait_until, sandbox, master_baseline,
):
    """コード分析から先頭 epic の master マージまでの一気通しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 設計書が無く実装だけがある既存プロジェクトを master に再現する
    for path, content in PROJECT_FILES.items():
        commit_file("master", path, content, f"chore: e2e 用に {path} を配置")

    system = system_issue_factory(
        MIGRATION_TITLE, SYSTEM_BODY_MIGRATION,
        labels=["リバースエンジニアリング", "確認:system-conductor"],
    )

    def _faces():
        # system 配下の全 Issue と、それらに紐づく open PR が応答対象の面
        numbers = _issue_tree(gh_live, owner, repo, system.number)
        faces = [("issue", n) for n in numbers]
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        faces += [
            ("pr", p.number) for p in pulls
            if any(f"#{n}" in (p.body or "") for n in numbers)
        ]
        return faces

    def _first_epic_merged():
        # 先頭 epic の PR が master へマージされた時点で終端
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=system.number
        ).parsed_data
        if not subs:
            return None
        closed = gh_live.rest.pulls.list(owner=owner, repo=repo, state="closed", per_page=100).parsed_data
        for sub in subs:
            merged = [
                p for p in closed
                if f"#{sub.number}" in (p.body or "") and p.merged_at and p.base.ref == "master"
            ]
            if merged:
                return (sub, merged[0], subs)
        return None

    # 実行: 全レイヤーのゲートに応答して先頭 epic のマージまで進める
    history, (first_epic, epic_pr, subs) = drive_gates(
        gh_live, owner, repo,
        faces=_faces,
        choices={(kind, label): None for kind in ("issue", "pr") for label in CONFIRM_LABELS},
        terminal=_first_epic_merged,
        wait_until=wait_until,
        timeout_sec=21600,
        max_rounds=120,
    )
    assert history, "ユーザー確認ゲートが 1 度も開いていない"

    # 検証: 土台と現状の設計書が master に揃っている
    for path in ("README.md", "docs/rules.yaml", "docs/wiki/設計図/アーキテクチャ図.md"):
        assert _exists(gh_live, owner, repo, path, "master"), f"master に {path} がない"
    missing = [d for d in EXPECTED_DESIGN_DIRS if not _exists(gh_live, owner, repo, d, "master")]
    assert not missing, f"先頭 epic の範囲の設計書が master に揃っていない: {missing}"

    # 検証: エピック一覧の 対応 Issue 列が全行 #N に更新されている
    body = (issue(gh_live, owner, repo, system.number).body or "").replace("\r\n", "\n")
    epic_rows = [
        line for line in body.split("## エピック一覧", 1)[1].splitlines()
        if line.startswith("|") and "---" not in line and "エピック名" not in line
    ]
    assert epic_rows and not any("未起票" in row for row in epic_rows), (
        f"対応 Issue 列が更新されていない: {epic_rows}"
    )

    # 検証: 2 本目以降の epic は open のまま確認ラベルなしで残っている
    remaining = [s for s in subs if s.number != first_epic.number]
    for sub in remaining:
        sub_now = issue(gh_live, owner, repo, sub.number)
        assert sub_now.state == "open", f"#{sub.number} が close されている（着手は順次）"
        assert not [n for n in label_names(sub_now) if n.startswith("確認:")], (
            f"#{sub.number} に確認ラベルが付いている（ユーザーが順次付与する）"
        )

    # 検証: system Issue は未完了の epic があるので open のまま
    assert issue(gh_live, owner, repo, system.number).state == "open", (
        "未完了の epic があるのに system Issue が close されている"
    )

    # 検証: 先頭 epic 配下の中間ブランチが残っていない
    branches = {b.name for b in gh_live.rest.repos.list_branches(
        owner=owner, repo=repo, per_page=100
    ).parsed_data}
    assert epic_pr.head.ref not in branches, f"マージした epic ブランチが残っている: {epic_pr.head.ref}"

    # 検証: 先頭 epic 配下の tmux セッションが一括解放されている
    def _released():
        listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
        alive = [
            name for name in listed.stdout.splitlines()
            if name.startswith(f"ai-monitor-{sandbox['name']}-{first_epic.number}-")
        ]
        return True if not alive else None

    wait_until(_released, timeout_sec=900, message="先頭 epic 配下のセッション一括解放")

    # 検証: 処理中ラベルがどこにも残っていない
    for number in _issue_tree(gh_live, owner, repo, system.number):
        names = label_names(issue(gh_live, owner, repo, number))
        assert not [n for n in names if n.startswith("処理中:")], (
            f"#{number} に処理中ラベルが残っている: {sorted(names)}"
        )

"""「新規プロジェクトの立ち上げ」の E2E テスト。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

from tests.e2e.ゲート応答 import drive_gates, open_prs_for
from tests.e2e.エスカレーション import issue, label_names
from tests.e2e.システム import SYSTEM_BODY, SYSTEM_TITLE

# 土台生成で system ブランチに反映されるべきページ
# （master へ載るのは全 epic 完了後の system完了マージ なので、ここでは system ブランチを見る）
EXPECTED_PAGES = [
    "README.md",
    "docs/rules.yaml",
    "docs/wiki/README.md",
    "docs/wiki/設計図/アーキテクチャ図.md",
]


def _exists(gh_live, owner, repo, path: str, ref: str) -> bool:
    """指定 ref にファイルが存在するかを返す。"""
    try:
        gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref)
        return True
    except RequestFailed:
        return False


def _system_pr(gh_live, owner, repo, system_number: int):
    """master を base にした system PR を返す（未作成なら None）。"""
    for pr in open_prs_for(gh_live, owner, repo, system_number):
        if pr.base.ref == "master":
            return pr
    return None


def test_normal(
    monitor, gh_live, repo_ctx, system_issue_factory, wait_until, sandbox, master_baseline,
):
    """構成確定から子 epic PR 一括作成までの一気通しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    system = system_issue_factory(SYSTEM_TITLE, SYSTEM_BODY)

    def _faces():
        # 立ち上げ Issue と、それに紐づく open PR（system PR / 土台生成の成果物 PR）が応答対象の面
        faces = [("system_issue", system.number)]
        faces += [("system_pr", p.number) for p in open_prs_for(gh_live, owner, repo, system.number)]
        return faces

    def _epics_started():
        # 子 epic PR が system ブランチの上に作られ、着手順の先頭だけが起動した時点で終端
        system_pr = _system_pr(gh_live, owner, repo, system.number)
        if system_pr is None:
            return None
        children = list(
            gh_live.rest.pulls.list(
                owner=owner, repo=repo, state="open", base=system_pr.head.ref, per_page=100
            ).parsed_data
        )
        epics = [
            pr for pr in children
            if "layer:epic" in label_names(issue(gh_live, owner, repo, pr.number))
        ]
        if not epics:
            return None
        started = [
            pr for pr in epics
            if "確認:epic-conductor" in label_names(issue(gh_live, owner, repo, pr.number))
        ]
        return (system_pr, epics) if len(started) == 1 else None

    # 実行: 構成確定 → 土台生成 → 成果物 PR のマージ → 子epicPR作成 の各ゲートに応答して終端まで進める
    history, (system_pr, epics) = drive_gates(
        gh_live, owner, repo,
        faces=_faces,
        choices={
            ("system_issue", "確認:system-conductor"): None,
            ("system_pr", "確認:system-architect"): None,
            ("system_pr", "確認:system-conductor"): None,
        },
        terminal=_epics_started,
        wait_until=wait_until,
        timeout_sec=5400,
    )
    assert history, "ユーザー確認ゲートが 1 度も開いていない"

    # 検証: 土台が system ブランチに反映されている
    branch = system_pr.head.ref
    missing = [p for p in EXPECTED_PAGES if not _exists(gh_live, owner, repo, p, branch)]
    assert not missing, f"system ブランチに反映されていないページがある: {missing}"

    # 検証: 土台生成の成果物 PR が merged でブランチも削除済み
    closed_prs = gh_live.rest.pulls.list(
        owner=owner, repo=repo, state="closed", per_page=100
    ).parsed_data
    artifacts = [
        p for p in closed_prs
        if f"#{system.number}" in (p.body or "") and p.base.ref == branch
    ]
    assert artifacts, "土台生成の成果物 PR が見つからない"
    assert all(p.merged_at is not None for p in artifacts), "土台生成の成果物 PR が merged になっていない"
    branches = {b.name for b in gh_live.rest.repos.list_branches(
        owner=owner, repo=repo, per_page=100
    ).parsed_data}
    for pr in artifacts:
        assert pr.head.ref not in branches, f"マージした成果物ブランチが残っている: {pr.head.ref}"

    # 検証: system PR は open のまま（master へのマージは全 epic 完了後）
    assert system_pr.state == "open", "system PR が閉じている（system完了マージ は epic 完了後）"
    assert branch in branches, f"system ブランチが削除されている: {branch}"

    # 検証: ラベルが対象リポジトリに一括作成されている
    all_labels = {
        label.name for label in gh_live.rest.issues.list_labels_for_repo(
            owner=owner, repo=repo, per_page=100
        ).parsed_data
    }
    assert "確認:epic-conductor" in all_labels, "ラベルの一括作成が実行されていない"

    # 検証: 全 epic PR に layer / type が付き、base が system ブランチになっている
    for pr in epics:
        pr_labels = label_names(issue(gh_live, owner, repo, pr.number))
        assert "layer:epic" in pr_labels, f"#{pr.number} に layer:epic がない"
        assert "type:feat" in pr_labels, f"#{pr.number} に type:feat がない"
        assert pr.base.ref == branch, f"#{pr.number} の base が system ブランチでない: {pr.base.ref}"

    # 検証: エピック一覧の 対応 PR 列が全行 #N に更新されている
    system_pr_now = issue(gh_live, owner, repo, system_pr.number)
    body = (system_pr_now.body or "").replace("\r\n", "\n")
    epic_rows = [
        line for line in body.split("## エピック一覧", 1)[1].splitlines()
        if line.startswith("|") and "---" not in line and "エピック" not in line
    ]
    assert epic_rows and not any("未作成" in row for row in epic_rows), (
        f"対応 PR 列が更新されていない: {epic_rows}"
    )

    # 検証: 立ち上げ Issue と system PR に確認ラベルが残っていない
    for number in (system.number, system_pr.number):
        names = label_names(issue(gh_live, owner, repo, number))
        assert not [n for n in names if n.startswith("確認:")], (
            f"#{number} に確認ラベルが残っている: {sorted(names)}"
        )

    # 検証: 処理中ラベルがどこにも残っていない（ターン終了の取りこぼしがない）
    targets = [system.number, system_pr.number] + [pr.number for pr in epics]
    for number in targets:
        names = label_names(issue(gh_live, owner, repo, number))
        assert not [n for n in names if n.startswith("処理中:")], (
            f"#{number} に処理中ラベルが残っている: {sorted(names)}"
        )

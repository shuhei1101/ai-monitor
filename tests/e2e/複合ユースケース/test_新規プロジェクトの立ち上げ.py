"""「新規プロジェクトの立ち上げ」の E2E テスト。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

from tests.e2e.ゲート応答 import drive_gates
from tests.e2e.エスカレーション import issue, label_names
from tests.e2e.システム import SYSTEM_BODY, SYSTEM_TITLE

# 土台生成で master に反映されるべきページ
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


def test_normal(
    monitor, gh_live, repo_ctx, system_issue_factory, wait_until, sandbox, master_baseline,
):
    """構成確定から子 epic 一括起票までの一気通しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    system = system_issue_factory(SYSTEM_TITLE, SYSTEM_BODY)

    def _faces():
        # system Issue と、それに紐づく open PR（system PR）が応答対象の面
        faces = [("system_issue", system.number)]
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        faces += [("system_pr", p.number) for p in pulls if f"#{system.number}" in (p.body or "")]
        return faces

    def _epics_started():
        # 子 epic が起票され、着手順の先頭だけが起動した時点で終端
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=system.number
        ).parsed_data
        if not subs:
            return None
        started = [
            s for s in subs
            if "確認:epic-conductor" in label_names(issue(gh_live, owner, repo, s.number))
        ]
        return subs if len(started) == 1 else None

    # 実行: 構成確定 → 土台生成 → マージ → 子epic起票 の各ゲートに応答して終端まで進める
    history, subs = drive_gates(
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

    # 検証: 土台が master に反映されている
    missing = [p for p in EXPECTED_PAGES if not _exists(gh_live, owner, repo, p, "master")]
    assert not missing, f"master に反映されていないページがある: {missing}"

    # 検証: system PR が merged でブランチも削除済み
    closed_prs = gh_live.rest.pulls.list(owner=owner, repo=repo, state="closed", per_page=100).parsed_data
    system_prs = [p for p in closed_prs if f"#{system.number}" in (p.body or "")]
    assert system_prs, "system PR が見つからない"
    assert all(p.merged_at is not None for p in system_prs), "system PR が merged になっていない"
    branches = {b.name for b in gh_live.rest.repos.list_branches(
        owner=owner, repo=repo, per_page=100
    ).parsed_data}
    for pr in system_prs:
        assert pr.head.ref not in branches, f"マージした system ブランチが残っている: {pr.head.ref}"

    # 検証: ラベルが対象リポジトリに一括作成されている
    all_labels = {
        label.name for label in gh_live.rest.issues.list_labels_for_repo(
            owner=owner, repo=repo, per_page=100
        ).parsed_data
    }
    assert "確認:epic-conductor" in all_labels, "ラベルの一括作成が実行されていない"

    # 検証: 全 epic に layer / type が付き、対応 Issue 列が全行 #N に更新されている
    for sub in subs:
        sub_labels = label_names(issue(gh_live, owner, repo, sub.number))
        assert "layer:epic" in sub_labels, f"#{sub.number} に layer:epic がない"
        assert "type:feat" in sub_labels, f"#{sub.number} に type:feat がない"
    system_now = issue(gh_live, owner, repo, system.number)
    body = (system_now.body or "").replace("\r\n", "\n")
    epic_rows = [
        line for line in body.split("## エピック一覧", 1)[1].splitlines()
        if line.startswith("|") and "---" not in line and "エピック名" not in line
    ]
    assert epic_rows and not any("未起票" in row for row in epic_rows), (
        f"対応 Issue 列が更新されていない: {epic_rows}"
    )

    # 検証: system Issue に確認ラベルが残っていない
    assert not [n for n in label_names(system_now) if n.startswith("確認:")], (
        f"system Issue に確認ラベルが残っている: {sorted(label_names(system_now))}"
    )

    # 検証: 処理中ラベルがどこにも残っていない（ターン終了の取りこぼしがない）
    targets = [system.number] + [s.number for s in subs] + [p.number for p in system_prs]
    for number in targets:
        names = label_names(issue(gh_live, owner, repo, number))
        assert not [n for n in names if n.startswith("処理中:")], (
            f"#{number} に処理中ラベルが残っている: {sorted(names)}"
        )

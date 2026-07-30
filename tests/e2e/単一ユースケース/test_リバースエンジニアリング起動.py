"""「リバースエンジニアリング起動」の E2E テスト。

UC は subsystem レベル（依頼先は ss-design-reverse-engineer）で代表する。
他レイヤーは担当と成果物が違うだけで手順は同じ。
"""
from __future__ import annotations

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments_from, issue, label_names, waiting_for_user
from tests.e2e.システム import RE_DONE_REPORT, setup_re_target, watch_numbers
from tests.e2e.実装対象 import SUBSYSTEM_TITLE

RE_LABELS = ["layer:subsystem", "scope:backend", "リバースエンジニアリング", "確認:subsystem-conductor"]
MODULE_PATH = "docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md"
MODULE_MD = """---
template_version: 1.3.0
---

# モジュール構成: バックエンド / タスク

## 一覧

| ユースケース | 役割 | コンテナ | 種別 | 名前 | 概要 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| タスク取得 | 取得 | `src/tasks/service.py` | 関数 | `get_task` | ID 指定で 1 件返す | - |
| タスク更新 | 更新 | `src/tasks/service.py` | 関数 | `update_task` | タイトルと本文を差し替える | - |
| タスク一覧 | 取得 | `src/tasks/service.py` | 関数 | `list_tasks` | ID 順で返す | - |
"""

BOUNCE_REPORT = """> from: @ss-design-reverse-engineer
> to: @subsystem-conductor

担当範囲の実装が見つかりませんでした。

- 探した範囲: `src/` 配下の全ファイル
- `scope:backend` に対応する実装が存在しません

---

---
"""


def _find_re_pr(gh_live, owner, repo, subsystem_number: int):
    """subsystem Issue に紐づく open PR を返す（無ければ None）。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    candidates = [p for p in pulls if f"#{subsystem_number}" in (p.body or "")]
    return candidates[0] if candidates else None


def _file_exists(gh_live, owner, repo, path: str, ref: str) -> bool:
    """指定 ref にファイルが存在するかを返す。"""
    try:
        gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref)
        return True
    except RequestFailed:
        return False


def test_normal_when_request(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox, e2e_state_path,
):
    """RE Draft PR の作成と reverse-engineer への依頼を実環境で確認する（正常系・RE PR の作成と依頼）。"""
    owner, repo = repo_ctx
    ctx = setup_re_target(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        subsystem_labels=RE_LABELS,
    )
    subsystem_number = ctx["subsystem"].number

    # 実行: RE PR の作成と依頼先への引き渡しを待つ
    def _requested():
        pr = _find_re_pr(gh_live, owner, repo, subsystem_number)
        if pr is None:
            return None
        pr_labels = label_names(issue(gh_live, owner, repo, pr.number))
        return pr if "確認:ss-design-reverse-engineer" in pr_labels else None

    pr = wait_until(_requested, timeout_sec=2400, message="RE Draft PR の作成と依頼")

    # 検証: base は通常 PR と同じ story ブランチで、Draft のまま
    assert pr.draft is True, "RE PR が Draft で作成されていない"
    assert pr.base.ref == ctx["story_branch"], f"base が story ブランチでない: {pr.base.ref}"
    pr_body = (pr.body or "").replace("\r\n", "\n")
    assert "## 紐づく Issue" in pr_body, "PR 本文に ## 紐づく Issue がない"
    assert "## タスク一覧" in pr_body, "PR 本文に ## タスク一覧 がない"

    # 検証: 作成した PR の番号が自セッションの監視面に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "subsystem-conductor", subsystem_number), (
        "RE PR の番号が監視面に登録されていない"
    )

    # 検証: 依頼コメントが未解決で投稿されている
    requests = comments_from(gh_live, owner, repo, pr.number, "subsystem-conductor")
    assert requests, "RE の依頼コメントが投稿されていない"
    assert not server._is_minimized(requests[-1].node_id), "依頼コメントが Resolve されている"

    # 検証: 通常 PR はまだ作られておらず、対象 Issue の担当は conductor のまま
    open_prs = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    linked = [p for p in open_prs if f"#{subsystem_number}" in (p.body or "")]
    assert len(linked) == 1, f"RE PR 以外の PR が作られている: {[p.number for p in linked]}"
    assert "確認:subsystem-conductor" in label_names(issue(gh_live, owner, repo, subsystem_number)), (
        "対象 Issue の 確認:subsystem-conductor が外れている（マージまで担当を持つ）"
    )


def test_normal_when_merge(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox, e2e_state_path,
):
    """完了報告の受領と RE PR のマージを実環境で確認する（正常系・完了報告の受領とマージ）。"""
    owner, repo = repo_ctx
    ctx = setup_re_target(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        subsystem_labels=["layer:subsystem", "scope:backend", "リバースエンジニアリング"],
    )
    subsystem_number = ctx["subsystem"].number
    # 準備: RE が現状の設計書を commit 済みの RE PR を再現する
    re_branch_name = f"docs/reverse/backend/task-edit-{subsystem_number}"
    re_pr = draft_pr_factory(
        re_branch_name, f"{SUBSYSTEM_TITLE}（現状の設計書）",
        f"## 紐づく Issue\n\n- #{subsystem_number}\n\n## タスク一覧\n\n- [x] 現状のモジュール構成を起こす\n",
        base_branch=ctx["story_branch"],
    )
    commit_file(re_branch_name, MODULE_PATH, MODULE_MD, "docs: 現状のモジュール構成を追加")

    # 準備: RE の完了報告 → 確認:subsystem-conductor 付与（マージの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=re_pr.number,
        body=RE_DONE_REPORT.format(sender="ss-design-reverse-engineer", receiver="subsystem-conductor"),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=re_pr.number, labels=["確認:subsystem-conductor"]
    )

    # 実行: RE PR のマージを待つ
    def _merged():
        data = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=re_pr.number).parsed_data
        return data if data.merged else None

    wait_until(_merged, timeout_sec=2400, message="RE PR のマージ")

    # 検証: base ブランチに現状の設計書が入っている
    assert _file_exists(gh_live, owner, repo, MODULE_PATH, ctx["story_branch"]), (
        "base ブランチに現状の設計書が入っていない"
    )

    # 検証: RE ブランチが削除されている
    assert not _file_exists(gh_live, owner, repo, MODULE_PATH, re_branch_name), (
        "RE ブランチが残っている"
    )

    # 検証: RE PR の番号が監視面から除去されている
    def _watch_updated():
        numbers = watch_numbers(e2e_state_path, "subsystem-conductor", subsystem_number)
        return True if re_pr.number not in numbers else None

    wait_until(_watch_updated, timeout_sec=900, message="RE PR の番号が監視面から除去")

    # 検証: 対象 Issue は要件確定へ続くので担当と空の本文がそのまま残っている
    subsystem_now = issue(gh_live, owner, repo, subsystem_number)
    assert "確認:subsystem-conductor" in label_names(subsystem_now), (
        "対象 Issue の 確認:subsystem-conductor が外れている（要件確定へ続く）"
    )
    assert not (subsystem_now.body or "").strip(), f"対象 Issue の本文が埋まっている: {subsystem_now.body}"

    # 検証: 自分宛コメントが Resolve 済み
    assert server._is_minimized(report.node_id), "RE の完了報告が未 Resolve"


def test_error_when_bounced(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """RE からの差し戻しでユーザーへ相談することを実環境で確認する（異常系・RE からの差し戻し）。"""
    owner, repo = repo_ctx
    ctx = setup_re_target(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        subsystem_labels=["layer:subsystem", "scope:backend", "リバースエンジニアリング"],
    )
    subsystem_number = ctx["subsystem"].number
    # 準備: 設計書が 1 ページも commit されていない RE PR を再現する
    re_branch_name = f"docs/reverse/backend/task-edit-{subsystem_number}"
    re_pr = draft_pr_factory(
        re_branch_name, f"{SUBSYSTEM_TITLE}（現状の設計書）",
        f"## 紐づく Issue\n\n- #{subsystem_number}\n\n## タスク一覧\n\n- [ ] 現状のモジュール構成を起こす\n",
        base_branch=ctx["story_branch"],
    )

    # 準備: RE の差し戻し報告 → 確認:subsystem-conductor 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=re_pr.number, body=BOUNCE_REPORT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=re_pr.number, labels=["確認:subsystem-conductor"]
    )

    # 実行: ユーザーへの相談（議論中 + assignee）を待つ
    def _consulted():
        data = issue(gh_live, owner, repo, re_pr.number)
        if not waiting_for_user(data):
            return None
        consults = comments_from(gh_live, owner, repo, re_pr.number, "subsystem-conductor")
        return (data, consults[-1]) if consults else None

    _, consult = wait_until(_consulted, timeout_sec=2400, message="差し戻しのユーザー相談（議論中 + assignee）")

    # 検証: 相談コメントが未解決で、設計書は 1 ページも入っていない
    assert not server._is_minimized(consult.node_id), "相談コメントが Resolve されている"
    assert not _file_exists(gh_live, owner, repo, MODULE_PATH, re_branch_name), (
        "設計書が commit されている（差し戻し時は commit しない）"
    )

    # 検証: RE PR はマージされていない
    pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=re_pr.number).parsed_data
    assert pr_now.merged is False, "差し戻しのまま RE PR がマージされている"

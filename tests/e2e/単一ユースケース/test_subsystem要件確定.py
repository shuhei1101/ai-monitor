"""「subsystem要件確定」の E2E テスト。"""
from __future__ import annotations

from pathlib import Path

import yaml
from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.ゲート応答 import drive_gates
from tests.e2e.エスカレーション import issue, label_names

INTAKE_TITLE = "タスク編集機能"
INTAKE_BODY = "既存タスクを編集できる機能を追加する。"

EPIC_TITLE = "タスク編集機能"
EPIC_BODY = """## 前提条件

なし

## 概要

既存タスクを一覧から選択して編集できる機能を提供する。

## 背景

現状はタスクの新規作成のみで編集導線がなく、内容の修正ができない。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| タスク編集 | 一覧から編集画面へ遷移して編集内容を保存する | 起票済み |

## 横断要件

- 保存時は既存 API を利用する
"""

STORY_TITLE = "タスク編集"
STORY_BODY_TEMPLATE = """## 前提条件

なし

## 概要

ユーザーが一覧からタスクを選択して、内容を編集して保存する。

## 背景

親 epic #{epic_number} の UC「タスク編集」に対応。既存の一覧画面から編集導線を追加する必要がある。

## ユースケース要件

| 要件 | 補足 |
| --- | --- |
| 一覧からタスクを選択して編集画面に遷移できる | - |
| タスクの内容を編集して保存できる | - |
| 保存時にバリデーションエラーをインライン表示 | フィールド直下に表示 |
| 保存成功時にトーストで通知 | 3 秒表示 |
"""

SCENARIO_PATH = "docs/wiki/設計図/シナリオ/単一ユースケース/タスク編集.md"
SCENARIO_MD = """---
template_version: 1.0.0
---

# タスク編集

一覧から選択したタスクの内容を編集して保存する単一ユースケース。

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| タスク | 編集対象のタスクを 1 件登録済み | - |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant FE as タスク編集画面
  participant BE as バックエンド API

  U->>FE: 一覧から対象タスクを選んで編集画面を開く
  U->>FE: 内容を編集して保存
  FE->>FE: 入力バリデーション
  FE->>BE: タスク更新リクエスト
  BE-->>FE: 更新後のタスク
  FE-->>U: 一覧へ戻り 完了トースト表示
```

### 期待値

- 一覧に編集後の内容が表示されている
- 完了トーストが表示されている

## 異常シナリオ（必須項目が空）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 入力 | タスク名を空にして保存 | 検証失敗を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant FE as タスク編集画面

  U->>FE: タスク名を空にして保存
  FE->>FE: 入力バリデーション失敗
  FE-->>U: フィールド直下にインラインエラー表示
```

### 期待値

- インラインエラーが表示され、保存されていない
"""

SUBSYSTEM_TITLE = "タスク編集 バックエンド"
CURRENT_SUBSECTIONS = ["### 関連 Issue/PR", "### 関連ドキュメント"]
SA_SUBSECTIONS = ["### 機能要件", "### 非機能要件", "### スコープ外"]


def _watch_numbers(state_path: Path, subsystem_number: int) -> list[int]:
    """モニター台帳から subsystem-conductor セッションの監視面番号一覧を返す。"""
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        # subsystem-conductor × subsystem 主番号のセッションを探す
        if entry["agent_name"] == "subsystem-conductor" and entry["primary_number"] == subsystem_number:
            return entry["watch_numbers"]
    return []


def test_normal(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    subsystem_issue_factory,
    commit_file,
    wait_until,
    e2e_state_path,
):
    """SA 確定 → 承認 → subsystem Draft PR 作成 → タスク一覧承認 → architect 引き継ぎを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: epic Issue + epic Draft PR（確認ラベルなし）
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    # 準備: 要件確定済みの story Issue（確認ラベルなし・親 epic 付き）
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number), labels=["layer:story"],
    )
    # 準備: story Draft PR（base=epic ブランチ）と、story ブランチ上の単一 UC シナリオ
    story_branch = f"feat/story/task-edit-{story.number}"
    draft_pr_factory(
        story_branch, STORY_TITLE, f"## 紐づく Issue\n\n- #{story.number}\n", base_branch=epic_branch
    )
    commit_file(story_branch, SCENARIO_PATH, SCENARIO_MD, "docs: 単一UC シナリオ（タスク編集）を追加")
    # 準備: 子 subsystem Issue（layer:subsystem + 確認:subsystem-conductor + 本文空）
    subsystem = subsystem_issue_factory(story.number, SUBSYSTEM_TITLE)

    # 実行: モニターの polling 検知 → 要件確定（初回）の完了を待つ（議論中 + assignee）
    def _first_turn_done():
        data = _get(subsystem.number)
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    data = wait_until(_first_turn_done, timeout_sec=1800, message="要件確定（初回）の完了（議論中 + assignee）")

    # 検証: 本文に 現状 2 サブセクションと システム要件（SA）3 サブセクションが揃っている
    body = (data.body or "").replace("\r\n", "\n")
    assert "## 現状" in body, "本文に ## 現状 がない"
    assert "## システム要件（SA）" in body, "本文に ## システム要件（SA） がない"
    for section in CURRENT_SUBSECTIONS + SA_SUBSECTIONS:
        assert section in body, f"本文に {section} がない"
    assert f"#{story.number}" in body, "背景に親 story の番号がない"
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=subsystem.number).parsed_data
    assert comments, "完了報告・確認質問コメントが投稿されていない"

    # 実行: ユーザー回答（回答コメント + assignee 外し）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=subsystem.number,
        body="A（本 subsystem の担当範囲で合っています）でお願いします。",
    )
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=subsystem.number, assignees=[assignee.login]
        )

    # 応答ループの完了を待つ（assignee 再設定）
    def _reply_turn_done():
        data = _get(subsystem.number)
        return data if data.assignees else None

    data = wait_until(_reply_turn_done, timeout_sec=1200, message="応答ループの完了（assignee 再設定）")

    # 実行: SA 承認（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=subsystem.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=subsystem.number, assignees=[assignee.login]
        )

    # 要件確定（完了処理）の完了を待つ（subsystem PR 作成 + PR 側 議論中 + assignee）
    def _pr_gate_open():
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open").parsed_data
        candidates = [pr for pr in pulls if f"#{subsystem.number}" in (pr.body or "")]
        if len(candidates) != 1:
            return None
        pr_data = _get(candidates[0].number)
        labels = {label.name for label in pr_data.labels}
        return candidates[0] if "議論中" in labels and pr_data.assignees else None

    pr = wait_until(_pr_gate_open, timeout_sec=1800, message="要件確定（完了処理）の完了（PR 作成 + 議論中 + assignee）")

    # 検証: subsystem Draft PR が base=親 story ブランチで、本文に 紐づく Issue と タスク一覧がある
    assert pr.draft is True
    assert pr.base.ref == story_branch, f"subsystem PR の base が親 story ブランチでない: {pr.base.ref}"
    pr_body = (pr.body or "").replace("\r\n", "\n")
    sections = [line for line in pr_body.splitlines() if line.startswith("## ")]
    assert sections == ["## 紐づく Issue", "## タスク一覧"], f"PR 本文のセクションが想定と異なる: {sections}"
    assert f"- #{subsystem.number}" in pr_body, "紐づく Issue に subsystem Issue 番号がない"
    assert "- [ ]" in pr_body, "タスク一覧がチェックボックス形式で記入されていない"

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in _watch_numbers(e2e_state_path, subsystem.number)

    # 検証: タスク一覧の確認コメントが投稿されている
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    assert pr_comments, "タスク一覧の確認コメントが投稿されていない"

    # 実行: タスク一覧の承認（議論中 除去 + assignee 外し）
    pr_data = _get(pr.number)
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in pr_data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    # 要件確定（完了処理）の完了を待つ（PR に 確認:architect + Issue から 確認:subsystem-conductor 除去）
    def _handed_off():
        pr_now = _get(pr.number)
        issue_now = _get(subsystem.number)
        pr_labels = {label.name for label in pr_now.labels}
        issue_labels = {label.name for label in issue_now.labels}
        if "確認:architect" not in pr_labels:
            return None
        return (pr_now, issue_now) if not any(n.startswith("確認:") for n in issue_labels) else None

    wait_until(_handed_off, timeout_sec=1200, message="要件確定（完了処理）の完了（確認:architect 付与 + 確認:* 除去）")

    # 検証: Issue / PR のエージェント投稿コメントが全て Resolve 済み
    for number in (subsystem.number, pr.number):
        comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=number).parsed_data
        agent_comments = [c for c in comments if c.body.lstrip().startswith("> from:")]
        assert agent_comments, f"#{number} にエージェントのコメントが見つからない"
        for comment in agent_comments:
            assert server._is_minimized(comment.node_id), f"コメント {comment.html_url} が未 Resolve"


# base（親 story ブランチ）にある現状の設計書（RE PR がマージ済みの状態）
CURRENT_MODULE_PATH = "docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md"
CURRENT_MODULE_MD = """# モジュール構成: バックエンド / タスク

現状の実装から起こしたモジュール構成。

## 一覧

| ユースケース | 役割 | コンテナ | 種別 | 名前 | 概要 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| タスク編集 | サービス | `src/tasks/service.py` | 関数 | `update_task` | タスクのタイトルと本文を更新する | 検証は呼び出し側に散っている |
"""


def test_normal_when_reverse(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, e2e_state_path,
):
    """現状の設計書を入力にした subsystem 要件確定を実環境で確認する（正常系・リバースエンジニアリング）。"""
    owner, repo = repo_ctx
    # 準備: RE 経路の epic / story と、現状の設計書が入った story ブランチ
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY,
        epic_labels=["layer:epic", "type:docs", "リバースエンジニアリング"],
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number),
        labels=["layer:story", "type:docs", "リバースエンジニアリング"],
    )
    story_branch = f"feat/story/task-edit-{story.number}"
    draft_pr_factory(
        story_branch, STORY_TITLE, f"## 紐づく Issue\n\n- #{story.number}\n", base_branch=epic_branch
    )
    commit_file(story_branch, SCENARIO_PATH, SCENARIO_MD, "docs: 単一UC シナリオ（タスク編集）を追加")
    commit_file(story_branch, CURRENT_MODULE_PATH, CURRENT_MODULE_MD, "docs: 現状のモジュール構成を追加")
    subsystem = subsystem_issue_factory(
        story.number, SUBSYSTEM_TITLE,
        labels=["layer:subsystem", "type:docs", "scope:backend", "リバースエンジニアリング",
                "確認:subsystem-conductor"],
    )

    def _faces():
        # subsystem Issue と、作成された subsystem PR が応答対象の面
        faces = [("subsystem_issue", subsystem.number)]
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        faces += [("subsystem_pr", p.number) for p in pulls if f"#{subsystem.number}" in (p.body or "")]
        return faces

    def _handed_to_architect():
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        for pr in pulls:
            if f"#{subsystem.number}" not in (pr.body or ""):
                continue
            if "確認:architect" in label_names(issue(gh_live, owner, repo, pr.number)):
                return pr
        return None

    # 実行: SA 確認 → タスク一覧確認 の各ゲートに応答して architect への引き渡しまで進める
    history, pr = drive_gates(
        gh_live, owner, repo,
        faces=_faces,
        choices={
            ("subsystem_issue", "確認:subsystem-conductor"): "現状の設計書どおりの担当範囲で合っています。",
            ("subsystem_pr", "確認:subsystem-conductor"): None,
        },
        terminal=_handed_to_architect,
        wait_until=wait_until,
        timeout_sec=3600,
    )
    assert history, "ユーザー確認ゲートが 1 度も開いていない"

    # 検証: 本文に 現状 と システム要件（SA）が揃い、現状の設計書が更新対象に挙がっている
    body = (issue(gh_live, owner, repo, subsystem.number).body or "").replace("\r\n", "\n")
    assert "## 現状" in body, "本文に ## 現状 がない"
    assert "## システム要件（SA）" in body, "本文に ## システム要件（SA） がない"
    assert CURRENT_MODULE_PATH.split("docs/wiki/")[1] in body or "モジュール構成" in body, (
        "関連ドキュメントに現状の設計書が挙がっていない"
    )

    # 検証: subsystem Draft PR が base=親 story ブランチで、タスク一覧が記入されている
    assert pr.draft is True
    assert pr.base.ref == story_branch, f"subsystem PR の base が親 story ブランチでない: {pr.base.ref}"
    pr_body = (pr.body or "").replace("\r\n", "\n")
    assert "## タスク一覧" in pr_body, "PR 本文にタスク一覧がない"

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in _watch_numbers(e2e_state_path, subsystem.number)
    assert intake is not None

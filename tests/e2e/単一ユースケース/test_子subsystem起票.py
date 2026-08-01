"""「子subsystem起票」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server

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

SCENARIO_DONE_REPORT = """> from: @single-scenario-writer
> to: @story-conductor

単一 UC シナリオ「タスク編集」の設計が完了しました。

- ファイル: `docs/wiki/設計図/シナリオ/単一ユースケース/タスク編集.md`
- 正常シナリオ: 一覧から編集画面へ遷移 → 保存 → 一覧へ戻って完了トースト
- 異常シナリオ（必須項目が空）: タスク名を空にして保存するとインラインエラー

確認後に本コメントの Resolve をお願いします。

------
"""

INTERFACE_DONE_REPORT = """> from: @subsystem-conductor
> to: @story-conductor

subsystem #{subsystem_number} のインターフェースが確定しました（設計は続行中）。

- 確定した結合ドキュメント: `設計図/インターフェース定義/バックエンド/タスク更新.py.md`
- リクエスト: `PATCH /tasks/{{task_id}}`（body に `title` / `content`）
- レスポンス: 更新後のタスク（`id` / `title` / `content` / `updated_at`）

後続 subsystem の起票をお願いします。

------
"""

SUBSYSTEM_TITLE_BE = "タスク編集 バックエンド"

# 子subsystem起票（初回）が記入した後の状態（先頭グループの BE だけ起票済み）
SUBSYSTEM_TABLE = """
## サブシステム一覧

| 対象システム | 担当範囲 | 依存 | 対応 subsystem | 補足 |
| --- | --- | --- | --- | --- |
| バックエンド | タスク更新 API と入力検証 | なし | #{backend_number} | - |
| フロントエンド | タスク編集画面と保存導線 | バックエンド | 未起票 | インターフェース確定後に起票 |
"""


def _row(body: str, keyword: str) -> str:
    """サブシステム一覧から指定の対象システムの行を取り出す。"""
    rows = [line for line in body.replace("\r\n", "\n").splitlines() if line.startswith("|") and keyword in line]
    assert rows, f"サブシステム一覧に「{keyword}」の行がない"
    return rows[0]


def _story_subs(gh_live, owner, repo, story_number):
    """story Issue の Sub-issue 一覧を返す。"""
    return gh_live.rest.issues.list_sub_issues(
        owner=owner, repo=repo, issue_number=story_number
    ).parsed_data


def _setup_story(
    gh_live,
    owner,
    repo,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    commit_file,
):
    """要件確定済みの epic / story と、story ブランチ上の単一 UC シナリオを用意する。"""
    # epic Issue + epic Draft PR（確認ラベルなし = 起動対象にしない）
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    # 要件確定済みの story Issue（確認ラベルは最後に付ける）
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number), labels=["layer:story", "type:feat"],
    )
    # story Draft PR（base=epic ブランチ）と、story ブランチ上の単一 UC シナリオ
    story_branch = f"feat/story/task-edit-{story.number}"
    draft_pr_factory(
        story_branch, STORY_TITLE, f"## 紐づく Issue\n\n- #{story.number}\n", base_branch=epic_branch
    )
    commit_file(story_branch, SCENARIO_PATH, SCENARIO_MD, "docs: 単一UC シナリオ（タスク編集）を追加")
    return story


def test_normal_when_first(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    wait_until,
    commit_file,
):
    """依存順の決定と先頭グループのみの起票を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    story = _setup_story(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file,
    )

    # 準備: single-scenario-writer の完了報告 → 確認:story-conductor 付与（起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story.number, body=SCENARIO_DONE_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=story.number, labels=["確認:story-conductor"]
    )

    # 実行: 子subsystem起票（初回）の完了を待つ（確認:story-conductor 除去 + Sub-issue 出現）
    def _first_done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=story.number).parsed_data
        labels = {label.name for label in data.labels}
        if any(name.startswith("確認:") for name in labels):
            return None
        subs = _story_subs(gh_live, owner, repo, story.number)
        return (data, subs) if subs else None

    data, subs = wait_until(
        _first_done, timeout_sec=1800, message="子subsystem起票（初回）の完了（確認:* 除去 + Sub-issue 起票）"
    )

    # 検証: 依存のない先頭グループだけが起票されている（FE は BE 依存のため未起票）
    assert len(subs) == 1, f"先頭グループ以外も起票されている: {[(s.number, s.title) for s in subs]}"
    sub_data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=subs[0].number).parsed_data
    sub_labels = {label.name for label in sub_data.labels}
    assert "layer:subsystem" in sub_labels, f"layer:subsystem がない: {sub_labels}"
    assert "確認:subsystem-conductor" in sub_labels, f"確認:subsystem-conductor がない: {sub_labels}"
    assert any(name.startswith("scope:") for name in sub_labels), f"scope:* ラベルがない: {sub_labels}"

    # 検証: サブシステム一覧に洗い出し結果が記入され、起票済みの行だけ Issue 番号が入っている
    body_after = (data.body or "").replace("\r\n", "\n")
    assert "## サブシステム一覧" in body_after, "story 本文に ## サブシステム一覧 がない"
    assert f"#{subs[0].number}" in body_after, "起票した subsystem の番号がサブシステム一覧に入っていない"
    assert "未起票" in body_after, "未起票の subsystem の行がない（全件起票された可能性）"

    # 検証: 議論中 なし・assignee なしで自動完了している
    labels_after = {label.name for label in data.labels}
    assert "議論中" not in labels_after, "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"

    # 検証: 完了報告が Resolve され、起票結果の報告コメントが投稿されている
    assert server._is_minimized(report.node_id), "single-scenario-writer の完了報告が未 Resolve"
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=story.number
    ).parsed_data
    assert any(
        (c.body or "").lstrip().startswith("> from: @story-conductor") for c in comments
    ), "起票結果の報告コメントが投稿されていない"


def test_normal_when_sequential(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    subsystem_issue_factory,
    wait_until,
    commit_file,
):
    """インターフェース確定報告を受けた次 subsystem の逐次起票を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    story = _setup_story(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file,
    )
    # 準備: 先頭グループ（BE）は起票済み（確認ラベルなし = subsystem-conductor を起動させない）
    backend = subsystem_issue_factory(
        story.number, SUBSYSTEM_TITLE_BE, labels=["layer:subsystem", "scope:backend"]
    )
    # 準備: 初回起票が記入した後の状態（BE は起票済み・FE は未起票）を本文に再現する
    story_body = (
        gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=story.number).parsed_data.body or ""
    )
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=story.number,
        body=story_body + SUBSYSTEM_TABLE.format(backend_number=backend.number),
    )

    # 準備: subsystem-conductor のインターフェース確定報告 → 確認:story-conductor 付与（起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story.number,
        body=INTERFACE_DONE_REPORT.format(subsystem_number=backend.number),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=story.number, labels=["確認:story-conductor"]
    )

    # 実行: 子subsystem起票（逐次）の完了を待つ（確認:story-conductor 除去 + Sub-issue が 2 件）
    def _sequential_done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=story.number).parsed_data
        labels = {label.name for label in data.labels}
        if any(name.startswith("確認:") for name in labels):
            return None
        subs = _story_subs(gh_live, owner, repo, story.number)
        return (data, subs) if len(subs) >= 2 else None

    data, subs = wait_until(
        _sequential_done, timeout_sec=1800, message="子subsystem起票（逐次）の完了（確認:* 除去 + 2 件目の起票）"
    )

    # 検証: 次の subsystem が 1 件だけ追加されている
    assert len(subs) == 2, f"起票数が想定と異なる: {[(s.number, s.title) for s in subs]}"
    added = [s for s in subs if s.number != backend.number]
    assert len(added) == 1, f"追加された subsystem が 1 件でない: {[(s.number, s.title) for s in added]}"
    added_data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=added[0].number).parsed_data
    added_labels = {label.name for label in added_data.labels}
    assert "layer:subsystem" in added_labels, f"layer:subsystem がない: {added_labels}"
    assert "確認:subsystem-conductor" in added_labels, f"確認:subsystem-conductor がない: {added_labels}"
    assert any(name.startswith("scope:") for name in added_labels), f"scope:* ラベルがない: {added_labels}"
    assert "scope:backend" not in added_labels, "先頭グループと同じ scope で起票されている"

    # 検証: サブシステム一覧のフロントエンド行が起票した Issue 番号に更新されている
    body_after = (data.body or "").replace("\r\n", "\n")
    frontend_row = _row(body_after, "フロントエンド")
    assert f"#{added[0].number}" in frontend_row, (
        f"サブシステム一覧の該当行が起票した番号に更新されていない: {frontend_row}"
    )
    assert "未起票" not in frontend_row, f"該当行に 未起票 が残っている: {frontend_row}"

    # 検証: インターフェース確定報告が Resolve されている
    assert server._is_minimized(report.node_id), "インターフェース確定報告が未 Resolve"

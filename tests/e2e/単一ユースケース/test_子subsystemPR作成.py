"""「子subsystemPR作成」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server

INTAKE_TITLE = "タスク編集機能"
INTAKE_BODY = "既存タスクを編集できる機能を追加する。"

EPIC_TITLE = "タスク編集機能"
EPIC_PR_BODY = """## 紐づく Issue

- #{intake_number}

## 概要

既存タスクを一覧から選択して編集できる機能を提供する。

## 背景

現状はタスクの新規作成のみで編集導線がなく、内容の修正ができない。

## ユースケース一覧

| ユースケース | 変更種別 | 概要 | 対応 story | 補足 |
| --- | --- | --- | --- | --- |
| タスク編集 | 変更 | 一覧から編集画面へ遷移して編集内容を保存する | #{story_placeholder} | - |

## 横断要件

| カテゴリ | 要件 | 対象 UC | 補足 |
| --- | --- | --- | --- |
| 既存 API | 保存時は既存 API を利用する | 全 UC | - |
"""

STORY_TITLE = "タスク編集"
STORY_PR_BODY = """## 紐づく Issue

- #{intake_number}

## 概要

ユーザーが一覧からタスクを選択して、内容を編集して保存する。

## 背景

親 epic の UC「タスク編集」に対応。既存の一覧画面から編集導線を追加する必要がある。

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

後続 subsystem の PR 作成をお願いします。

------
"""

SUBSYSTEM_TITLE_BE = "タスク編集 バックエンド"

# 子subsystemPR作成（初回）が記入した後の状態（先頭グループの BE だけ作成済み）
SUBSYSTEM_TABLE = """
## サブシステム一覧

| 対象システム | 担当範囲 | 依存 | 対応 subsystem | 補足 |
| --- | --- | --- | --- | --- |
| バックエンド | タスク更新 API と入力検証 | なし | #{backend_number} | - |
| フロントエンド | タスク編集画面と保存導線 | バックエンド | 未作成 | インターフェース確定後に作成 |
"""


def _issue(gh_live, owner, repo, number):
    """Issue / PR の最新状態を返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def _labels(data) -> set[str]:
    """ラベル名の集合を返す。"""
    return {label.name for label in data.labels}


def _row(body: str, keyword: str) -> str:
    """サブシステム一覧から指定の対象システムの行を取り出す。"""
    rows = [
        line for line in body.replace("\r\n", "\n").splitlines()
        if line.startswith("|") and keyword in line
    ]
    assert rows, f"サブシステム一覧に「{keyword}」の行がない"
    return rows[0]


def _children(gh_live, owner, repo, base_branch) -> list:
    """指定ブランチを base にした open PR を返す。"""
    return list(
        gh_live.rest.pulls.list(
            owner=owner, repo=repo, state="open", base=base_branch, per_page=100
        ).parsed_data
    )


def _setup_story(gh_live, owner, repo, issue_factory, layer_pr_factory, commit_file):
    """要件確定済みの epic / story PR と、story ブランチ上の単一 UC シナリオを用意する。"""
    intake = issue_factory(
        title=INTAKE_TITLE, body=INTAKE_BODY, labels=["layer:intake", "type:feat"]
    )
    # epic PR（確認ラベルなし = 起動対象にしない）
    epic_branch = f"feat/epic/task-edit-{intake.number}/base"
    layer_pr_factory(
        epic_branch, EPIC_TITLE,
        EPIC_PR_BODY.format(intake_number=intake.number, story_placeholder="0"),
        labels=["layer:epic", "type:feat"],
    )
    # 要件確定済みの story PR（確認ラベルは最後に付ける）
    story_branch = f"feat/story/task-edit-{intake.number}/base"
    story_pr = layer_pr_factory(
        story_branch, STORY_TITLE, STORY_PR_BODY.format(intake_number=intake.number),
        base_branch=epic_branch, labels=["layer:story", "type:feat"],
    )
    commit_file(story_branch, SCENARIO_PATH, SCENARIO_MD, "docs: 単一UC シナリオ（タスク編集）を追加")
    return story_pr, story_branch


def test_normal_when_first(
    monitor, gh_live, repo_ctx, issue_factory, layer_pr_factory, commit_file, wait_until
):
    """依存順の決定と先頭グループのみの PR 作成を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    story_pr, story_branch = _setup_story(
        gh_live, owner, repo, issue_factory, layer_pr_factory, commit_file
    )

    # 準備: single-scenario-writer の完了報告 → 確認:story-conductor 付与（起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story_pr.number, body=SCENARIO_DONE_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=story_pr.number, labels=["確認:story-conductor"]
    )

    # 実行: 子subsystemPR作成（初回）の完了を待つ（確認:* 除去 + story ブランチ上の子 PR）
    def _first_done():
        data = _issue(gh_live, owner, repo, story_pr.number)
        if any(name.startswith("確認:") for name in _labels(data)):
            return None
        children = _children(gh_live, owner, repo, story_branch)
        return (data, children) if children else None

    data, children = wait_until(
        _first_done, timeout_sec=1800, message="子subsystemPR作成（初回）の完了（確認:* 除去 + 子 PR）"
    )

    # 検証: 依存のない先頭グループだけが作られている（FE は BE 依存のため未作成）
    assert len(children) == 1, f"先頭グループ以外も作られている: {[(p.number, p.title) for p in children]}"
    child = children[0]
    assert child.base.ref == story_branch, f"base が story ブランチでない: {child.base.ref}"
    assert child.draft, f"#{child.number} が Draft でない"
    sub_labels = _labels(_issue(gh_live, owner, repo, child.number))
    assert "layer:subsystem" in sub_labels, f"layer:subsystem がない: {sorted(sub_labels)}"
    assert "確認:subsystem-conductor" in sub_labels, f"確認:subsystem-conductor がない: {sorted(sub_labels)}"
    assert any(name.startswith("scope:") for name in sub_labels), f"scope:* ラベルがない: {sorted(sub_labels)}"

    # 検証: サブシステム一覧に洗い出し結果が記入され、作成済みの行だけ番号が入っている
    body_after = (data.body or "").replace("\r\n", "\n")
    assert "## サブシステム一覧" in body_after, "story PR 本文に ## サブシステム一覧 がない"
    assert f"#{child.number}" in body_after, "作成した subsystem の番号がサブシステム一覧に入っていない"
    assert "未作成" in body_after, "未作成の subsystem の行がない（全件作られた可能性）"

    # 検証: 議論中 なし・assignee なしで自動完了している
    labels_after = _labels(data)
    assert "議論中" not in labels_after, "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"

    # 検証: 完了報告が Resolve され、作成結果の報告コメントが投稿されている
    assert server._is_minimized(report.node_id), "single-scenario-writer の完了報告が未 Resolve"
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=story_pr.number
    ).parsed_data
    assert any(
        (c.body or "").lstrip().startswith("> from: @story-conductor") for c in comments
    ), "作成結果の報告コメントが投稿されていない"


def test_normal_when_sequential(
    monitor, gh_live, repo_ctx, issue_factory, layer_pr_factory, commit_file, wait_until
):
    """インターフェース確定報告を受けた次 subsystem の逐次作成を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    story_pr, story_branch = _setup_story(
        gh_live, owner, repo, issue_factory, layer_pr_factory, commit_file
    )

    # 準備: 先頭グループ（BE）は作成済み（確認ラベルなし = subsystem-conductor を起動させない）
    backend = layer_pr_factory(
        f"feat/backend/task-edit-{story_pr.number}/base", SUBSYSTEM_TITLE_BE,
        f"## 紐づく Issue\n\n- #{story_pr.number}\n",
        base_branch=story_branch, labels=["layer:subsystem", "scope:backend"],
    )
    # 準備: 初回作成が記入した後の状態（BE は作成済み・FE は未作成）を本文に再現する
    story_body = _issue(gh_live, owner, repo, story_pr.number).body or ""
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=story_pr.number,
        body=story_body + SUBSYSTEM_TABLE.format(backend_number=backend.number),
    )

    # 準備: subsystem-conductor のインターフェース確定報告 → 確認:story-conductor 付与（起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story_pr.number,
        body=INTERFACE_DONE_REPORT.format(subsystem_number=backend.number),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=story_pr.number, labels=["確認:story-conductor"]
    )

    # 実行: 子subsystemPR作成（逐次）の完了を待つ（確認:* 除去 + 子 PR が 2 件）
    def _sequential_done():
        data = _issue(gh_live, owner, repo, story_pr.number)
        if any(name.startswith("確認:") for name in _labels(data)):
            return None
        children = _children(gh_live, owner, repo, story_branch)
        return (data, children) if len(children) >= 2 else None

    data, children = wait_until(
        _sequential_done, timeout_sec=1800, message="子subsystemPR作成（逐次）の完了（2 件目の作成）"
    )

    # 検証: 次の subsystem が 1 件だけ追加されている
    assert len(children) == 2, f"作成数が想定と異なる: {[(p.number, p.title) for p in children]}"
    added = [p for p in children if p.number != backend.number]
    assert len(added) == 1, f"追加された subsystem が 1 件でない: {[(p.number, p.title) for p in added]}"
    added_labels = _labels(_issue(gh_live, owner, repo, added[0].number))
    assert "layer:subsystem" in added_labels, f"layer:subsystem がない: {sorted(added_labels)}"
    assert "確認:subsystem-conductor" in added_labels, f"確認:subsystem-conductor がない: {sorted(added_labels)}"
    assert any(name.startswith("scope:") for name in added_labels), f"scope:* ラベルがない: {sorted(added_labels)}"
    assert "scope:backend" not in added_labels, "先頭グループと同じ scope で作成されている"
    assert added[0].base.ref == story_branch, f"base が story ブランチでない: {added[0].base.ref}"

    # 検証: サブシステム一覧のフロントエンド行が作成した PR 番号に更新されている
    body_after = (data.body or "").replace("\r\n", "\n")
    frontend_row = _row(body_after, "フロントエンド")
    assert f"#{added[0].number}" in frontend_row, (
        f"サブシステム一覧の該当行が作成した番号に更新されていない: {frontend_row}"
    )
    assert "未作成" not in frontend_row, f"該当行に 未作成 が残っている: {frontend_row}"

    # 検証: インターフェース確定報告が Resolve されている
    assert server._is_minimized(report.node_id), "インターフェース確定報告が未 Resolve"

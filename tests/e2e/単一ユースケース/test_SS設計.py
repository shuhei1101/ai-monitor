"""「SS設計」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from githubkit.exception import RequestFailed

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
  FE->>BE: タスク更新リクエスト
  BE-->>FE: 更新後のタスク
  FE-->>U: 一覧へ戻り 完了トースト表示
```

### 期待値

- 一覧に編集後の内容が表示されている

## 異常シナリオ（タスク名が空）

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
  participant BE as バックエンド API

  U->>FE: タスク名を空にして保存
  FE->>BE: タスク更新リクエスト
  BE-->>FE: 検証エラー
  FE-->>U: フィールド直下にインラインエラー表示
```

### 期待値

- インラインエラーが表示され、保存されていない
"""

SUBSYSTEM_TITLE = "タスク編集 バックエンド"
SUBSYSTEM_BODY_TEMPLATE = """## 前提条件

なし

## 概要

タスク編集のバックエンド側（タスク更新 API と入力検証）を担当する。

## 背景

親 story #{story_number} の バックエンド 担当。既存のタスク取得 API はあるが更新 API がない。

## 現状

### 関連 Issue/PR

| 番号 | 状況 | 概要 | 補足 |
| --- | --- | --- | --- |
| - | - | 関連する Issue / PR なし | - |

### 関連ドキュメント

| 分類 | ページ | 概要 | 補足 |
| --- | --- | --- | --- |
| Wiki | `設計図/README.md` | 設計図の索引 | 新規ページ追加で更新が必要 |

## システム要件（SA）

### 機能要件

| 要件 | 補足 |
| --- | --- |
| タスクの内容を更新する API を提供する | タイトル・本文を更新 |
| 更新前に入力値を検証する | タイトルは 100 文字以内・空文字不可 |
| 検証失敗時はフィールド単位のエラー内容を返す | - |

### 非機能要件

| 要件 | 補足 |
| --- | --- |
| 更新は 1 秒以内に応答する | - |

### スコープ外

| 項目 | 理由 |
| --- | --- |
| 編集画面の実装 | フロントエンド subsystem の担当 |
| DB スキーマの変更 | 既存 tasks テーブルの既存カラムのみを更新するため不要 |
"""

SUBSYSTEM_PR_BODY_TEMPLATE = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] `設計図/バックエンド結合/タスク更新.py.md` を新規作成
- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] 実装コードを書く
- [ ] 単体テストを追加 + 実行
- [ ] 関連する結合テストを実行
"""

DESIGN_TASK_LINES = [
    "`設計図/バックエンド結合/タスク更新.py.md` を新規作成",
    "`設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成",
]
# 設計ページごとに 1 往復するため、往復回数の上限は設計タスク数 + 余裕分にする
MAX_ROUNDS = 6


def _design_paths(gh_live, owner: str, repo: str, branch: str) -> list[str]:
    """指定ブランチの `docs/wiki/設計図/` 配下のファイルパス一覧を返す。"""
    sha = gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=branch).parsed_data.commit.sha
    tree = gh_live.rest.git.get_tree(owner=owner, repo=repo, tree_sha=sha, recursive="1").parsed_data
    return [entry.path for entry in tree.tree if entry.path.startswith("docs/wiki/設計図/")]


def _add_worktree(local_path: str, branch: str) -> None:
    """subsystem ブランチの worktree を作る（subsystem-conductor の完了処理の再現）。"""
    worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", local_path, "fetch", "origin"], capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "-C", local_path, "worktree", "add", str(worktree_path), branch],
        capture_output=True, text=True, check=True,
    )


def test_normal_no_er(
    monitor,
    gh_live,
    repo_ctx,
    sandbox,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    subsystem_issue_factory,
    commit_file,
    wait_until,
):
    """設計ページの提案 → 確定の繰り返し → tester への引き渡しを実環境で確認する（正常系・タスク一覧に ER図 なし）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: epic Issue + epic Draft PR（確認ラベルなし）
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    # 準備: 要件確定済みの story Issue と story Draft PR（base=epic ブランチ）+ 単一 UC シナリオ
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number), labels=["layer:story"],
    )
    story_branch = f"feat/story/task-edit-{story.number}"
    draft_pr_factory(
        story_branch, STORY_TITLE, f"## 紐づく Issue\n\n- #{story.number}\n", base_branch=epic_branch
    )
    commit_file(story_branch, SCENARIO_PATH, SCENARIO_MD, "docs: 単一UC シナリオ（タスク編集）を追加")
    # 準備: SA 確定済みの subsystem Issue（確認ラベルなし = ボールは PR 側）
    subsystem = subsystem_issue_factory(
        story.number, SUBSYSTEM_TITLE,
        body=SUBSYSTEM_BODY_TEMPLATE.format(story_number=story.number),
        labels=["layer:subsystem", "scope:backend"],
    )
    # 準備: タスク一覧承認済みの subsystem Draft PR（base=story ブランチ）+ worktree + 確認:architect
    subsystem_branch = f"feat/backend/task-edit-{subsystem.number}/update-api"
    pr = draft_pr_factory(
        subsystem_branch, SUBSYSTEM_TITLE,
        SUBSYSTEM_PR_BODY_TEMPLATE.format(subsystem_number=subsystem.number),
        base_branch=story_branch,
    )
    _add_worktree(sandbox["local_path"], subsystem_branch)
    gh_live.rest.issues.add_labels(owner=owner, repo=repo, issue_number=pr.number, labels=["確認:architect"])

    # 実行: 設計ページごとの「提案 → 待機 → ユーザー承認」を tester へ引き渡されるまで繰り返す
    def _gate_or_handoff():
        pr_now = _get(pr.number)
        labels = {label.name for label in pr_now.labels}
        # 全ページ確定済みなら tester へ引き渡されている
        if "確認:tester" in labels:
            return ("handoff", pr_now)
        # 設計ページの提案待機（議論中 + assignee）なら承認して次のページへ進める
        return ("gate", pr_now) if "議論中" in labels and pr_now.assignees else None

    rounds = 0
    for _ in range(MAX_ROUNDS):
        kind, pr_now = wait_until(
            _gate_or_handoff, timeout_sec=1800, message="設計ページの提案待機 または tester への引き渡し"
        )
        if kind == "handoff":
            break
        rounds += 1
        # 検証: 待機のたびに設計提案コメントが積まれ、設計 Wiki が commit されている
        comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
        assert any(c.body.lstrip().startswith("> from: @architect") for c in comments), (
            f"{rounds} 回目の待機に architect の提案コメントがない"
        )
        assert _design_paths(gh_live, owner, repo, subsystem_branch), (
            f"{rounds} 回目の待機までに設計 Wiki が commit されていない"
        )
        # 実行: ユーザー承認（議論中 除去 + assignee 外し）
        try:
            gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
        except RequestFailed:
            pass
        for assignee in pr_now.assignees:
            gh_live.rest.issues.remove_assignees(
                owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
            )
    else:
        raise AssertionError(f"{MAX_ROUNDS} 往復しても tester へ引き渡されなかった")

    assert rounds >= len(DESIGN_TASK_LINES), (
        f"設計ページごとの確認ゲートが開いた回数が足りない: {rounds} 回（設計タスクは {len(DESIGN_TASK_LINES)} 件）"
    )

    # 検証: 確認:tester が付与され、確認:architect が除去されている
    pr_final = _get(pr.number)
    labels = {label.name for label in pr_final.labels}
    assert "確認:tester" in labels, f"確認:tester が付与されていない: {sorted(labels)}"
    assert "確認:architect" not in labels, "確認:architect が除去されていない"

    # 検証: タスク一覧の設計タスクがチェック済みで、実装・テストのタスクは未チェックのまま
    pr_body = (pr_final.body or "").replace("\r\n", "\n")
    for task in DESIGN_TASK_LINES:
        assert f"- [x] {task}" in pr_body, f"設計タスクがチェックされていない: {task}"
    assert "- [ ] 実装コードを書く" in pr_body, "実装タスクが先にチェックされている"

    # 検証: 担当分の設計 Wiki が subsystem ブランチに commit され、ER図 は作られていない
    paths = _design_paths(gh_live, owner, repo, subsystem_branch)
    assert any(p.startswith("docs/wiki/設計図/バックエンド結合/") for p in paths), f"バックエンド結合が未作成: {paths}"
    assert any(p.startswith("docs/wiki/設計図/モジュール構成/") for p in paths), f"モジュール構成が未作成: {paths}"
    assert not [p for p in paths if p.startswith("docs/wiki/設計図/ER図/")], (
        f"タスク一覧にない ER図 が作成されている: {paths}"
    )

    # 検証: ユーザー宛の設計提案コメントは Resolve 済み・tester 宛の割り当てコメントは未 Resolve（受領は tester の担当）
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    agent_comments = [c for c in comments if c.body.lstrip().startswith("> from: @architect")]
    assert agent_comments, "architect のコメントが見つからない"
    handoffs = [c for c in agent_comments if "> to: @tester" in c.body]
    proposals = [c for c in agent_comments if "> to: @tester" not in c.body]
    assert len(proposals) >= len(DESIGN_TASK_LINES), f"設計提案コメントが足りない: {len(proposals)} 件"
    for comment in proposals:
        assert server._is_minimized(comment.node_id), f"設計提案コメント {comment.html_url} が未 Resolve"
    assert len(handoffs) == 1, f"tester への割り当てコメントが 1 件でない: {len(handoffs)} 件"
    assert not server._is_minimized(handoffs[0].node_id), (
        f"tester への割り当てコメント {handoffs[0].html_url} が Resolve されている（受領は tester が行う）"
    )

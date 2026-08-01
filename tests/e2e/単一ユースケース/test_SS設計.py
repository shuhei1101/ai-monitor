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

- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] 実装コードを書く
- [ ] 単体テストを追加 + 実行
- [ ] 関連する結合テストを実行
"""

DESIGN_TASK_LINES = [
    "`設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成",
    "`設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成",
]
# 全ページをまとめて 1 回確認する運用なので、往復は 1 回で終わるのが期待値（余裕を持たせて上限を置く）
MAX_ROUNDS = 3


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


def test_normal_when_no_er(
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

    assert rounds == 1, (
        f"確認ゲートが 1 回にまとまっていない: {rounds} 回（設計タスクは {len(DESIGN_TASK_LINES)} 件）"
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
    assert any(p.startswith("docs/wiki/設計図/インターフェース定義/バックエンド/") for p in paths), f"インターフェース定義（バックエンド）が未作成: {paths}"
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


# ER図 の作成タスクを含むタスク一覧（正常シナリオ）
PR_BODY_WITH_ER = SUBSYSTEM_PR_BODY_TEMPLATE.replace(
    "- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成",
    "- [ ] `設計図/ER図/タスク.md` を新規作成\n"
    "- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成",
)
DESIGN_TASK_LINES_WITH_ER = ["`設計図/ER図/タスク.md` を新規作成", *DESIGN_TASK_LINES]

# 設計タスクを持たない修正用 PR（バグ差し戻しを受けた subsystem-conductor が作るもの）
PR_BODY_NO_DESIGN = SUBSYSTEM_PR_BODY_TEMPLATE.replace(
    "- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成\n"
    "- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成\n",
    "",
)

# base（story ブランチ）にある現状のモジュール構成（RE 経路の入力）
CURRENT_MODULE_PATH = "docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md"
CURRENT_MODULE_MD = """# モジュール構成: バックエンド / タスク

現状の実装から起こしたモジュール構成。

## 一覧

| ユースケース | 役割 | コンテナ | 種別 | 名前 | 概要 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| タスク編集 | サービス | `src/tasks/service.py` | 関数 | `update_task` | タスクのタイトルと本文を更新する | 検証は呼び出し側に散っている |
"""

BOUNCE_REPORT = """> from: @tester
> to: @architect

設計 Wiki どおりにテストを書けない箇所があります。

`設計図/モジュール構成/バックエンド/タスク.py.md` の `#### 単体テスト` 表に「更新履歴を検証する」ケースがありますが、
プロパティ表にも処理ステップにも更新履歴に相当する定義がありません。
設計の見直しをお願いします。

---
"""


def _setup_ss_design(
    gh_live, owner, repo, sandbox, factories, commit_file,
    *, pr_body: str, re_route: bool = False, base_designs: dict[str, str] | None = None,
):
    """タスク一覧承認済みの subsystem Draft PR（確認:architect 付き）まで用意する。"""
    layer_type = "type:docs" if re_route else "type:feat"
    re_label = ["リバースエンジニアリング"] if re_route else []
    intake, epic = factories["epic_issue_factory"](
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY,
        epic_labels=["layer:epic", layer_type, *re_label],
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    factories["epic_pr_factory"](
        branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n"
    )
    story = factories["story_issue_factory"](
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number),
        labels=["layer:story", layer_type, *re_label],
    )
    story_branch = f"feat/story/task-edit-{story.number}"
    factories["draft_pr_factory"](
        story_branch, STORY_TITLE, f"## 紐づく Issue\n\n- #{story.number}\n", base_branch=epic_branch
    )
    commit_file(story_branch, SCENARIO_PATH, SCENARIO_MD, "docs: 単一UC シナリオ（タスク編集）を追加")
    for path, content in (base_designs or {}).items():
        commit_file(story_branch, path, content, f"docs: 現状の設計書 {path} を追加")
    subsystem = factories["subsystem_issue_factory"](
        story.number, SUBSYSTEM_TITLE,
        body=SUBSYSTEM_BODY_TEMPLATE.format(story_number=story.number),
        labels=["layer:subsystem", layer_type, "scope:backend", *re_label],
    )
    subsystem_branch = f"feat/backend/task-edit-{subsystem.number}/update-api"
    pr = factories["draft_pr_factory"](
        subsystem_branch, SUBSYSTEM_TITLE,
        pr_body.format(subsystem_number=subsystem.number), base_branch=story_branch,
    )
    _add_worktree(sandbox["local_path"], subsystem_branch)
    seed = gh_live.rest.repos.get_branch(
        owner=owner, repo=repo, branch=subsystem_branch
    ).parsed_data.commit.sha
    return {
        "intake": intake, "epic": epic, "story": story, "subsystem": subsystem, "pr": pr,
        "subsystem_branch": subsystem_branch, "story_branch": story_branch, "seed": seed,
    }


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory):
    """セットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "subsystem_issue_factory": subsystem_issue_factory,
    }


def _drive_design(gh_live, owner, repo, pr_number, wait_until, *, max_rounds: int) -> int:
    """設計ページごとの「提案 → 承認」を tester へ引き渡されるまで繰り返し、往復回数を返す。"""

    def _gate_or_handoff():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=pr_number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:tester" in labels:
            return ("handoff", data)
        return ("gate", data) if "議論中" in labels and data.assignees else None

    rounds = 0
    for _ in range(max_rounds):
        kind, data = wait_until(
            _gate_or_handoff, timeout_sec=1800, message="設計ページの提案待機 または tester への引き渡し"
        )
        if kind == "handoff":
            return rounds
        rounds += 1
        try:
            gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr_number, name="議論中")
        except RequestFailed:
            pass
        for assignee in data.assignees:
            gh_live.rest.issues.remove_assignees(
                owner=owner, repo=repo, issue_number=pr_number, assignees=[assignee.login]
            )
    raise AssertionError(f"{max_rounds} 往復しても tester へ引き渡されなかった")


def test_normal(
    monitor, gh_live, repo_ctx, sandbox, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until,
):
    """ER図 を含む設計ページの確定と tester への引き渡しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = _setup_ss_design(
        gh_live, owner, repo, sandbox,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, pr_body=PR_BODY_WITH_ER,
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    rounds = _drive_design(gh_live, owner, repo, ctx["pr"].number, wait_until, max_rounds=MAX_ROUNDS + 2)
    assert rounds == 1, (
        f"確認ゲートが 1 回にまとまっていない: {rounds} 回（設計タスクは {len(DESIGN_TASK_LINES_WITH_ER)} 件）"
    )

    # 検証: 担当分の設計 Wiki（ER図 含む）が上流順に commit されている
    paths = _design_paths(gh_live, owner, repo, ctx["subsystem_branch"])
    assert [p for p in paths if p.startswith("docs/wiki/設計図/ER図/")], f"ER図 が未作成: {paths}"
    assert [p for p in paths if p.startswith("docs/wiki/設計図/インターフェース定義/バックエンド/")], (
        f"インターフェース定義（バックエンド）が未作成: {paths}"
    )
    assert [p for p in paths if p.startswith("docs/wiki/設計図/モジュール構成/")], f"モジュール構成が未作成: {paths}"

    # 検証: タスク一覧の設計タスクがチェック済みで、tester へ引き渡されている
    pr_final = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
    pr_body = (pr_final.body or "").replace("\r\n", "\n")
    for task in DESIGN_TASK_LINES_WITH_ER:
        assert f"- [x] {task}" in pr_body, f"設計タスクがチェックされていない: {task}"
    labels = {label.name for label in pr_final.labels}
    assert "確認:tester" in labels and "確認:architect" not in labels

    # 検証: tester への割り当てコメントに確定したページ名と commit 範囲が載っている
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["pr"].number
    ).parsed_data
    handoffs = [c for c in comments if "> to: @tester" in (c.body or "")]
    assert handoffs, "tester への割り当てコメントが投稿されていない"
    assert "設計図/" in (handoffs[-1].body or ""), "割り当てコメントに設計ページ名がない"


def test_normal_when_no_design_change(
    monitor, gh_live, repo_ctx, sandbox, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until,
):
    """設計タスク 0 件の修正用 PR で設計を作らず tester へ渡すことを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = _setup_ss_design(
        gh_live, owner, repo, sandbox,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, pr_body=PR_BODY_NO_DESIGN,
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    # 実行: tester への引き渡しを待つ（設計提案のユーザー確認ゲートは開かない想定）
    def _handoff():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        return data if "確認:tester" in labels else None

    pr_final = wait_until(_handoff, timeout_sec=1800, message="tester への引き渡し")

    # 検証: 設計 Wiki が 1 件も作られていない
    paths = _design_paths(gh_live, owner, repo, ctx["subsystem_branch"])
    seed_paths = _design_paths(gh_live, owner, repo, ctx["story_branch"])
    assert paths == seed_paths, f"設計 Wiki が追加されている: {sorted(set(paths) - set(seed_paths))}"

    # 検証: ユーザー確認を挟まずに tester へ渡っている
    labels = {label.name for label in pr_final.labels}
    assert "確認:architect" not in labels, "確認:architect が除去されていない"
    assert "議論中" not in labels, "ユーザー確認ゲートが開いている"

    # 検証: 判定一覧とテスト作成の指示が tester 宛に投稿されている
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["pr"].number
    ).parsed_data
    handoffs = [c for c in comments if "> to: @tester" in (c.body or "")]
    assert handoffs, "tester への割り当てコメントが投稿されていない"


def test_normal_when_interface_report(
    monitor, gh_live, repo_ctx, sandbox, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until,
):
    """インターフェース確定時の中間報告を実環境で確認する（正常系・インターフェース確定報告）。"""
    owner, repo = repo_ctx
    ctx = _setup_ss_design(
        gh_live, owner, repo, sandbox,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, pr_body=SUBSYSTEM_PR_BODY_TEMPLATE,
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    # 実行: インターフェース確定報告（確認:subsystem-conductor 付与）を待つ
    def _reported():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:subsystem-conductor" not in labels:
            return None
        comments = gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=ctx["pr"].number
        ).parsed_data
        reports = [c for c in comments if "> to: @subsystem-conductor" in (c.body or "")]
        return (data, reports) if reports else None

    data, reports = wait_until(
        _reported, timeout_sec=2400, message="インターフェース確定報告（確認:subsystem-conductor 付与）"
    )

    # 検証: インターフェース定義が commit され、確認:architect は保持されている（設計続行中）
    paths = _design_paths(gh_live, owner, repo, ctx["subsystem_branch"])
    assert [p for p in paths if p.startswith("docs/wiki/設計図/インターフェース定義/バックエンド/")], (
        f"インターフェース定義が commit されていない: {paths}"
    )
    assert "確認:architect" in {label.name for label in data.labels}, (
        "確認:architect が除去されている（設計は続行中）"
    )

    # 検証: 中間報告が未 Resolve のまま投稿されている
    assert not server._is_minimized(reports[-1].node_id), "インターフェース確定報告が Resolve されている"


def test_normal_when_bounced(
    monitor, gh_live, repo_ctx, sandbox, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until,
):
    """worker の差し戻しを受けた設計修正と再開指示を実環境で確認する（正常系・差し戻しからの設計修正）。"""
    owner, repo = repo_ctx
    ctx = _setup_ss_design(
        gh_live, owner, repo, sandbox,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, pr_body=SUBSYSTEM_PR_BODY_TEMPLATE,
    )
    # 準備: 設計確定済みの状態（設計 Wiki が subsystem ブランチにある）を再現する
    commit_file(
        ctx["subsystem_branch"], CURRENT_MODULE_PATH, CURRENT_MODULE_MD, "docs: モジュール構成を追加"
    )
    seed = gh_live.rest.repos.get_branch(
        owner=owner, repo=repo, branch=ctx["subsystem_branch"]
    ).parsed_data.commit.sha
    # 準備: tester の差し戻し報告 → 確認ラベル付与（起動トリガー）
    bounce = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=BOUNCE_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    # 実行: 設計修正 → tester への再開指示を待つ（途中のユーザー確認ゲートには承認で応答する）
    def _resumed():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:tester" in labels and "確認:architect" not in labels:
            return ("done", data)
        return ("gate", data) if "議論中" in labels and data.assignees else None

    for _ in range(MAX_ROUNDS):
        kind, data = wait_until(_resumed, timeout_sec=1800, message="設計修正の承認ゲート または 再開指示")
        if kind == "done":
            break
        try:
            gh_live.rest.issues.remove_label(
                owner=owner, repo=repo, issue_number=ctx["pr"].number, name="議論中"
            )
        except RequestFailed:
            pass
        for assignee in data.assignees:
            gh_live.rest.issues.remove_assignees(
                owner=owner, repo=repo, issue_number=ctx["pr"].number, assignees=[assignee.login]
            )
    else:
        raise AssertionError("設計修正から tester への再開指示に到達しなかった")

    # 検証: 設計 Wiki の修正 commit が積まれている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert [f for f in changed if f.startswith("docs/wiki/設計図/")], (
        f"設計 Wiki の修正 commit が積まれていない: {changed}"
    )

    # 検証: 差し戻し報告スレッドに再開指示が返信追記され、未解決のまま残っている
    thread = next(
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=ctx["pr"].number
        ).parsed_data if c.node_id == bounce.node_id
    )
    assert "> to: @tester" in (thread.body or ""), "再開指示が返信追記されていない"
    assert not server._is_minimized(bounce.node_id), (
        "差し戻し報告スレッドが Resolve されている（Resolve は差し戻し元 worker）"
    )


def test_normal_when_reverse(
    monitor, gh_live, repo_ctx, sandbox, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until,
):
    """現状の設計書を入力にした SS 設計を実環境で確認する（正常系・リバースエンジニアリング）。"""
    owner, repo = repo_ctx
    ctx = _setup_ss_design(
        gh_live, owner, repo, sandbox,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, pr_body=SUBSYSTEM_PR_BODY_TEMPLATE, re_route=True,
        base_designs={CURRENT_MODULE_PATH: CURRENT_MODULE_MD},
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    rounds = _drive_design(gh_live, owner, repo, ctx["pr"].number, wait_until, max_rounds=MAX_ROUNDS)
    assert rounds == 1, (
        f"確認ゲートが 1 回にまとまっていない: {rounds} 回"
    )

    # 検証: 現状の設計書を起点にした差分（あるべき姿への変更）が積まれている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{ctx['seed']}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert CURRENT_MODULE_PATH in changed, f"現状のモジュール構成が更新されていない: {changed}"

    # 検証: 実装の物理名と対応づいている（現状の設計書にある物理名が残っている）
    content = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path=CURRENT_MODULE_PATH, ref=ctx["subsystem_branch"]
    ).parsed_data
    import base64

    module_md = base64.b64decode(content.content).decode("utf-8")
    assert "update_task" in module_md, "実装の物理名が設計書に残っていない"

    # 検証: tester へ引き渡され、確認:architect が除去されている
    labels = {
        label.name for label in gh_live.rest.issues.get(
            owner=owner, repo=repo, issue_number=ctx["pr"].number
        ).parsed_data.labels
    }
    assert "確認:tester" in labels and "確認:architect" not in labels


def _addressed_review_comments(gh_live, owner, repo, pr_number, login: str) -> list:
    """ユーザー宛のインライン確認事項だけを返す。"""
    return [
        c
        for c in gh_live.rest.pulls.list_review_comments(
            owner=owner, repo=repo, pull_number=pr_number
        ).parsed_data
        if f"@{login}" in (c.body or "")
    ]


def test_normal_when_thumbs_up(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """インライン確認事項への 👍 を推奨への同意として扱うことを確認する（正常系・👍 で回答）。"""
    owner, repo = repo_ctx
    login = gh_live.rest.users.get_authenticated().parsed_data.login
    ctx = _setup_ss_design(
        gh_live, owner, repo, sandbox,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, pr_body=SUBSYSTEM_PR_BODY_TEMPLATE,
    )
    pr_number = ctx["pr"].number

    # 準備: 設計提案の待機（議論中 + assignee）まで進め、インライン確認事項が出るのを待つ
    def _gate_with_question():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=pr_number).parsed_data
        labels = {label.name for label in data.labels}
        if "議論中" not in labels or not data.assignees:
            return None
        questions = _addressed_review_comments(gh_live, owner, repo, pr_number, login)
        return (data, questions) if questions else None

    data, questions = wait_until(
        _gate_with_question, timeout_sec=1800, message="設計提案の待機とインライン確認事項の投稿"
    )
    target = questions[-1]
    question_ids_before = {c.id for c in questions}
    design_before = set(_design_paths(gh_live, owner, repo, ctx["subsystem_branch"]))

    # 実行: 本文のコメントは書かず 👍 だけを付けて assignee を外す
    gh_live.rest.reactions.create_for_pull_request_review_comment(
        owner=owner, repo=repo, comment_id=target.id, content="+1"
    )
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr_number, assignees=[assignee.login]
        )

    # 実行: スレッドへの返信と再待機（assignee 再設定）を待つ
    def _replied():
        threads = gh_live.rest.pulls.list_review_comments(
            owner=owner, repo=repo, pull_number=pr_number
        ).parsed_data
        replies = [c for c in threads if getattr(c, "in_reply_to_id", None) == target.id]
        if not replies:
            return None
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=pr_number).parsed_data
        return (data, replies) if data.assignees else None

    after, replies = wait_until(
        _replied, timeout_sec=1800, message="👍 への応答（スレッド返信 + assignee 再設定）"
    )

    # 検証: 該当スレッドに確定内容の返信が投稿されている
    assert any((r.body or "").lstrip().startswith("> from: @architect") for r in replies), (
        "スレッドに architect の返信が投稿されていない"
    )

    # 検証: 回答内容を問い直す確認事項が増えていない（👍 だけで判断できている）
    now_questions = _addressed_review_comments(gh_live, owner, repo, pr_number, login)
    added = [c for c in now_questions if c.id not in question_ids_before and c.id != target.id]
    assert not added, f"回答を問い直す確認事項が投稿されている: {[c.html_url for c in added]}"

    # 検証: 別案へ差し替えられていない（設計ページの構成が推奨のまま）
    design_after = set(_design_paths(gh_live, owner, repo, ctx["subsystem_branch"]))
    assert design_before <= design_after, f"設計ページが削除・改名されている: {design_before - design_after}"

    # 検証: 議論中 + assignee=ユーザー が残っている（確定はユーザーの 議論中 除去で行う）
    assert "議論中" in {label.name for label in after.labels}
    assert after.assignees

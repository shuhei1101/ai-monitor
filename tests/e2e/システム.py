"""system レイヤー / リバースエンジニアリング系 UC の E2E で seed する資材。

新規プロジェクトの経路は空のリポジトリを前提にするため、master には何も置かずに起動する。
既存プロジェクトの移行の経路は `実装対象.PROJECT_FILES` の最小プロジェクトを対象コードに見立て、
master にコードと現状の設計書を置いてから起動する。
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml

SYSTEM_TITLE = "タスク管理ツールの立ち上げ"

# 構成要件（リポジトリ / サブシステム / 言語 / 外部システム）に触れている入力
SYSTEM_BODY = """タスクを登録して編集・一覧できるツールを作りたい。

- リポジトリは 1 つにまとめたい（分けるほどの規模ではない）
- 画面は後回しにして、まずはバックエンドだけ作る
- 言語は Python
- 外部サービスとの連携は今のところ不要
"""

# 技術構成に一切触れていない入力（不足の洗い出しを決定的に誘発する）
SYSTEM_BODY_MINIMAL = """タスクを登録して編集・一覧できるツールが欲しい。

- 個人で使う想定
- 今は紙とメモアプリに散らばっていて、どれが未着手か分からなくなる
"""

MIGRATION_TITLE = "既存のタスク管理コードの移行"
SYSTEM_BODY_MIGRATION = """すでに動いているタスク管理のコードを ai-monitor のワークフローに載せたい。

- 実装は `src/tasks/` にある
- 設計書が無いので、現状を起こしたうえで整理したい
"""

ARCHITECTURE_PATH = "docs/wiki/設計図/アーキテクチャ図.md"
ARCHITECTURE_MD = """---
template_version: 1.1.0
---

# アーキテクチャ図

## システム全体図

```mermaid
flowchart LR
  U([ユーザー])

  subgraph SYS["タスク管理"]
    BE[バックエンド]
    STORE[(インメモリストア)]
  end

  U --> BE
  BE --> STORE
```

## リポジトリ構成

| 項目 | 内容 | 補足 |
| --- | --- | --- |
| 方式 | モノレポ | サブシステムをトップレベルディレクトリで分ける |
| 配置 | `src/tasks/` | `docs/wiki/` は共通 |

## サブシステム一覧

| サブシステム | scope | 役割 | 言語・ランタイム | 補足 |
| --- | --- | --- | --- | --- |
| バックエンド | `scope:backend` | タスクの取得・更新・一覧 | Python 3.12 | 画面は未実装 |

## 外部システム連携

なし
"""

# architecture-reverse-engineer が現状のアーキテクチャ図を起こしたときの完了報告
ARCHITECTURE_RE_REPORT = """> from: @architecture-reverse-engineer
> to: @system-conductor

現状のアーキテクチャ図を起こしました。

- 作成したページ: `docs/wiki/設計図/アーキテクチャ図.md`
- サブシステム: バックエンド（`src/tasks/`）のみ
- 外部システム連携: なし

洗い出した機能:

| 機能 | 実体 | 補足 |
| --- | --- | --- |
| タスク取得 | `get_task` | ID 指定で 1 件返す |
| タスク更新 | `update_task` | タイトルと本文を差し替える |
| タスク一覧 | `list_tasks` | ID 順で返す |

実装から読み取れなかった箇所: 永続化層（現状はインメモリの dict のみで、保存先の想定が読み取れない）

------
"""

# 要件セクションだけを取り出したもの（system PR 本文の組み立てに使う）
SYSTEM_REQUIREMENTS = """## 概要

タスクを登録して編集・一覧できる個人向けのタスク管理ツール。

## 背景

紙とメモアプリにタスクが散らばっていて、未着手のものを見失う。

## 構成要件

| カテゴリ | 決定内容 | 根拠 | 補足 |
| --- | --- | --- | --- |
| リポジトリ | 単一リポジトリにまとめる | サブシステムが 1 つで分ける利点がない | - |
| サブシステム | バックエンドのみ | 画面は次フェーズ | - |
| 言語 | Python 3.12 | 標準ライブラリだけで完結する | - |
| 外部システム | なし | 外部サービスへの依存を作らない | - |

## エピック一覧

| エピック | 概要 | 所属ユースケース | 着手順 | 対応 PR | 補足 |
| --- | --- | --- | --- | --- | --- |
| タスク編集機能 | 登録済みタスクのタイトルと本文を編集する | タスク編集 | 1 | 未作成 | - |
| タスク一覧機能 | 登録済みタスクを一覧で確認する | タスク一覧 | 2 | 未作成 | タスク編集機能の完了後 |
"""

SYSTEM_TASKS = """## タスク一覧

- [ ] `docs/wiki/` の骨格と `docs/rules.yaml` を生成
- [ ] `設計図/アーキテクチャ図.md` を作成
- [ ] `設計図/非機能要件.md` を作成
- [ ] `README.md` を作成
- [ ] `.gitignore` を作成
- [ ] `.claude/settings.json` にルール索引を宣言
- [ ] GitHub ラベルを一括作成
"""

SYSTEM_PR_BODY = """## 紐づく Issue

- #{system_number}

""" + SYSTEM_TASKS

# 要件まで確定済みの system PR 本文（土台生成 / 子epicPR作成 の起点）
# 面が Issue から PR へ移ったため、要件の置き場所は立ち上げ Issue ではなく PR 本文になる
SYSTEM_PR_BODY_CONFIRMED = """## 紐づく Issue

- #{system_number}

""" + SYSTEM_REQUIREMENTS + "\n" + SYSTEM_TASKS

# 土台生成が終わってタスク一覧を消化済みの system PR 本文（system マージ の起点）
SYSTEM_PR_BODY_DONE = SYSTEM_PR_BODY_CONFIRMED.replace("- [ ]", "- [x]")

# system-architect が生成済みの土台（system マージ の seed）
FOUNDATION_FILES = {
    "README.md": "# タスク管理ツール\n\nタスクを登録して編集・一覧できる個人向けのツール。\n",
    "docs/rules.yaml": "# inject-rules ルール索引\nrules: []\n",
    "docs/wiki/README.md": (
        "# Wiki\n\n## 目次\n\n| ページ | 概要 |\n| --- | --- |\n"
        "| [設計図](./設計図/) | プロジェクト固有の設計図 |\n"
    ),
    ARCHITECTURE_PATH: ARCHITECTURE_MD,
}


# system-conductor が system-architect へ土台生成を依頼するコメント
BUILD_REQUEST = """> from: @system-conductor
> to: @system-architect

構成要件が確定しました。土台の生成をお願いします。

- 紐づく system Issue: #{system_number}
- 構成要件は Issue 本文の `## 構成要件` を参照してください

------
"""

# system-architect が土台生成を終えたときの完了報告
BUILD_DONE_REPORT = """> from: @system-architect
> to: @{login}

土台を生成しました。ご確認ください。

| 生成物 | 内容 |
| --- | --- |
| `docs/wiki/` 骨格 | 全ディレクトリに README を併置 |
| `設計図/アーキテクチャ図.md` | 構成要件どおりのサブシステム 1 つ |
| `設計図/非機能要件.md` | 一覧と詳細セクション |
| `docs/rules.yaml` | 空の索引 |
| GitHub ラベル | 全ラベルを作成 |

- 問題なければ `議論中` ラベルを外して assignee を外してください

------
"""

# conductor が reverse-engineer へ現状の起こしを依頼するコメント
RE_REQUEST = """> from: @{sender}
> to: @{receiver}

現状の設計書を起こしてください。

- 対象: `src/tasks/`
- 成果物は本 PR に commit してください

------
"""

# reverse-engineer が現状を起こし終えたときの完了報告
RE_DONE_REPORT = """> from: @{sender}
> to: @{receiver}

現状の設計書を起こしました。

| ページ | 内容 |
| --- | --- |
| `設計図/モジュール構成/バックエンド/タスク.py.md` | `get_task` / `update_task` / `list_tasks` |

実装から読み取れなかった箇所: 永続化層（インメモリの dict のみ）

| commit | 内容 |
| --- | --- |
| seed | 現状のモジュール構成を追加 |

------
"""


def setup_re_target(
    gh_live, owner, repo,
    epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file,
    *, subsystem_labels: list[str],
):
    """RE 起動の対象になる subsystem Issue までを用意する（通常 PR は作らない）。

    RE は要件確定より前の工程なので、subsystem PR がまだ無い状態から始める。
    起こす対象の実装コードは story ブランチへ置く（RE ブランチはそこから生える）。
    """
    from tests.e2e.実装対象 import (
        EPIC_BODY,
        EPIC_TITLE,
        INTAKE_BODY,
        INTAKE_TITLE,
        PROJECT_FILES,
        SCENARIO_MD,
        SCENARIO_PATH,
        STORY_BODY_TEMPLATE,
        STORY_TITLE,
        SUBSYSTEM_TITLE,
    )

    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY,
        epic_labels=["layer:epic", "type:docs", "リバースエンジニアリング"],
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}/base"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number),
        labels=["layer:story", "type:docs", "リバースエンジニアリング"],
    )
    story_branch = f"feat/story/task-edit-{story.number}/base"
    draft_pr_factory(
        story_branch, STORY_TITLE, f"## 紐づく Issue\n\n- #{story.number}\n", base_branch=epic_branch
    )
    commit_file(story_branch, SCENARIO_PATH, SCENARIO_MD, "docs: 単一UC シナリオ（タスク編集）を追加")
    # RE が読む現状の実装コードを置く
    for path, content in PROJECT_FILES.items():
        commit_file(story_branch, path, content, f"chore: e2e 用に {path} を配置")
    subsystem = subsystem_issue_factory(story.number, SUBSYSTEM_TITLE, labels=subsystem_labels)
    return {
        "intake": intake,
        "epic": epic,
        "epic_branch": epic_branch,
        "story": story,
        "story_branch": story_branch,
        "subsystem": subsystem,
    }


def _merge_when_ready(gh_live, owner, repo, pr_number: int, *, attempts: int = 20) -> None:
    """マージ可能になるのを待ってから squash マージする。

    GitHub は PR のマージ可能性を非同期で計算するため、作成 / push の直後は
    `mergeable` が null のままで `merge` が 405 を返す。
    """
    for _ in range(attempts):
        data = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr_number).parsed_data
        if data.mergeable:
            gh_live.rest.pulls.merge(
                owner=owner, repo=repo, pull_number=pr_number, merge_method="squash"
            )
            # マージ済み PR は後片付けの「open PR から辿る」対象に入らないのでここで消す
            gh_live.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{data.head.ref}")
            return
        time.sleep(3)
    raise AssertionError(f"PR #{pr_number} がマージ可能にならなかった（mergeable が null のまま）")


def setup_system_with_foundation(
    gh_live, owner, repo, system_issue_factory, layer_pr_factory, commit_file,
    *, pr_labels: list[str], re_route: bool = False,
):
    """立ち上げ Issue + 要件確定済みの system PR + マージ済みの土台生成成果物 PR を用意する。

    子epicPR作成 の起動条件が「土台生成の成果物 PR が merged」なので、
    成果物ブランチを切って squash マージするところまで再現する。
    """
    issue_labels = ["layer:system", "type:docs" if re_route else "type:feat"]
    if re_route:
        issue_labels.append("リバースエンジニアリング")
    system = system_issue_factory(SYSTEM_TITLE, SYSTEM_BODY, labels=issue_labels)
    branch = system_branch(system.number)
    system_pr = layer_pr_factory(
        branch, SYSTEM_TITLE, SYSTEM_PR_BODY_CONFIRMED.format(system_number=system.number),
        labels=pr_labels,
    )
    # 土台生成の成果物 PR（base=system ブランチ）を作り、成果物を積んでからマージする
    artifact_branch = foundation_branch(system.number)
    # マージまで再現するので Draft では作らない（Draft PR のマージは 405 になる）
    artifact_pr = layer_pr_factory(
        artifact_branch, "土台生成", f"## 紐づく Issue\n\n- #{system.number}\n",
        base_branch=branch, draft=False,
    )
    for path, content in FOUNDATION_FILES.items():
        commit_file(artifact_branch, path, content, f"docs: e2e 用に {path} を配置")
    _merge_when_ready(gh_live, owner, repo, artifact_pr.number)
    return {
        "system": system,
        "system_pr": system_pr,
        "branch": branch,
        "artifact_pr": artifact_pr,
    }


def session_entry(state_path: Path, agent_name: str, primary_number: int) -> dict | None:
    """モニター台帳から指定エージェント × 主番号のセッション 1 件を返す。"""
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        if entry["agent_name"] == agent_name and entry["primary_number"] == primary_number:
            return entry
    return None


def watch_numbers(state_path: Path, agent_name: str, primary_number: int) -> list[int]:
    """モニター台帳から指定セッションの監視面番号一覧を返す。"""
    entry = session_entry(state_path, agent_name, primary_number)
    return entry["watch_numbers"] if entry else []


def re_branch(number: int) -> str:
    """RE PR のブランチ名を返す。"""
    return f"docs/reverse/task-{number}"


def system_branch(number: int) -> str:
    """system PR のブランチ名（レイヤーブランチ）を返す。"""
    return f"docs/system/task-{number}/base"


def foundation_branch(number: int) -> str:
    """土台生成の成果物ブランチ名を返す。

    レイヤーブランチと兄弟にする（`.../base` の配下に置くと git の ref 名前空間で衝突する）。
    """
    return f"docs/system/task-{number}/foundation"

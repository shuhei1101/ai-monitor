"""統合テスト系 UC の E2E で story ブランチ / story PR へ seed する資材。

全 subsystem がマージ済みの story ブランチを再現する。
画面は無いので、単一 UC シナリオの E2E はサービス層を通した一連の操作として検証する。
"""
from __future__ import annotations

from tests.e2e.実装対象 import ERRORS_PY, MODELS_PY, SCENARIO_MD, SCENARIO_PATH

# 実装済み（全 subsystem マージ後）のサービス層
SERVICE_PY = '''"""タスクのドメインロジック。"""
from __future__ import annotations

from tasks.errors import TaskNotFoundError, ValidationError
from tasks.models import Task


def get_task(store: dict[str, Task], task_id: str) -> Task:
    """ストアからタスクを 1 件取得する。"""
    # 未登録の ID は例外にする
    if task_id not in store:
        raise TaskNotFoundError(f"task not found: {task_id}")
    return store[task_id]


def update_task(store: dict[str, Task], task_id: str, title: str, content: str = "") -> Task:
    """登録済みタスクのタイトルと本文を更新して返す。"""
    # タイトルを検証する
    if not (1 <= len(title) <= 100):
        raise ValidationError("title は 1 文字以上 100 文字以内")
    # 本文を検証する
    if len(content) > 1000:
        raise ValidationError("content は 1000 文字以内")
    # 対象タスクを取得する
    task = get_task(store, task_id)
    # 差し替えたタスクを書き戻して返す
    updated = Task(id=task.id, title=title, content=content)
    store[task_id] = updated
    return updated


def list_tasks(store: dict[str, Task]) -> list[Task]:
    """ストアのタスクを ID 順で一覧にする。"""
    return [store[key] for key in sorted(store)]
'''

# タイトルの空文字を素通しするバグ（異常シナリオの E2E だけが落ちる）
BUGGY_SERVICE_PY = SERVICE_PY.replace(
    "    if not (1 <= len(title) <= 100):",
    "    if len(title) > 100:",
)

TEST_HOWTO_MD = """# テスト実行方法

sandbox プロジェクトのテスト実行コマンドと前提条件。

## 前提

- Python 3.12 以上（標準ライブラリのみ。外部パッケージのインストールは不要）
- テストは `unittest` で書く

## E2E テスト

`unittest` で実行。

**前提:**

- 画面は未実装のため、単一ユースケースシナリオの検証はサービス層（`src/tasks/service.py`）を通した一連の操作で行う
- テストは `tests/e2e/単一ユースケース/test_{機能名}.py` に置き、シナリオの H2 見出しと 1 テスト関数を機械対応させる
- 対象は `設計図/シナリオ/単一ユースケース/**` と 1:1

**全件実行:**

```bash
python3 -m unittest discover -s tests/e2e -t .
```

**個別シナリオ実行:**

```bash
python3 -m unittest {シナリオテストのモジュールパス}
```

## 単体テスト（バック）

`unittest` で実行。

**前提:**

- 外部依存なし（純粋関数のみ）
- 対象は `設計図/モジュール構成/**` の単体テスト表と 1:1

**全件実行:**

```bash
python3 -m unittest discover -s tests/unit -t .
```

**個別ファイル実行:**

```bash
python3 -m unittest {単体テストのモジュールパス}
```

## 結合テスト（バック）

なし

## 単体テスト（フロント）

なし

## 結合テスト（フロント）

なし
"""

UNIT_TEST_PATH = "tests/unit/tasks/test_service.py"
UNIT_TEST_PY = '''"""`src/tasks/service.py` の単体テスト。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from tasks.errors import ValidationError  # noqa: E402
from tasks.models import Task  # noqa: E402
from tasks.service import update_task  # noqa: E402


class UpdateTaskTest(unittest.TestCase):
    def test_update_task(self):
        """タイトルと本文を更新する（正常系）。"""
        store = {"t1": Task(id="t1", title="旧タイトル", content="旧本文")}
        result = update_task(store, "t1", "新タイトル", "新本文")
        self.assertEqual(result.title, "新タイトル")

    def test_update_task_when_title_empty(self):
        """タイトルが空なら ValidationError（異常系）。"""
        store = {"t1": Task(id="t1", title="旧タイトル", content="旧本文")}
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "")


if __name__ == "__main__":
    unittest.main()
'''

E2E_TEST_PATH = "tests/e2e/単一ユースケース/test_タスク編集.py"
_E2E_HEADER = '''"""単一UC「タスク編集」の E2E テスト。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from tasks.errors import ValidationError  # noqa: E402
from tasks.models import Task  # noqa: E402
from tasks.service import update_task  # noqa: E402


def _store() -> dict[str, Task]:
    return {"t1": Task(id="t1", title="旧タイトル", content="旧本文")}


class タスク編集Test(unittest.TestCase):
    def test_normal(self):
        """一覧から選んだタスクを編集して保存する（正常系）。"""
        store = _store()
        update_task(store, "t1", "新タイトル", "新本文")
        self.assertEqual(store["t1"].title, "新タイトル")
        self.assertEqual(store["t1"].content, "新本文")
'''

_E2E_ERROR_CASE = '''
    def test_error_when_タイトルが空(self):
        """タイトルを空にして保存するとエラーになり保存されない（異常系）。"""
        store = _store()
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "")
        self.assertEqual(store["t1"].title, "旧タイトル")
'''

_E2E_FOOTER = '''

if __name__ == "__main__":
    unittest.main()
'''

# シナリオの正常 / 異常を両方カバーした E2E テスト
E2E_TEST_PY = _E2E_HEADER + _E2E_ERROR_CASE + _E2E_FOOTER

# 異常シナリオのケースが欠落した E2E テスト（統合テストレビューの指摘を誘発）
E2E_TEST_PY_MISSING_ERROR_CASE = _E2E_HEADER + _E2E_FOOTER

STORY_PR_BODY = """## 紐づく Issue

- #{story_number}

## タスク一覧

- [x] `設計図/シナリオ/単一ユースケース/タスク編集.md` を新規作成
- [x] `設計図/シナリオ/README.md` の `## 一覧` に該当行を追加
- [ ] 単一ユースケース E2E テストを実行
"""

STORY_PR_BODY_WITH_TABLE = STORY_PR_BODY + """
## 単一ユースケースシナリオテスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/e2e/単一ユースケース/test_タスク編集.py` | 全実行 | | 新規・対応シナリオ: `タスク編集` |
| `tests/unit/tasks/test_service.py` | 全実行 | | 回帰・`update_task` の変更影響 |
"""

TESTER_DONE_REPORT = """> from: @single-scenario-tester
> to: @single-scenario-writer

単一 UC「タスク編集」の E2E テスト実装が完了しました。

- 作成したテストファイル: `tests/e2e/単一ユースケース/test_タスク編集.py`
- 対応シナリオ: `設計図/シナリオ/単一ユースケース/タスク編集.md`
- 回帰確認の対象: `tests/unit/tasks/test_service.py`（`update_task` の変更影響）

| commit | 内容 |
| --- | --- |
| seed | 単一UC の E2E テストを追加 |
"""

RUN_INSTRUCTION = """> from: @single-scenario-writer
> to: @single-scenario-tester

レビューが完了しました。テスト結果表の全行（新規 + 回帰）を実行して、結果列を埋めてください。
"""

SCENARIO_INDEX_PATH = "docs/wiki/設計図/シナリオ/README.md"
SCENARIO_INDEX_MD = """# シナリオ

単一ユースケース / 複合ユースケース の 2 種類を扱う。
1 ファイル = 1 テストファイルに対応する。

## 一覧

| 種別 | シナリオ / 機能名 | 概要 | リンク | 補足 |
| --- | --- | --- | --- | --- |
| 単一ユースケース | タスク編集 | 一覧から選択したタスクの内容を編集して保存する | [タスク編集](./単一ユースケース/タスク編集.md) | - |
"""


COMPLEX_SCENARIO_PATH = "docs/wiki/設計図/シナリオ/複合ユースケース/タスク編集から一覧反映.md"
COMPLEX_SCENARIO_MD = """---
template_version: 1.0.0
---

# タスク編集から一覧反映

タスクを編集して保存し、一覧に反映されるまでの業務シナリオ。

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| タスク | 編集対象のタスクを 1 件登録済み | - |

### フロー

```mermaid
flowchart TD
  U0([ユーザー]) -->|一覧から対象タスクを選ぶ| UC1([タスク編集:正常シナリオ])
  UC1 -->|保存完了・一覧へ戻る| DONE([一覧に編集後の内容が表示された状態])

  click UC1 "../単一ユースケース/タスク編集.md#正常シナリオ"
```

### 期待値

- 一覧に編集後のタイトルと本文が並んでいる

## 異常シナリオ（タイトルが空）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 入力 | タイトルを空にして保存 | 検証失敗を決定的に誘発 |

### フロー

```mermaid
flowchart TD
  U0([ユーザー]) -->|タイトルを空にして保存| UC1([タスク編集:異常シナリオ<br>（タイトルが空）])
  UC1 -->|保存されない| DONE([一覧が編集前のままの状態])

  click UC1 "../単一ユースケース/タスク編集.md#異常シナリオタイトルが空"
```

### 期待値

- 一覧が編集前の内容のまま変わっていない
"""

COMPLEX_E2E_TEST_PATH = "tests/e2e/複合ユースケース/test_タスク編集から一覧反映.py"
_COMPLEX_E2E_HEADER = '''"""複合UC「タスク編集から一覧反映」の E2E テスト。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from tasks.errors import ValidationError  # noqa: E402
from tasks.models import Task  # noqa: E402
from tasks.service import list_tasks, update_task  # noqa: E402


def _store() -> dict[str, Task]:
    return {"t1": Task(id="t1", title="旧タイトル", content="旧本文")}


class タスク編集から一覧反映Test(unittest.TestCase):
    def test_normal(self):
        """編集して保存すると一覧に反映される（正常系）。"""
        store = _store()
        update_task(store, "t1", "新タイトル", "新本文")
        listed = list_tasks(store)
        self.assertEqual(listed[0].title, "新タイトル")
        self.assertEqual(listed[0].content, "新本文")
'''

_COMPLEX_E2E_ERROR_CASE = '''
    def test_error_when_タイトルが空(self):
        """タイトルを空にして保存すると一覧が変わらない（異常系）。"""
        store = _store()
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "")
        listed = list_tasks(store)
        self.assertEqual(listed[0].title, "旧タイトル")
'''

COMPLEX_E2E_TEST_PY = _COMPLEX_E2E_HEADER + _COMPLEX_E2E_ERROR_CASE + _E2E_FOOTER
COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE = _COMPLEX_E2E_HEADER + _E2E_FOOTER

EPIC_PR_BODY = """## 紐づく Issue

- #{epic_number}

## タスク一覧

- [x] `設計図/シナリオ/複合ユースケース/タスク編集から一覧反映.md` を新規作成
- [x] `設計図/シナリオ/README.md` の `## 一覧` に該当行を追加
- [ ] 複合ユースケース E2E テストを実行
"""

EPIC_PR_BODY_WITH_TABLE = EPIC_PR_BODY + """
## 複合ユースケースシナリオテスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/e2e/複合ユースケース/test_タスク編集から一覧反映.py` | 全実行 | | 新規・対応シナリオ: `タスク編集から一覧反映` |
| `tests/e2e/単一ユースケース/test_タスク編集.py` | 全実行 | | 回帰・単一 UC の再確認 |
"""

COMPLEX_TESTER_DONE_REPORT = """> from: @complex-scenario-tester
> to: @complex-scenario-writer

複合 UC「タスク編集から一覧反映」の E2E テスト実装が完了しました。

- 作成したテストファイル: `tests/e2e/複合ユースケース/test_タスク編集から一覧反映.py`
- 対応シナリオ: `設計図/シナリオ/複合ユースケース/タスク編集から一覧反映.md`
- 回帰確認の対象: `tests/e2e/単一ユースケース/test_タスク編集.py`

| commit | 内容 |
| --- | --- |
| seed | 複合UC の E2E テストを追加 |
"""

COMPLEX_RUN_INSTRUCTION = """> from: @complex-scenario-writer
> to: @complex-scenario-tester

レビューが完了しました。テスト結果表の全行（新規 + 回帰）を実行して、結果列を埋めてください。
"""


def story_branch_files(*, service: str = SERVICE_PY, e2e_test: str | None = None) -> dict[str, str]:
    """全 subsystem マージ後の story ブランチに置くファイル一式を返す。"""
    files = {
        ".gitignore": "__pycache__/\n*.pyc\n",
        "src/tasks/__init__.py": "",
        "src/tasks/models.py": MODELS_PY,
        "src/tasks/errors.py": ERRORS_PY,
        "src/tasks/service.py": service,
        "tests/__init__.py": "",
        "tests/unit/__init__.py": "",
        "tests/unit/tasks/__init__.py": "",
        UNIT_TEST_PATH: UNIT_TEST_PY,
        "docs/wiki/テスト/テスト実行方法.md": TEST_HOWTO_MD,
        SCENARIO_PATH: SCENARIO_MD,
        SCENARIO_INDEX_PATH: SCENARIO_INDEX_MD,
    }
    if e2e_test is not None:
        files["tests/e2e/__init__.py"] = ""
        files["tests/e2e/単一ユースケース/__init__.py"] = ""
        files[E2E_TEST_PATH] = e2e_test
    return files


def setup_story(
    gh_live, owner, repo,
    epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file,
    *, pr_body: str, files: dict[str, str],
):
    """全 subsystem マージ済みの story（Issue + PR + ブランチ）を用意する。"""
    from tests.e2e.実装対象 import (
        EPIC_BODY,
        EPIC_TITLE,
        INTAKE_BODY,
        INTAKE_TITLE,
        STORY_BODY_TEMPLATE,
        STORY_TITLE,
    )

    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number), labels=["layer:story", "type:feat"],
    )
    story_branch = f"feat/story/task-edit-{story.number}"
    pr = draft_pr_factory(
        story_branch, STORY_TITLE, pr_body.format(story_number=story.number), base_branch=epic_branch
    )
    for path, content in files.items():
        commit_file(story_branch, path, content, f"chore: e2e 用に {path} を配置")
    return {
        "intake": intake, "epic": epic, "story": story, "pr": pr,
        "epic_branch": epic_branch, "story_branch": story_branch,
    }


def epic_branch_files(*, service: str = SERVICE_PY, complex_e2e_test: str | None = None) -> dict[str, str]:
    """全 story マージ後の epic ブランチに置くファイル一式を返す。

    単一 UC の E2E は回帰確認の対象として既に存在している状態にする。
    """
    files = story_branch_files(service=service, e2e_test=E2E_TEST_PY)
    files[COMPLEX_SCENARIO_PATH] = COMPLEX_SCENARIO_MD
    files[SCENARIO_INDEX_PATH] = SCENARIO_INDEX_MD.replace(
        "| 単一ユースケース | タスク編集 |",
        "| 複合ユースケース | タスク編集から一覧反映 | 編集して保存 → 一覧に反映 |"
        " [タスク編集から一覧反映](./複合ユースケース/タスク編集から一覧反映.md) | - |\n"
        "| 単一ユースケース | タスク編集 |",
    )
    if complex_e2e_test is not None:
        files["tests/e2e/複合ユースケース/__init__.py"] = ""
        files[COMPLEX_E2E_TEST_PATH] = complex_e2e_test
    return files


def setup_epic(
    gh_live, owner, repo, epic_issue_factory, epic_pr_factory, commit_file,
    *, pr_body: str, files: dict[str, str],
):
    """全 story マージ済みの epic（Issue + PR + ブランチ）を用意する。"""
    from tests.e2e.実装対象 import EPIC_BODY, EPIC_TITLE, INTAKE_BODY, INTAKE_TITLE

    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    pr = epic_pr_factory(
        branch=epic_branch, title=EPIC_TITLE, body=pr_body.format(epic_number=epic.number)
    )
    for path, content in files.items():
        commit_file(epic_branch, path, content, f"chore: e2e 用に {path} を配置")
    return {"intake": intake, "epic": epic, "pr": pr, "epic_branch": epic_branch}


def result_rows(body: str, *, section_name: str = "## 単一ユースケースシナリオテスト結果") -> list[str]:
    """テスト結果表のデータ行を返す。"""
    text = body.replace("\r\n", "\n")
    section = text.split(section_name, 1)[1]
    section = section.split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")]
    return rows[2:]


def complex_result_rows(body: str) -> list[str]:
    """`## 複合ユースケースシナリオテスト結果` の表のデータ行を返す。"""
    return result_rows(body, section_name="## 複合ユースケースシナリオテスト結果")

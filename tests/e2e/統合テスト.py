"""統合テスト系 UC の E2E で story ブランチ / story PR へ seed する資材。

全 subsystem がマージ済みの story ブランチを再現する。
画面は無いので、単一 UC シナリオの E2E はサービス層を通した一連の操作として検証する。
"""
from __future__ import annotations

from tests.e2e.実装対象 import ERRORS_PY, MODELS_PY, RED_TEST_PY, SCENARIO_MD, SCENARIO_PATH

# 実装済み（全 subsystem マージ後）のサービス層
SERVICE_PY = '''"""タスクのドメインロジック。"""
from __future__ import annotations

from tasks.errors import TaskNotFoundError, ValidationError
from tasks.models import Task

TITLE_MIN_LENGTH = 1
TITLE_MAX_LENGTH = 100
CONTENT_MAX_LENGTH = 1000


def get_task(store: dict[str, Task], task_id: str) -> Task:
    """ストアからタスクを 1 件取得する。"""
    # 未登録の ID は例外にする
    if task_id not in store:
        raise TaskNotFoundError(f"task not found: {task_id}")
    return store[task_id]


def update_task(store: dict[str, Task], task_id: str, title: str, content: str = "") -> Task:
    """登録済みタスクのタイトルと本文を更新して返す。"""
    # タイトルを検証する
    if not (TITLE_MIN_LENGTH <= len(title) <= TITLE_MAX_LENGTH):
        raise ValidationError(
            f"title は {TITLE_MIN_LENGTH} 文字以上 {TITLE_MAX_LENGTH} 文字以内"
        )
    # 本文を検証する
    if len(content) > CONTENT_MAX_LENGTH:
        raise ValidationError(f"content は {CONTENT_MAX_LENGTH} 文字以内")
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
    "    if not (TITLE_MIN_LENGTH <= len(title) <= TITLE_MAX_LENGTH):",
    "    if len(title) > TITLE_MAX_LENGTH:",
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
# 回帰対象の単体テスト（設計 Wiki の単体テスト表と同じ 6 ケース）。
# `tests/unit/tasks/` に置くのでリポジトリルートまでの階層だけ読み替える
UNIT_TEST_PY = RED_TEST_PY.replace("parents[2]", "parents[3]")

E2E_TEST_PATH = "tests/e2e/単一ユースケース/test_タスク編集.py"
_E2E_HEADER = '''"""単一UC「タスク編集」の E2E テスト。"""
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


class タスク編集Test(unittest.TestCase):
    def test_normal(self):
        """一覧から選んだタスクを編集して保存する（正常系）。"""
        # 準備
        store = _store()
        # 実行
        update_task(store, "t1", "新タイトル", "新本文")
        listed = list_tasks(store)
        # 検証
        self.assertEqual(listed[0].title, "新タイトル")
        self.assertEqual(listed[0].content, "新本文")
'''

_E2E_ERROR_CASE = '''
    def test_error_when_タイトルが空(self):
        """タイトルを空にして保存するとエラーになり保存されない（異常系）。"""
        # 準備
        store = _store()
        # 実行・検証
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "")
        self.assertEqual(list_tasks(store)[0].title, "旧タイトル")
'''

_E2E_FOOTER = '''

if __name__ == "__main__":
    unittest.main()
'''

# シナリオの正常 / 異常を両方カバーした E2E テスト
E2E_TEST_PY = _E2E_HEADER + _E2E_ERROR_CASE + _E2E_FOOTER

# 異常シナリオのケースが欠落した E2E テスト（統合テストレビューの指摘を誘発）
E2E_TEST_PY_MISSING_ERROR_CASE = _E2E_HEADER + _E2E_FOOTER

# シナリオ設計書が story のユースケース要件（タイトルは 1 文字以上）と矛盾している状態。
# 実装は要件どおりなので、この設計書から起こしたテストは必ず落ちる（シナリオ側の問題）。
SCENARIO_MD_CONFLICTING = SCENARIO_MD.replace(
    "## 異常シナリオ（タイトルが空）", "## 正常シナリオ（タイトルが空）"
).replace(
    """  U->>FE: タイトルを空にして保存
  FE->>FE: 入力バリデーション失敗
  FE-->>U: インラインエラー表示""",
    """  U->>FE: タイトルを空にして保存
  FE->>BE: タスク更新リクエスト
  BE-->>FE: 空タイトルのまま更新されたタスク
  FE-->>U: 一覧へ戻り 空タイトルで表示""",
).replace(
    "- インラインエラーが表示され、保存されていない",
    "- 一覧に空タイトルのまま保存された内容が表示されている",
).replace(
    """  actor U as ユーザー
  participant FE as タスク編集画面

  U->>FE: タイトルを空にして保存""",
    """  actor U as ユーザー
  participant FE as タスク編集画面
  participant BE as バックエンド API

  U->>FE: タイトルを空にして保存""",
)

# 上の矛盾したシナリオに忠実に起こした E2E テスト（実装が要件どおりなので落ちる）
E2E_TEST_PY_FOLLOWING_CONFLICT = _E2E_HEADER + '''
    def test_normal_when_タイトルが空(self):
        """タイトルを空にして保存すると空タイトルのまま保存される（正常系）。"""
        # 準備
        store = _store()
        # 実行
        update_task(store, "t1", "")
        # 検証
        self.assertEqual(list_tasks(store)[0].title, "")
''' + _E2E_FOOTER

# テストコード側の誤り（正常系の期待値を取り違えている）。シナリオ・実装とも正しい
E2E_TEST_PY_WRONG_ASSERTION = _E2E_HEADER.replace(
    'self.assertEqual(listed[0].content, "新本文")',
    'self.assertEqual(listed[0].content, "旧本文")',
    1,
) + _E2E_ERROR_CASE + _E2E_FOOTER

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

_SINGLE_NEW_ROW = "| `tests/e2e/単一ユースケース/test_タスク編集.py` | 全実行 | | 新規・対応シナリオ: `タスク編集` |"
_SINGLE_FAILED_ROW = (
    "| `tests/e2e/単一ユースケース/test_タスク編集.py` | 全実行 | ❌ | 新規・対応シナリオ: `タスク編集`。"
    "`test_error_when_タイトルが空` が失敗（`ValidationError` が送出されず保存される） |"
)

# 全行 pass を記入済みの story PR 本文（全 pass の完了報告 の起点）
STORY_PR_BODY_ALL_PASSED = STORY_PR_BODY_WITH_TABLE.replace("| 全実行 | |", "| 全実行 | ✅ |")

# fail を記録済みの story PR 本文（再テストの実行指示 の起点）
STORY_PR_BODY_FAILED = STORY_PR_BODY_WITH_TABLE.replace(
    _SINGLE_NEW_ROW, _SINGLE_FAILED_ROW
).replace("| 全実行 | |", "| 全実行 | ✅ |")

TESTER_PASS_REPORT = """> from: @single-scenario-tester
> to: @single-scenario-writer

テスト結果表の全行を実行しました。新規 + 回帰とも全 pass です。

| ファイル | 結果 |
| --- | --- |
| `tests/e2e/単一ユースケース/test_タスク編集.py` | ✅ |
| `tests/unit/tasks/test_service.py` | ✅ |
"""

TESTER_FAIL_REPORT = """> from: @single-scenario-tester
> to: @single-scenario-writer

テスト結果表の全行を実行しました。1 件 fail です。

| ファイル | ケース | 結果 |
| --- | --- | --- |
| `tests/e2e/単一ユースケース/test_タスク編集.py` | `test_error_when_タイトルが空` | ❌ |
| `tests/unit/tasks/test_service.py` | 全実行 | ✅ |

失敗内容: タイトルを空文字にして保存しても `ValidationError` が送出されず、ストアが更新される。
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
        # 準備
        store = _store()
        # 実行
        update_task(store, "t1", "新タイトル", "新本文")
        listed = list_tasks(store)
        # 検証
        self.assertEqual(listed[0].title, "新タイトル")
        self.assertEqual(listed[0].content, "新本文")
'''

_COMPLEX_E2E_ERROR_CASE = '''
    def test_error_when_タイトルが空(self):
        """タイトルを空にして保存すると一覧が変わらない（異常系）。"""
        # 準備
        store = _store()
        # 実行・検証
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "")
        listed = list_tasks(store)
        self.assertEqual(listed[0].title, "旧タイトル")
        self.assertEqual(listed[0].content, "旧本文")
'''

COMPLEX_E2E_TEST_PY = _COMPLEX_E2E_HEADER + _COMPLEX_E2E_ERROR_CASE + _E2E_FOOTER
COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE = _COMPLEX_E2E_HEADER + _E2E_FOOTER

# 複合シナリオが story のユースケース要件（タイトルは 1 文字以上）と矛盾している状態
COMPLEX_SCENARIO_MD_CONFLICTING = COMPLEX_SCENARIO_MD.replace(
    "## 異常シナリオ（タイトルが空）", "## 正常シナリオ（タイトルが空）"
).replace(
    """  U0([ユーザー]) -->|タイトルを空にして保存| UC1([タスク編集:異常シナリオ<br>（タイトルが空）])
  UC1 -->|保存されない| DONE([一覧が編集前のままの状態])

  click UC1 "../単一ユースケース/タスク編集.md#異常シナリオタイトルが空\"""",
    """  U0([ユーザー]) -->|タイトルを空にして保存| UC1([タスク編集:正常シナリオ<br>（タイトルが空）])
  UC1 -->|空タイトルのまま保存される| DONE([一覧に空タイトルで反映された状態])

  click UC1 "../単一ユースケース/タスク編集.md#正常シナリオタイトルが空\"""",
).replace(
    "- 一覧が編集前の内容のまま変わっていない",
    "- 一覧に空タイトルのまま反映されている",
)

# 上の矛盾した複合シナリオに忠実に起こした E2E テスト（実装が要件どおりなので落ちる）
COMPLEX_E2E_TEST_PY_FOLLOWING_CONFLICT = _COMPLEX_E2E_HEADER + '''
    def test_normal_when_タイトルが空(self):
        """タイトルを空にして保存すると一覧に空タイトルで反映される（正常系）。"""
        # 準備
        store = _store()
        # 実行
        update_task(store, "t1", "")
        listed = list_tasks(store)
        # 検証
        self.assertEqual(listed[0].title, "")
''' + _E2E_FOOTER

# テストコード側の誤り（正常系の期待値を取り違えている）。シナリオ・実装とも正しい
COMPLEX_E2E_TEST_PY_WRONG_ASSERTION = _COMPLEX_E2E_HEADER.replace(
    'self.assertEqual(listed[0].content, "新本文")',
    'self.assertEqual(listed[0].content, "旧本文")',
) + _COMPLEX_E2E_ERROR_CASE + _E2E_FOOTER

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

_COMPLEX_NEW_ROW = (
    "| `tests/e2e/複合ユースケース/test_タスク編集から一覧反映.py` | 全実行 | | "
    "新規・対応シナリオ: `タスク編集から一覧反映` |"
)
_COMPLEX_FAILED_ROW = (
    "| `tests/e2e/複合ユースケース/test_タスク編集から一覧反映.py` | 全実行 | ❌ | "
    "新規・対応シナリオ: `タスク編集から一覧反映`。"
    "`test_error_when_タイトルが空` が失敗（`ValidationError` が送出されず保存される） |"
)

# 全行 pass を記入済みの epic PR 本文（全 pass の完了報告 の起点）
EPIC_PR_BODY_ALL_PASSED = EPIC_PR_BODY_WITH_TABLE.replace("| 全実行 | |", "| 全実行 | ✅ |")

# fail を記録済みの epic PR 本文（再テストの実行指示 の起点）
EPIC_PR_BODY_FAILED = EPIC_PR_BODY_WITH_TABLE.replace(
    _COMPLEX_NEW_ROW, _COMPLEX_FAILED_ROW
).replace("| 全実行 | |", "| 全実行 | ✅ |")

COMPLEX_TESTER_PASS_REPORT = """> from: @complex-scenario-tester
> to: @complex-scenario-writer

テスト結果表の全行を実行しました。新規 + 回帰とも全 pass です。

| ファイル | 結果 |
| --- | --- |
| `tests/e2e/複合ユースケース/test_タスク編集から一覧反映.py` | ✅ |
| `tests/e2e/単一ユースケース/test_タスク編集.py` | ✅ |
"""

COMPLEX_TESTER_FAIL_REPORT = """> from: @complex-scenario-tester
> to: @complex-scenario-writer

テスト結果表の全行を実行しました。1 件 fail です。

| ファイル | ケース | 結果 |
| --- | --- | --- |
| `tests/e2e/複合ユースケース/test_タスク編集から一覧反映.py` | `test_error_when_タイトルが空` | ❌ |
| `tests/e2e/単一ユースケース/test_タスク編集.py` | 全実行 | ✅ |

失敗内容: タイトルを空文字にして保存しても `ValidationError` が送出されず、一覧に反映される。
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


SUBSYSTEM_TITLE = "タスク編集 バックエンド"
SUBSYSTEM_BODY = """## 前提条件

なし

## 概要

タスク編集のバックエンド側（`update_task`）を担当する。

## 背景

親 story のユースケース「タスク編集」に対応する。

## 現状

### 関連 Issue/PR

なし

### 関連ドキュメント

- `設計図/シナリオ/単一ユースケース/タスク編集.md`

## システム要件（SA）

### 機能要件

| 要件 | 補足 |
| --- | --- |
| 登録済みタスクのタイトルと本文を更新できる | - |
| タイトルは 1 文字以上 100 文字以内で検証する | 違反時は `ValidationError` |
| 本文は 1000 文字以内で検証する | 違反時は `ValidationError` |
| 未登録の ID は `TaskNotFoundError` にする | - |

### スコープ外

- 画面（フロントエンド）の実装
"""


def add_merged_subsystem(gh_live, owner, repo, subsystem_issue_factory, story_number: int):
    """PR を story へマージし終えた状態の subsystem Issue（closed）を用意する。"""
    subsystem = subsystem_issue_factory(
        story_number, SUBSYSTEM_TITLE, body=SUBSYSTEM_BODY, labels=["layer:subsystem", "scope:backend"]
    )
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=subsystem.number, state="closed", state_reason="completed"
    )
    return subsystem


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
    parent_title: str | None = None, parent_body: str | None = None,
    parent_labels: list[str] | None = None,
):
    """全 story マージ済みの epic（Issue + PR + ブランチ）を用意する。

    既定の親は intake Issue。
    上位レイヤーありの経路を再現する場合は parent_* に system Issue の値を渡す。
    """
    from tests.e2e.実装対象 import EPIC_BODY, EPIC_TITLE, INTAKE_BODY, INTAKE_TITLE

    intake, epic = epic_issue_factory(
        parent_title or INTAKE_TITLE, parent_body or INTAKE_BODY, EPIC_TITLE,
        epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"], parent_labels=parent_labels,
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

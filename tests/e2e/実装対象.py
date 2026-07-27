"""tester / implementer の E2E で subsystem ブランチへ seed する実装対象。

sandbox には実装対象もテスト実行環境も無いため、各テストが自分のブランチへ
依存なしで走る最小プロジェクト（stdlib の unittest のみ）を積んでから起動する。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

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
| タスクの内容を編集して保存できる | - |
| 保存時にバリデーションエラーをインライン表示 | タイトルは 1 文字以上 100 文字以内 |
"""

SUBSYSTEM_TITLE = "タスク編集 バックエンド"

SUBSYSTEM_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] `設計図/バックエンド結合/タスク更新.py.md` を新規作成
- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] `update_task` を実装
- [ ] 単体テストを作成して実行
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

  U->>FE: 内容を編集して保存
  FE->>BE: タスク更新リクエスト
  BE-->>FE: 更新後のタスク
  FE-->>U: 一覧へ戻り 完了トースト表示
```

### 期待値

- 一覧に編集後の内容が表示されている

## 異常シナリオ（タイトルが空）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| 入力 | タイトルを空にして保存 | 検証失敗を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant FE as タスク編集画面

  U->>FE: タイトルを空にして保存
  FE->>FE: 入力バリデーション失敗
  FE-->>U: インラインエラー表示
```

### 期待値

- インラインエラーが表示され、保存されていない
"""

INTEGRATION_MD = """---
template_version: 1.0.0
---

# タスク更新

エンドポイント: PATCH /tasks/{task_id}

登録済みタスクのタイトルと本文を更新する。

## インターフェース

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `task_id` | str | ✅ | - | 更新対象のタスク ID | - | パスパラメータ |
| `title` | str | ✅ | - | タスク名 | 1 文字以上 100 文字以内 | - |
| `content` | str | - | `""` | 本文 | 1000 文字以内 | - |

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `id` | str | タスク ID | - | - |
| `title` | str | 更新後のタスク名 | - | - |
| `content` | str | 更新後の本文 | - | - |

## 制約

| 項目 | 制約 | 補足 |
| --- | --- | --- |
| タイムアウト | 制限なし | - |
| 認可 | なし | sandbox 用の最小実装 |

## フロー一覧

| 分類 | フロー名 | 概要 | 補足 |
| --- | --- | --- | --- |
| 正常 | 正常系 | 対象タスクのタイトルと本文を更新して返す | - |
| 異常 | 異常系（タスク不明） | 未登録の ID を指定 | - |
| 異常 | 異常系（タイトルが空） | タイトルの検証失敗 | - |

## 正常系

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（インメモリのストアを実物のまま使う） | - |
| タスク | `t1` のタスクを登録済み | - |

### フロー

```mermaid
sequenceDiagram
  participant C as クライアント
  participant IF as PATCH /tasks/{task_id}
  participant DB as タスクストア

  C->>IF: task_id, title, content
  IF->>IF: 入力値の検証
  IF->>DB: タスクを更新
  IF-->>C: 更新後のタスク
```

### 期待値

- 更新後のタイトルと本文を持つタスクが返る
- ストアの該当タスクが更新後の値になっている

## 異常系（タスク不明）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（インメモリのストアを実物のまま使う） | - |
| 入力 | 未登録の `task_id` を指定 | 検索失敗を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant C as クライアント
  participant IF as PATCH /tasks/{task_id}
  participant DB as タスクストア

  C->>IF: 未登録の task_id
  IF-->>DB: タスクを検索（該当なし）
  IF-->>C: TaskNotFoundError
```

### 期待値

- `TaskNotFoundError` が送出される
- ストアが変更されていない

## 異常系（タイトルが空）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（インメモリのストアを実物のまま使う） | - |
| 入力 | `title` に空文字を指定 | 検証失敗を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant C as クライアント
  participant IF as PATCH /tasks/{task_id}

  C->>IF: title に空文字
  IF->>IF: 入力値の検証に失敗
  IF-->>C: ValidationError
```

### 期待値

- `ValidationError` が送出される
- ストアが変更されていない
"""

MODULE_MD = """---
template_version: 1.1.0
---

# モジュール構成: バックエンド / タスク

`タスク` ドメイン（バックエンド側）に属する構成要素詳細。

## 一覧

| ユースケース | 役割 | コンテナ | 種別 | 名前 | 概要 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| 共通 | ドメインモデル | `src/tasks/models.py` | データモデル | [`Task`](#タスク) | タスク 1 件 | frozen dataclass |
| タスク編集 | サービス | `src/tasks/service.py` | 関数 | [`update_task`](#タスク更新) | タスクのタイトルと本文を更新する | - |

## ディレクトリ構成

```
src/tasks/
├── models.py     # Task
├── errors.py     # TaskNotFoundError / ValidationError
└── service.py    # get_task / update_task
```

## タスク
> 物理名: `Task`<br>
> 種別: データモデル<br>
> コンテナ: `src/tasks/models.py`

タスク 1 件（`@dataclass(frozen=True, slots=True, kw_only=True)`）。

### プロパティ

| 論理名 | プロパティ名 | 型 | 可視性 | デフォルト | 説明 | 例 | 補足 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ID | `id` | `str` | 公開 | - | タスク ID | `"t1"` | - |
| タイトル | `title` | `str` | 公開 | - | タスク名 | `"買い物"` | 1 文字以上 100 文字以内 |
| 本文 | `content` | `str` | 公開 | `""` | 本文 | `"牛乳"` | 1000 文字以内 |

### メソッド

なし

### 単体テスト

なし

## `src/tasks/service.py`
> 種別: ファイル

タスクのドメインロジックを束ねる関数ファイル。

---

### タスク更新
> 物理名: `update_task`<br>
> 種別: 関数

登録済みタスクのタイトルと本文を更新して返す。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| ストア | `store` | `dict[str, Task]` | ✅ | - | タスク ID をキーにしたインメモリのストア | 破壊的に更新する |
| タスク ID | `task_id` | `str` | ✅ | - | 更新対象のタスク ID | - |
| タイトル | `title` | `str` | ✅ | - | 更新後のタスク名 | 1 文字以上 100 文字以内 |
| 本文 | `content` | `str` | - | `""` | 更新後の本文 | 1000 文字以内 |

引数例:

```python
update_task(store, "t1", "買い物", "牛乳")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| [`Task`](#タスク) | 更新後のタスク | - |

戻り値例:

```python
Task(id="t1", title="買い物", content="牛乳")
```

#### 処理

1. `title` を検証する（空文字 or 100 文字超なら `ValidationError`）
2. `content` を検証する（1000 文字超なら `ValidationError`）
3. `store` から `task_id` のタスクを取得する（無ければ `TaskNotFoundError`）
4. タイトルと本文を差し替えたタスクを `store` に書き戻して返す

#### 例外

| 例外名 | 発生条件 | メッセージ | 補足 |
| --- | --- | --- | --- |
| `ValidationError` | `title` が空文字 or 100 文字超 | `"title は 1 文字以上 100 文字以内"` | - |
| `ValidationError` | `content` が 1000 文字超 | `"content は 1000 文字以内"` | - |
| `TaskNotFoundError` | `task_id` が `store` に無い | `"task not found: {task_id}"` | - |

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_update_task` | 正常 | タイトルと本文を更新 | `t1` が登録済みのストア | なし | 更新後の `Task` を返し、ストアも更新される | - |
| `test_update_task_when_content_omitted` | 正常 | 本文の省略 | `content` を渡さない | なし | 本文が空文字になる | デフォルト値の分岐 |
| `test_update_task_when_title_empty` | 異常 | タイトルが空 | `title=""` | なし | `ValidationError` | 例外表「title が空文字 or 100 文字超」に対応 |
| `test_update_task_when_title_too_long` | 異常 | タイトルが長すぎる | `title` が 101 文字 | なし | `ValidationError` | 同上 |
| `test_update_task_when_content_too_long` | 異常 | 本文が長すぎる | `content` が 1001 文字 | なし | `ValidationError` | 例外表「content が 1000 文字超」に対応 |
| `test_update_task_when_task_missing` | 異常 | タスク不明 | 未登録の `task_id` | なし | `TaskNotFoundError`・ストアは不変 | 例外表「task_id が store に無い」に対応 |
"""

TEST_HOWTO_MD = """# テスト実行方法

sandbox プロジェクトのテスト実行コマンドと前提条件。

## 前提

- Python 3.12 以上（標準ライブラリのみ。外部パッケージのインストールは不要）
- テストは `unittest` で書き、`tests/` 配下に実装のパスをミラーして置く

## 単体テスト（バック）

`unittest` で実行。

**前提:**

- 外部依存なし（純粋関数のみ）
- 対象は `設計図/モジュール構成/**` の単体テスト表と 1:1

**全件実行:**

```bash
python3 -m unittest discover -s tests -t .
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

MODELS_PY = '''"""タスクのドメインモデル。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    """タスク 1 件。"""

    id: str
    title: str
    content: str = ""
'''

ERRORS_PY = '''"""タスクドメインの例外。"""
from __future__ import annotations


class TaskNotFoundError(Exception):
    """指定 ID のタスクが存在しない。"""


class ValidationError(Exception):
    """入力値が制約を満たさない。"""
'''

SERVICE_PY = '''"""タスクのドメインロジック。"""
from __future__ import annotations

from tasks.errors import TaskNotFoundError
from tasks.models import Task


def get_task(store: dict[str, Task], task_id: str) -> Task:
    """ストアからタスクを 1 件取得する。"""
    # 未登録の ID は例外にする
    if task_id not in store:
        raise TaskNotFoundError(f"task not found: {task_id}")
    return store[task_id]
'''

PROJECT_FILES = {
    ".gitignore": "__pycache__/\n*.pyc\n",
    "src/tasks/__init__.py": "",
    "src/tasks/models.py": MODELS_PY,
    "src/tasks/errors.py": ERRORS_PY,
    "src/tasks/service.py": SERVICE_PY,
    "tests/__init__.py": "",
    "docs/wiki/テスト/テスト実行方法.md": TEST_HOWTO_MD,
}

INTEGRATION_PATH = "docs/wiki/設計図/バックエンド結合/タスク更新.py.md"
MODULE_PATH = "docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md"

DESIGN_FILES = {
    INTEGRATION_PATH: INTEGRATION_MD,
    MODULE_PATH: MODULE_MD,
}

RED_TEST_PATH = "tests/tasks/test_service.py"
RED_TEST_PY = '''"""`src/tasks/service.py` の単体テスト。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tasks.errors import TaskNotFoundError, ValidationError  # noqa: E402
from tasks.models import Task  # noqa: E402
from tasks.service import update_task  # noqa: E402


def _store() -> dict[str, Task]:
    return {"t1": Task(id="t1", title="旧タイトル", content="旧本文")}


class UpdateTaskTest(unittest.TestCase):
    def test_update_task(self):
        """タイトルと本文を更新する（正常系）。"""
        store = _store()
        result = update_task(store, "t1", "新タイトル", "新本文")
        self.assertEqual(result.title, "新タイトル")
        self.assertEqual(result.content, "新本文")
        self.assertEqual(store["t1"].title, "新タイトル")

    def test_update_task_when_content_omitted(self):
        """本文を省略すると空文字になる（正常系）。"""
        store = _store()
        result = update_task(store, "t1", "新タイトル")
        self.assertEqual(result.content, "")

    def test_update_task_when_title_empty(self):
        """タイトルが空なら ValidationError（異常系）。"""
        store = _store()
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "")

    def test_update_task_when_title_too_long(self):
        """タイトルが 101 文字なら ValidationError（異常系）。"""
        store = _store()
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "a" * 101)

    def test_update_task_when_content_too_long(self):
        """本文が 1001 文字なら ValidationError（異常系）。"""
        store = _store()
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "新タイトル", "a" * 1001)

    def test_update_task_when_task_missing(self):
        """未登録の task_id なら TaskNotFoundError（異常系）。"""
        store = _store()
        with self.assertRaises(TaskNotFoundError):
            update_task(store, "missing", "新タイトル")
        self.assertEqual(store["t1"].title, "旧タイトル")


if __name__ == "__main__":
    unittest.main()
'''


# 異常系 3 ケース（title_too_long / content_too_long / task_missing）が欠落した状態。
# architect のテストレビューで「設計 Wiki の単体テスト表との不整合」として指摘されることを狙う。
INCOMPLETE_TEST_PY = '''"""`src/tasks/service.py` の単体テスト。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tasks.errors import ValidationError  # noqa: E402
from tasks.models import Task  # noqa: E402
from tasks.service import update_task  # noqa: E402


def _store() -> dict[str, Task]:
    return {"t1": Task(id="t1", title="旧タイトル", content="旧本文")}


class UpdateTaskTest(unittest.TestCase):
    def test_update_task(self):
        """タイトルと本文を更新する（正常系）。"""
        store = _store()
        result = update_task(store, "t1", "新タイトル", "新本文")
        self.assertEqual(result.title, "新タイトル")
        self.assertEqual(store["t1"].title, "新タイトル")

    def test_update_task_when_content_omitted(self):
        """本文を省略すると空文字になる（正常系）。"""
        store = _store()
        result = update_task(store, "t1", "新タイトル")
        self.assertEqual(result.content, "")

    def test_update_task_when_title_empty(self):
        """タイトルが空なら ValidationError（異常系）。"""
        store = _store()
        with self.assertRaises(ValidationError):
            update_task(store, "t1", "")


if __name__ == "__main__":
    unittest.main()
'''

# 設計（プロパティ表は id / title / content の 3 つ）に無い updated_at を返す実装。
# テストは全て Green のまま通るため、architect の実装レビューでのみ検知できる差異になる。
DEVIATING_MODELS_PY = '''"""タスクのドメインモデル。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    """タスク 1 件。"""

    id: str
    title: str
    content: str = ""
    updated_at: str = ""
'''

DEVIATING_SERVICE_PY = '''"""タスクのドメインロジック。"""
from __future__ import annotations

from datetime import datetime, timezone

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
    updated = Task(
        id=task.id,
        title=title,
        content=content,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    store[task_id] = updated
    return updated
'''


# テストの構造が設計から決められないモジュール構成。
# コンテナの記述がディレクトリ構成と食い違って import 先が定まらず、
# 単体テスト表が要求する更新履歴・楽観ロックのケースは、それを表す
# プロパティ・引数・例外・処理ステップが設計のどこにも定義されていない。
TESTER_CONFLICT_MODULE_MD = """---
template_version: 1.1.0
---

# モジュール構成: バックエンド / タスク

`タスク` ドメイン（バックエンド側）に属する構成要素詳細。

## 一覧

| ユースケース | 役割 | コンテナ | 種別 | 名前 | 概要 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| 共通 | ドメインモデル | `src/tasks/models.py` | データモデル | [`Task`](#タスク) | タスク 1 件 | frozen dataclass |
| タスク編集 | サービス | `src/tasks/service.py` | 関数 | [`update_task`](#タスク更新) | タスクのタイトルと本文を更新する | - |

## ディレクトリ構成

```
src/tasks/
├── models.py     # Task
├── errors.py     # TaskNotFoundError / ValidationError
├── update.py     # update_task
└── service.py    # get_task
```

## タスク
> 物理名: `Task`<br>
> 種別: データモデル<br>
> コンテナ: `src/tasks/models.py`

タスク 1 件（`@dataclass(frozen=True, slots=True, kw_only=True)`）。

### プロパティ

| 論理名 | プロパティ名 | 型 | 可視性 | デフォルト | 説明 | 例 | 補足 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ID | `id` | `str` | 公開 | - | タスク ID | `"t1"` | - |
| タイトル | `title` | `str` | 公開 | - | タスク名 | `"買い物"` | 100 文字以内 |
| 本文 | `content` | `str` | 公開 | `""` | 本文 | `"牛乳"` | 1000 文字以内 |

### メソッド

なし

### 単体テスト

なし

## `src/tasks/service.py`
> 種別: ファイル

タスクのドメインロジックを束ねる関数ファイル。

### タスク更新
> 物理名: `update_task`<br>
> 種別: 関数

登録済みタスクのタイトルと本文を更新して返す。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| ストア | `store` | `dict[str, Task]` | ✅ | - | タスク ID をキーにしたインメモリのストア | 破壊的に更新する |
| タスク ID | `task_id` | `str` | ✅ | - | 更新対象のタスク ID | - |
| タイトル | `title` | `str` | ✅ | - | 更新後のタスク名 | 1 文字以上 100 文字以内 |
| 本文 | `content` | `str` | - | `""` | 更新後の本文 | 1000 文字以内 |

引数例:

```python
update_task(store, "t1", "買い物", "牛乳")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| [`Task`](#タスク) | 更新後のタスク | - |

戻り値例:

```python
Task(id="t1", title="買い物", content="牛乳")
```

#### 処理

1. `title` を検証する（空文字 or 100 文字超なら `ValidationError`）
2. `content` を検証する（1000 文字超なら `ValidationError`）
3. `store` から `task_id` のタスクを取得する（無ければ `TaskNotFoundError`）
4. タイトルと本文を差し替えたタスクを `store` に書き戻して返す

#### 例外

| 例外名 | 発生条件 | メッセージ | 補足 |
| --- | --- | --- | --- |
| `ValidationError` | `title` が空文字 or 100 文字超 | `"title は 1 文字以上 100 文字以内"` | - |
| `ValidationError` | `content` が 1000 文字超 | `"content は 1000 文字以内"` | - |
| `TaskNotFoundError` | `task_id` が `store` に無い | `"task not found: {task_id}"` | - |

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_update_task` | 正常 | タイトルと本文を更新 | `t1` が登録済みのストア | なし | 更新後の `Task` を返し、ストアも更新される | - |
| `test_update_task_when_content_omitted` | 正常 | 本文の省略 | `content` を渡さない | なし | 本文が空文字になる | デフォルト値の分岐 |
| `test_update_task_when_history_recorded` | 正常 | 更新履歴の記録 | `t1` が登録済みのストア | なし | 更新前のタイトルと本文が履歴として参照できる | - |
| `test_update_task_when_title_empty` | 異常 | タイトルが空 | `title=""` | なし | `ValidationError` | 例外表「title が空文字 or 100 文字超」に対応 |
| `test_update_task_when_title_too_long` | 異常 | タイトルが長すぎる | `title` が 101 文字 | なし | `ValidationError` | 同上 |
| `test_update_task_when_content_too_long` | 異常 | 本文が長すぎる | `content` が 1001 文字 | なし | `ValidationError` | 例外表「content が 1000 文字超」に対応 |
| `test_update_task_when_task_missing` | 異常 | タスク不明 | 未登録の `task_id` | なし | `TaskNotFoundError`・ストアは不変 | 例外表「task_id が store に無い」に対応 |
| `test_update_task_when_conflicting_update` | 異常 | 同時更新の競合 | 取得後に別経路で同じタスクが更新された状態で更新する | なし | `ConflictError`・後勝ちにならない | 楽観ロックのリビジョンで判定 |
"""

# 実装が設計から決められないモジュール構成。
# 設計は「戻り値なし・更新は store に反映」で一貫している一方、レビュー済みのテストは
# 戻り値のタスクを検証するため、シグネチャを変えない限りどちらかが必ず破綻する。
IMPL_CONFLICT_MODULE_MD = """---
template_version: 1.1.0
---

# モジュール構成: バックエンド / タスク

`タスク` ドメイン（バックエンド側）に属する構成要素詳細。

## 一覧

| ユースケース | 役割 | コンテナ | 種別 | 名前 | 概要 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| 共通 | ドメインモデル | `src/tasks/models.py` | データモデル | [`Task`](#タスク) | タスク 1 件 | frozen dataclass |
| タスク編集 | サービス | `src/tasks/service.py` | 関数 | [`update_task`](#タスク更新) | タスクのタイトルと本文を更新する | - |

## ディレクトリ構成

```
src/tasks/
├── models.py     # Task
├── errors.py     # TaskNotFoundError / ValidationError
└── service.py    # get_task / update_task
```

## タスク
> 物理名: `Task`<br>
> 種別: データモデル<br>
> コンテナ: `src/tasks/models.py`

タスク 1 件（`@dataclass(frozen=True, slots=True, kw_only=True)`）。

### プロパティ

| 論理名 | プロパティ名 | 型 | 可視性 | デフォルト | 説明 | 例 | 補足 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ID | `id` | `str` | 公開 | - | タスク ID | `"t1"` | - |
| タイトル | `title` | `str` | 公開 | - | タスク名 | `"買い物"` | 1 文字以上 100 文字以内 |
| 本文 | `content` | `str` | 公開 | `""` | 本文 | `"牛乳"` | 1000 文字以内 |

### メソッド

なし

### 単体テスト

なし

## `src/tasks/service.py`
> 種別: ファイル

タスクのドメインロジックを束ねる関数ファイル。

### タスク更新
> 物理名: `update_task`<br>
> 種別: 関数

登録済みタスクのタイトルと本文を更新して返す。

#### 引数

| 論理名 | 引数名 | 型 | 必須 | デフォルト | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| ストア | `store` | `dict[str, Task]` | ✅ | - | タスク ID をキーにしたインメモリのストア | 破壊的に更新する |
| タスク ID | `task_id` | `str` | ✅ | - | 更新対象のタスク ID | - |
| タイトル | `title` | `str` | ✅ | - | 更新後のタスク名 | 1 文字以上 100 文字以内 |
| 本文 | `content` | `str` | - | `""` | 更新後の本文 | 1000 文字以内 |

引数例:

```python
update_task(store, "t1", "買い物", "牛乳")
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `None` | 戻り値なし | 更新結果は `store` に反映する |

#### 処理

1. `title` を検証する（空文字 or 100 文字超なら `ValidationError`）
2. `content` を検証する（1000 文字超なら `ValidationError`）
3. `store` から `task_id` のタスクを取得する（無ければ `TaskNotFoundError`）
4. タイトルと本文を差し替えたタスクを `store` に書き戻す（呼び出し元へは何も返さない）

#### 例外

| 例外名 | 発生条件 | メッセージ | 補足 |
| --- | --- | --- | --- |
| `ValidationError` | `title` が空文字 or 100 文字超 | `"title は 1 文字以上 100 文字以内"` | - |
| `ValidationError` | `content` が 1000 文字超 | `"content は 1000 文字以内"` | - |
| `TaskNotFoundError` | `task_id` が `store` に無い | `"task not found: {task_id}"` | - |

#### 単体テスト

| テスト名 | 正常/異常 | 概要 | 条件 | Mock | 期待値 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `test_update_task` | 正常 | タイトルと本文を更新 | `t1` が登録済みのストア | なし | `store` の該当タスクが更新後のタイトルと本文になっている | - |
| `test_update_task_when_content_omitted` | 正常 | 本文の省略 | `content` を渡さない | なし | `store` の該当タスクの本文が空文字になる | デフォルト値の分岐 |
| `test_update_task_when_title_empty` | 異常 | タイトルが空 | `title=""` | なし | `ValidationError` | 例外表「title が空文字 or 100 文字超」に対応 |
| `test_update_task_when_title_too_long` | 異常 | タイトルが長すぎる | `title` が 101 文字 | なし | `ValidationError` | 同上 |
| `test_update_task_when_content_too_long` | 異常 | 本文が長すぎる | `content` が 1001 文字 | なし | `ValidationError` | 例外表「content が 1000 文字超」に対応 |
| `test_update_task_when_task_missing` | 異常 | タスク不明 | 未登録の `task_id` | なし | `TaskNotFoundError`・ストアは不変 | 例外表「task_id が store に無い」に対応 |
"""


def setup_subsystem(
    gh_live, owner, repo,
    epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file,
    *, pr_body: str,
):
    """epic / story / subsystem の Issue と PR を作り、subsystem PR まで用意する。"""
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    epic_pr = epic_pr_factory(
        branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n"
    )
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number), labels=["layer:story", "type:feat"],
    )
    story_branch = f"feat/story/task-edit-{story.number}"
    story_pr = draft_pr_factory(
        story_branch, STORY_TITLE, f"## 紐づく Issue\n\n- #{story.number}\n", base_branch=epic_branch
    )
    commit_file(story_branch, SCENARIO_PATH, SCENARIO_MD, "docs: 単一UC シナリオ（タスク編集）を追加")
    # subsystem Issue は確認ラベルなしで作る（起動対象は subsystem PR 側）
    subsystem = subsystem_issue_factory(
        story.number, SUBSYSTEM_TITLE, labels=["layer:subsystem", "scope:backend"]
    )
    subsystem_branch = f"feat/backend/task-edit-{subsystem.number}/update-api"
    pr = draft_pr_factory(
        subsystem_branch, SUBSYSTEM_TITLE,
        pr_body.format(subsystem_number=subsystem.number), base_branch=story_branch,
    )
    return {
        "intake": intake, "epic": epic, "story": story, "subsystem": subsystem,
        "pr": pr, "epic_pr": epic_pr, "story_pr": story_pr,
        "epic_branch": epic_branch, "story_branch": story_branch,
        "subsystem_branch": subsystem_branch,
    }


def seed_subsystem_branch(
    gh_live, owner, repo, commit_file, branch: str,
    *, with_red_test: bool = False, include_design: bool = True,
    design_overrides: dict[str, str] | None = None,
) -> str:
    """subsystem ブランチに実装対象・設計 Wiki（必要なら Red テスト）を積み、seed 後の sha を返す。"""
    files = {**PROJECT_FILES, **DESIGN_FILES} if include_design else dict(PROJECT_FILES)
    if design_overrides:
        files = {**files, **design_overrides}
    if with_red_test:
        files = {**files, RED_TEST_PATH: RED_TEST_PY, "tests/tasks/__init__.py": ""}
    for path, content in files.items():
        commit_file(branch, path, content, f"chore: e2e 用に {path} を配置")
    return gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=branch).parsed_data.commit.sha


def add_worktree(local_path: str, branch: str, *, attempts: int = 6) -> None:
    """subsystem ブランチの worktree を作る（subsystem-conductor の完了処理の再現）。

    並列実行では他テストの git 操作と ref のロックが競合するため、間隔を空けて数回試す。
    """
    worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    detail = ""
    for attempt in range(attempts):
        # 競合したときは間隔を空けてから再試行する
        if attempt:
            time.sleep(5 * attempt)
        fetched = subprocess.run(
            ["git", "-C", local_path, "fetch", "origin"], capture_output=True, text=True, check=False
        )
        if fetched.returncode != 0:
            detail = fetched.stderr
            continue
        added = subprocess.run(
            ["git", "-C", local_path, "worktree", "add", str(worktree_path), branch],
            capture_output=True, text=True, check=False,
        )
        if added.returncode == 0 or worktree_path.exists():
            return
        detail = added.stderr
    raise RuntimeError(f"worktree を作成できない: {branch}\n{detail}")


def count_test_functions(gh_live, owner: str, repo: str, paths: list[str], ref: str) -> int:
    """指定 commit のテストファイル群に定義されたテスト関数の数を数える。

    Red のテストは import 段階で失敗して個々のケースを実行できないため、
    ケースが揃っているかは実行結果ではなく定義を数えて判定する。
    """
    import base64
    import re

    total = 0
    for path in paths:
        content = gh_live.rest.repos.get_content(
            owner=owner, repo=repo, path=path, ref=ref
        ).parsed_data
        body = base64.b64decode(content.content).decode("utf-8")
        total += len(re.findall(r"^\s*def test_", body, re.M))
    return total


def branch_sha(gh_live, owner: str, repo: str, branch: str) -> str:
    """ブランチ先端の commit sha を返す（検証時点を固定するために使う）。"""
    return gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=branch).parsed_data.commit.sha


def run_branch_tests(local_path: str, branch: str, *, ref: str | None = None) -> subprocess.CompletedProcess:
    """ブランチの内容を使い捨ての worktree に取り出して単体テストを実行する。

    エージェントが作った worktree には手を触れず、検証専用の worktree で実測する。
    `ref` を渡すとその commit を検証する（後続エージェントの push で結果が変わるのを防ぐ）。
    """
    subprocess.run(
        ["git", "-C", local_path, "fetch", "origin", branch], capture_output=True, text=True, check=True
    )
    tmp = tempfile.mkdtemp(prefix="e2e-verify-")
    work = str(Path(tmp) / "wt")
    try:
        subprocess.run(
            ["git", "-C", local_path, "worktree", "add", "--detach", work, ref or f"origin/{branch}"],
            capture_output=True, text=True, check=True,
        )
        return subprocess.run(
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=work, capture_output=True, text=True, check=False,
        )
    finally:
        subprocess.run(
            ["git", "-C", local_path, "worktree", "remove", "--force", work],
            capture_output=True, text=True, check=False,
        )
        shutil.rmtree(tmp, ignore_errors=True)


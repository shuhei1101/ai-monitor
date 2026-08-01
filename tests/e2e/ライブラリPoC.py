"""ライブラリPoC検証 の E2E で subsystem PR / PoC PR に seed する資材。

sandbox には外部パッケージを入れられないため、候補ライブラリは標準ライブラリの `sqlite3` に見立てる。
検証観点は追加インストールなしで実測できるものだけにする。
"""
from __future__ import annotations

SUBSYSTEM_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] タスクの永続化ライブラリを選定
"""

# 発注元が PR 作成時に記入するところまでの本文（実測値・判定は未記入）
POC_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## 発注元 PR

- #{origin_pr_number}

## 検証対象

| 項目 | 内容 | 補足 |
| --- | --- | --- |
| ライブラリ | sqlite3 | - |
| 概要 | Python 標準ライブラリの組み込み RDB（ファイル / インメモリ） | 追加インストール不要 |
| バージョン | Python 3.12 同梱 | - |
| ライセンス | PSF License | 商用利用可 |
| 公式 URL | https://docs.python.org/3/library/sqlite3.html | - |
| 公式ドキュメント | https://docs.python.org/3/library/sqlite3.html | - |
| 既存 Wiki | - | - |

## 調査結果

### 使い方の要点

- インストール不要（標準ライブラリ）。`import sqlite3` で使える
- `sqlite3.connect(":memory:")` でプロセス内の一時 DB を作れる
- プレースホルダは `?` で、`execute(sql, params)` にタプルを渡す

### コード例

```python
import sqlite3

conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, content TEXT)")
conn.execute("INSERT INTO tasks VALUES (?, ?, ?)", ("t1", "買い物", "牛乳"))
row = conn.execute("SELECT title FROM tasks WHERE id = ?", ("t1",)).fetchone()
```

### 観点別評価

| 観点 | 評価 | 補足 |
| --- | --- | --- |
| 導入コスト | ○ | 標準ライブラリで依存が増えない |
| テスト容易性 | ○ | インメモリ DB を fixture にできる |
| 同時実行 | △ | 書き込みロックの粒度が粗い |

## 検証観点と結果

| 観点 | 成功条件 | 実測値 | 判定 | 補足 |
| --- | --- | --- | --- | --- |
| インメモリ DB の CRUD | `:memory:` で 作成 → 挿入 → 取得 → 更新 → 削除 が一連で成功する | - | - | 単体テストの fixture に使う |
| 一括挿入の性能 | 1000 件の挿入が 1 秒以内に完了する | - | - | - |
| 型の往復 | `str` / `int` / `None` が挿入時と同じ型で取り出せる | - | - | - |
"""

# 「ライブラリ自体が await 可能なクエリ API を提供する」は sqlite3 では事実として満たせない
POC_PR_BODY_UNMET = POC_PR_BODY + """| 非同期クエリ | ライブラリ自体が `await` 可能なクエリ API（コルーチン関数）を標準で提供する | - | - | 非同期フレームワークからの利用を想定 |
"""

# 初回検証が終わった状態の本文（再検証の起点）
POC_PR_BODY_DONE = POC_PR_BODY.replace(
    "| インメモリ DB の CRUD | `:memory:` で 作成 → 挿入 → 取得 → 更新 → 削除 が一連で成功する | - | - | 単体テストの fixture に使う |",
    "| インメモリ DB の CRUD | `:memory:` で 作成 → 挿入 → 取得 → 更新 → 削除 が一連で成功する | 一連の操作が成功 | ✅ | 単体テストの fixture に使う |",
).replace(
    "| 一括挿入の性能 | 1000 件の挿入が 1 秒以内に完了する | - | - | - |",
    "| 一括挿入の性能 | 1000 件の挿入が 1 秒以内に完了する | 0.01 秒 | ✅ | executemany を使用 |",
).replace(
    "| 型の往復 | `str` / `int` / `None` が挿入時と同じ型で取り出せる | - | - | - |",
    "| 型の往復 | `str` / `int` / `None` が挿入時と同じ型で取り出せる | 3 種とも同じ型で取得 | ✅ | - |",
) + """
**所感:**
- インメモリ DB は接続を閉じると消えるので、テストでは接続をフィクスチャの寿命に合わせる

## 最小再現コード

```python
# poc/sqlite3_poc.py — CRUD 検証の核心部（全体は PR diff 参照）
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, content TEXT)")
conn.execute("INSERT INTO tasks VALUES (?, ?, ?)", ("t1", "買い物", "牛乳"))
```

**diff の見どころ:** `poc/sqlite3_poc.py` の 1 ファイルだけ。
"""

POC_CODE_PATH = "poc/sqlite3_poc.py"
POC_CODE = '''"""sqlite3 の PoC（インメモリ DB の CRUD / 一括挿入 / 型の往復）。"""
from __future__ import annotations

import sqlite3
import time


def _connect() -> sqlite3.Connection:
    """検証用のインメモリ DB を作る。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, content TEXT)")
    return conn


def check_crud() -> str:
    """作成 → 挿入 → 取得 → 更新 → 削除 の一連を実行する。"""
    conn = _connect()
    conn.execute("INSERT INTO tasks VALUES (?, ?, ?)", ("t1", "買い物", "牛乳"))
    title = conn.execute("SELECT title FROM tasks WHERE id = ?", ("t1",)).fetchone()[0]
    conn.execute("UPDATE tasks SET title = ? WHERE id = ?", ("買い出し", "t1"))
    conn.execute("DELETE FROM tasks WHERE id = ?", ("t1",))
    remaining = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    return f"取得={title} 削除後件数={remaining}"


def check_bulk_insert() -> str:
    """1000 件の一括挿入にかかる時間を測る。"""
    conn = _connect()
    rows = [(f"t{i}", f"タイトル{i}", "") for i in range(1000)]
    started = time.perf_counter()
    conn.executemany("INSERT INTO tasks VALUES (?, ?, ?)", rows)
    elapsed = time.perf_counter() - started
    return f"{elapsed:.3f} 秒"


if __name__ == "__main__":
    print(check_crud())
    print(check_bulk_insert())
'''

VERIFY_INSTRUCTION = """> from: @architect
> to: @library-poc-runner

タスクの永続化ライブラリの候補として sqlite3 の PoC 検証をお願いします。

本文の `## 検証観点と結果` に沿って検証し、実測値・判定・所感を本文へ記録してください。
追加インストールが要らない範囲で、最小のコードで実測できる形にしてください。

------
"""

REVERIFY_INSTRUCTION = """> from: @architect
> to: @library-poc-runner

結果を確認しました。採用判断の前に観点を 1 つ足したいので、追加検証をお願いします。

| 観点 | 成功条件 |
| --- | --- |
| トランザクションのロールバック | 例外発生時に `rollback()` で挿入前の状態へ戻る |

既存の観点はそのままで、この行を `## 検証観点と結果` に追加して実測値・判定を記入してください。

------
"""

PREVIOUS_REPORT = """> from: @library-poc-runner
> to: @architect

sqlite3 の PoC 検証が完了しました。

| 観点 | 実測値 | 判定 |
| --- | --- | --- |
| インメモリ DB の CRUD | 一連の操作が成功 | ✅ |
| 一括挿入の性能 | 0.01 秒 | ✅ |
| 型の往復 | 3 種とも同じ型で取得 | ✅ |

| commit | 内容 |
| --- | --- |
| seed | sqlite3 の PoC コードを追加 |

------
"""


# 発注前（候補比較の合意待ち）の状態を作るための資材
EXTERNAL_LIB_INDEX_PATH = "docs/wiki/外部ライブラリ/README.md"
EXTERNAL_LIB_INDEX_MD = """---
template_version: 1.0.0
---

# 外部ライブラリ

採用済みの外部ライブラリ / 外部ツールのインデックス。

## 目次

| ライブラリ | ページ | 概要 | 補足 |
| --- | --- | --- | --- |
"""

CANDIDATES = ("sqlite3", "shelve")

CANDIDATE_COMPARISON = """> from: @architect
> to: @{login}

タスクの永続化に使うライブラリを調査しました。
このプロジェクトは外部パッケージを追加できないため、標準ライブラリの範囲で 2 候補に絞っています。

| 候補 | 概要 | ライセンス | 導入コスト |
| --- | --- | --- | --- |
| sqlite3 | 組み込み RDB（ファイル / インメモリ） | PSF License | 追加インストール不要 |
| shelve | pickle ベースの永続 dict | PSF License | 追加インストール不要 |

いずれも未経験のため PoC で実測したいです。
検証観点の案は以下です。

| 観点 | 成功条件 |
| --- | --- |
| CRUD | 作成 → 書き込み → 取得 → 更新 → 削除 が一連で成功する |
| 一括書き込みの性能 | 1000 件の書き込みが 1 秒以内に完了する |
| 型の往復 | `str` / `int` / `None` が書き込み時と同じ型で取り出せる |

- 候補と検証観点で問題なければ、このコメントに合意の返信をして assignee を外してください
- 変更したい場合は修正内容を返信してください

------
"""

AGREE_INSTRUCTION = (
    "候補（sqlite3 / shelve）と検証観点（CRUD / 一括書き込みの性能 / 型の往復）で問題ありません。"
    "この内容で候補ごとに PoC の検証をお願いします。"
)

ADOPT_DECISION = (
    "結果を確認しました。sqlite3 を採用してください。"
    "外部ライブラリ Wiki への反映をお願いします。"
)

WIKI_APPROVAL = "外部ライブラリ Wiki の内容で問題ありません。承認します。"


def result_rows(body: str) -> list[str]:
    """`## 検証観点と結果` の表のデータ行を返す。"""
    text = body.replace("\r\n", "\n")
    section = text.split("## 検証観点と結果", 1)[1]
    # 次の H2 の手前までを対象にする
    section = section.split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")]
    # ヘッダー行と区切り行を落とす
    return rows[2:]


def setup_poc_pr(
    gh_live, owner, repo,
    epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file,
    *, poc_body: str, poc_files: dict[str, str] | None = None,
):
    """subsystem の一式と、発注元が作成済みの PoC Draft PR を用意する。"""
    from tests.e2e.実装対象 import setup_subsystem

    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    poc_branch = f"poc/backend/task/task-edit-{ctx['subsystem'].number}/sqlite3"
    poc_pr = draft_pr_factory(
        poc_branch, f"PoC: sqlite3（#{ctx['subsystem'].number}）",
        poc_body.format(subsystem_number=ctx["subsystem"].number, origin_pr_number=ctx["pr"].number),
        base_branch="master",
    )
    for path, content in (poc_files or {}).items():
        commit_file(poc_branch, path, content, f"chore: e2e 用に {path} を配置")
    ctx["poc_pr"] = poc_pr
    ctx["poc_branch"] = poc_branch
    return ctx

"""エスカレーション系 複合UC の E2E で共有するセットアップとユーザー役の操作。

3 本とも「上がってきた論点にユーザーが方針を選び、決定が下位へ降りて設計が再開する」形なので、
ゲートへの応答を選択肢の表で切り替える 1 つのドライバで進める。
"""
from __future__ import annotations

from githubkit.exception import RequestFailed

# 設計タスクをモジュール構成 1 件に絞った subsystem PR 本文。
# バックエンド結合は seed 済みにして、インターフェース確定報告（上位への連絡）が混ざらないようにする。
SUBSYSTEM_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] `update_task` を実装
- [ ] 単体テストを作成して実行
"""

COMPLEX_SCENARIO_PATH = "docs/wiki/設計図/シナリオ/複合ユースケース/タスク編集から一覧反映.md"
COMPLEX_SCENARIO_MD = """---
template_version: 1.0.0
---

# タスク編集から一覧反映

タスクを編集して保存し、一覧画面に反映されるまでの業務シナリオ。

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

- 一覧に編集後の内容が表示されている

## 異常シナリオ

なし
"""

# architect が subsystem PR に投稿済みのライブラリ選定の相談（subsystem内解決 の起点）
CONSULT_COMMENT = """> from: @architect
> to: @{login}

`update_task` の入力検証に使うバリデーションライブラリを調査しましたが、要件を満たす候補が残りませんでした。

| 候補 | 判定 | 理由 |
| --- | --- | --- |
| validate-a | 不可 | ライセンスが商用利用不可 |
| validate-b | 不可 | ライセンスが商用利用不可 |
| validate-c | 不可 | メンテナンス停止（最終リリースが 4 年前） |

対応の方向性です。

| 案 | 内容 | 想定影響 |
| --- | --- | --- |
| A | 検証処理を自前実装する | 実装量が増える |
| B | subsystem レイヤーでは決められないため上位へ相談する | 判断が降りてくるまで設計が止まる |

推奨: B（ライセンス方針の判断は subsystem の裁量を超えるため）
"""

ESCALATE_INSTRUCTION = (
    "B でお願いします。subsystem レイヤーでは決められない論点なので、"
    "subsystem-conductor へエスカレーションしてください。"
)

# architect が subsystem PR に投稿済みのエスカレーション報告（story / epic レベルの起点）
ESCALATION_REPORT = """> from: @architect
> to: @subsystem-conductor

単一ユースケースシナリオ「タスク編集」の前提が、この subsystem では満たせません。

経緯:
- シナリオの `## 正常シナリオ` は「保存の完了を待って一覧へ戻る」同期の流れを前提にしている
- 更新の確定は外部の承認基盤への連携が必須で、応答が非同期（数秒〜数分）でしか返らない
- 同期化する手段（ポーリング待ち合わせ・タイムアウト付き待機）はいずれも UC の応答時間の前提を満たせない

論点:
- 同期前提のシナリオを維持するのか、非同期の結末に変えるのかを決められない

検討済みの選択肢と却下理由:
- subsystem 内での待ち合わせ実装: 応答時間の前提を満たせないため却下
- 承認基盤の同期 API への変更: 外部システムのため subsystem からは変更できない
"""

LOCAL_RESOLUTION = (
    "A でお願いします。subsystem レイヤーの解決案（検証処理を自前実装する方針）で設計を進めてください。"
)

RELAY_UP_FROM_SUBSYSTEM = (
    "B でお願いします。subsystem レイヤーでは決められないので、親 story へ中継してください。"
)

RELAY_UP_FROM_STORY = (
    "B でお願いします。story レイヤーでも決められないので、親 epic へ中継してください。"
)

STORY_SCENARIO_FIX = (
    "A でお願いします。単一ユースケースシナリオ「タスク編集」を、"
    "保存完了を待たずに受付完了を表示する非同期の結末へ変更する方針で進めてください。"
)

EPIC_SCENARIO_FIX = (
    "A でお願いします。epic の横断要件を非同期前提へ変更し、"
    "複合ユースケースシナリオ「タスク編集から一覧反映」も受付完了までの流れへ修正する方針で進めてください。"
)


def me(gh_live) -> str:
    """認証中のユーザーログイン名を返す。"""
    return gh_live.rest.users.get_authenticated().parsed_data.login


def label_names(data) -> set[str]:
    """スナップショットのラベル名集合を返す。"""
    return {label.name for label in data.labels}


def confirm_labels(data) -> list[str]:
    """スナップショットの確認ラベルだけを返す。"""
    return sorted(name for name in label_names(data) if name.startswith("確認:"))


def unresolved_review_threads(gh_live, owner: str, repo: str, pr_number: int) -> list[str]:
    """PR の未解決インライン指摘スレッドの先頭コメントを返す。"""
    query = """
    query($owner: String!, $repo: String!, $number: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
          reviewThreads(first: 100) {
            nodes { isResolved comments(first: 1) { nodes { body } } }
          }
        }
      }
    }
    """
    data = gh_live.graphql(query, {"owner": owner, "repo": repo, "number": pr_number})
    nodes = data["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    return [
        node["comments"]["nodes"][0]["body"][:120]
        for node in nodes
        if not node["isResolved"] and node["comments"]["nodes"]
    ]


def waiting_for_user(data) -> bool:
    """エージェントがターンを終えてユーザー待ちに入っているかを返す。

    `議論中` と assignee は前フェーズから残ることがあるため、ターンの終了は
    モニターが付ける処理中ラベルが消えていることで判定する。
    """
    names = label_names(data)
    if "議論中" not in names or not data.assignees:
        return False
    return not [name for name in names if name.startswith("処理中:")]


def issue(gh_live, owner, repo, number):
    """Issue / PR の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def comments(gh_live, owner, repo, number):
    """Issue / PR のコメント一覧を返す。"""
    return gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=number).parsed_data


def comments_from(gh_live, owner, repo, number, sender: str) -> list:
    """指定エージェントが起点のコメントだけを返す。"""
    return [
        c for c in comments(gh_live, owner, repo, number)
        if (c.body or "").lstrip().startswith(f"> from: @{sender}")
    ]


def append_user_block(gh_live, owner, repo, comment, text: str) -> None:
    """ユーザーの返信ブロックを既存コメントに追記する（reply_comment と同じ `---` 区切り）。"""
    gh_live.rest.issues.update_comment(
        owner=owner, repo=repo, comment_id=comment.id, body=f"{comment.body}\n\n---\n{text}"
    )


def wait_for_user(gh_live, owner, repo, number, login: str) -> None:
    """エージェントの待機状態（議論中 + assignee=ユーザー）を再現する。"""
    gh_live.rest.issues.add_labels(owner=owner, repo=repo, issue_number=number, labels=["議論中"])
    gh_live.rest.issues.add_assignees(owner=owner, repo=repo, issue_number=number, assignees=[login])


def approve(gh_live, owner, repo, number, assignees) -> None:
    """ユーザー役の承認操作（議論中 除去 + assignee 外し）。"""
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name="議論中")
    except RequestFailed:
        pass
    for assignee in assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def tree_paths(gh_live, owner: str, repo: str, branch: str, prefix: str) -> list[str]:
    """指定ブランチで prefix から始まるファイルパス一覧を返す。"""
    sha = gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=branch).parsed_data.commit.sha
    tree = gh_live.rest.git.get_tree(owner=owner, repo=repo, tree_sha=sha, recursive="1").parsed_data
    return [entry.path for entry in tree.tree if entry.path.startswith(prefix)]


def design_paths(gh_live, owner: str, repo: str, branch: str) -> list[str]:
    """指定ブランチの `docs/wiki/設計図/` 配下のファイルパス一覧を返す。"""
    return tree_paths(gh_live, owner, repo, branch, "docs/wiki/設計図/")


def scenario_changed(gh_live, owner: str, repo: str, branch: str, folder: str, seeded: str) -> bool:
    """指定フォルダのシナリオが seed 時点から変わっているかを返す（リネームされていても拾う）。"""
    paths = tree_paths(gh_live, owner, repo, branch, folder)
    return bool(paths) and any(file_text(gh_live, owner, repo, path, branch) != seeded for path in paths)


def file_text(gh_live, owner: str, repo: str, path: str, ref: str) -> str:
    """指定 ref のファイル内容を文字列で返す。"""
    import base64

    content = gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref).parsed_data
    return base64.b64decode(content.content).decode("utf-8")


def drive_until_tester(
    gh_live, owner, repo, *, pr_number: int, faces, choices, wait_until,
    max_rounds: int = 14, timeout_sec: int = 2400, interval_sec: int = 30,
) -> list[tuple[str, str]]:
    """ユーザー役として各面のゲートに応答し、subsystem PR に `確認:tester` が付くまで進める。

    faces は監視する面の `(種別, 番号)` 一覧、choices は `(種別, 確認ラベル)` に対する返信文
    （返信不要のゲートは None）。応答したゲートの履歴を返す。
    """
    history: list[tuple[str, str]] = []

    def _next_event():
        pr = issue(gh_live, owner, repo, pr_number)
        # 終端（tester への引き渡し）を最優先で判定する
        if "確認:tester" in label_names(pr):
            return ("done", pr, None)
        for kind, number in faces:
            data = issue(gh_live, owner, repo, number)
            names = label_names(data)
            # 議論中 + assignee が揃った面がユーザーの番
            if "議論中" in names and data.assignees:
                confirms = sorted(name for name in names if name.startswith("確認:"))
                return ("gate", data, (kind, number, confirms))
        return None

    for _ in range(max_rounds):
        event, data, gate = wait_until(
            _next_event, timeout_sec=timeout_sec, interval_sec=interval_sec,
            message="ユーザー確認ゲート または tester への引き渡し",
        )
        if event == "done":
            return history
        kind, number, confirms = gate
        key = next(((kind, name) for name in confirms if (kind, name) in choices), None)
        if key:
            history.append(key)
            reply = choices[key]
            if reply:
                latest = comments(gh_live, owner, repo, number)[-1]
                append_user_block(gh_live, owner, repo, latest, reply)
        approve(gh_live, owner, repo, number, data.assignees)
    raise AssertionError(f"{max_rounds} 回のゲート応答でも tester へ引き渡されなかった: {history}")

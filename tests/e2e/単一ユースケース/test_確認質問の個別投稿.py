"""「確認質問の個別投稿」の E2E テスト。

質問件数を決定的に固定するため、複製した Wiki のフェーズページを差し替えて
「確認事項を必ず 3 件投げる」手順をエージェントに読ませる（`broken_phase_page`）。

差し替え先に intake-issue-triager の `分解判定（初回）` を選ぶのは、ユーザーとの往復が
1 往復目で確認質問の投稿に到達し、前段の工程を組み立てずに観測できるため（シナリオ代表の選択理由）。
"""
from __future__ import annotations

import pytest

import re

INTAKE_TITLE = "顧客一覧に絞り込みを追加したい"
INTAKE_BODY = """顧客一覧画面で条件を指定して絞り込めるようにしたいです。

- 会社名・担当者名で絞り込みたい
- 絞り込み条件は URL に残して共有できるようにしたい
"""

PHASE_PAGE = "エージェント/intake-issue-triager/フェーズ/分解判定（初回）.md"

QUESTION_COUNT = 3

# 確認質問をちょうど 3 件投げて待機に入るだけの手順（分解・ラベル付与の分岐を持たせない）
FIXED_QUESTIONS_PHASE = """# 分解判定（初回）

intake Issue の内容から確認事項を 3 件組み立てて投稿し、待機に入る。

## 手順

### 確認質問の投稿

本文を読み、確認したい論点をちょうど 3 件組み立てる。
選択肢は 1 件につき 2 つ以上とし、ラベルの先頭に採番記号を書かない。

MCP `ask_questions` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `intake-issue-triager`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `questions`: 組み立てた 3 件

### 議論中 付与 + 待機

MCP `add_labels` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_IN_DISCUSSION` の値

続けて MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `intake-issue-triager`
- `number`: $issue_number
"""


@pytest.mark.serial
def test_normal(monitor, gh_live, repo_ctx, intake_issue_factory, broken_phase_page, wait_until):
    """質問 3 件が 3 コメントに分かれて投稿されることを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    login = gh_live.rest.users.get_authenticated().parsed_data.login

    # 準備: 確認質問を 3 件投げる手順に差し替え、確認ラベル付きの intake Issue を起票する
    broken_phase_page(PHASE_PAGE, FIXED_QUESTIONS_PHASE)
    issue = intake_issue_factory(title=INTAKE_TITLE, body=INTAKE_BODY)

    # 実行: 分解判定（初回）の完了を待つ（議論中 + assignee=ユーザー の待機状態）
    def _turn_done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=issue.number).parsed_data
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    wait_until(_turn_done, timeout_sec=1200, message="分解判定（初回）の完了（議論中 + assignee）")

    # 検証: 質問件数と同じ数のコメントが投稿されている
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=issue.number
    ).parsed_data
    agent_bodies = [c.body for c in comments if c.body.lstrip().startswith("> from:")]
    assert len(agent_bodies) == QUESTION_COUNT, (
        f"エージェントのコメントが {QUESTION_COUNT} 件ではない: {len(agent_bodies)} 件"
    )

    for body in agent_bodies:
        # 各コメントが質問 1 件だけを含む（質問見出しがちょうど 1 つ）
        headings = re.findall(r"^## .+$", body, re.M)
        assert len(headings) == 1, f"質問見出しが 1 つではない: {headings}"

        # 引用ヘッダー（from / to 行）が付いている
        assert body.lstrip().startswith("> from: @intake-issue-triager"), f"from 行がない: {body[:80]}"
        assert f"> to: @{login}" in body, f"to 行がない: {body[:120]}"

        # 選択肢の採番がそのコメント内で A から振られている
        letters = re.findall(r"^- ([A-Z])\. ", body, re.M)
        assert letters, f"選択肢行がない: {body}"
        assert letters == [chr(ord("A") + i) for i in range(len(letters))], (
            f"選択肢の採番が A から連番になっていない: {letters}"
        )

        # 区切り線で終わっている
        assert body.rstrip().endswith("---"), f"区切り線で終わっていない: {body[-80:]}"

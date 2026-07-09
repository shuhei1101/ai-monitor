"""ai-monitor の gh 操作 MCP サーバー（stdio）。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

mcp = FastMCP("ai-monitor-tools")

sys.path.insert(0, str(SCRIPTS / "gh"))
from github_ops import (  # noqa: E402
    add_labels as _op_add_labels,
    ask_questions as _op_ask_questions,
    close_issue_or_pr as _op_close,
    comment as _op_comment,
    create_child_issue as _op_create_child_issue,
    create_draft_pr as _op_create_draft_pr,
    get_issue as _op_get_issue,
    list_addressed_comments as _op_list_addressed_comments,
    mark_pr_ready as _op_mark_pr_ready,
    merge_pr as _op_merge_pr,
    remove_assignee as _op_remove_assignee,
    remove_labels as _op_remove_labels,
    reply_comment as _op_reply_comment,
    resolve_comments as _op_resolve_comments,
    save_original_body_comment as _op_save_original_body_comment,
    set_assignee as _op_set_assignee,
    transition_phase as _op_transition_phase,
    update_body as _op_update_body,
    update_title as _op_update_title,
)
from models import (  # noqa: E402
    AddressedComment,
    AssigneesResult,
    CommentResult,
    CreatedIssueResult,
    CreatedPRResult,
    EmptyResult,
    IssueSnapshot,
    LabelsResult,
    NodeIdResult,
    Question,
    ResolveResult,
    WorktreeCreateResult,
    WorktreeRemoveResult,
)
from worktree_tool import (  # noqa: E402
    create_worktree as _op_create_worktree,
    remove_worktree as _op_remove_worktree,
)


@mcp.tool(
    title="Issue / PR 情報取得",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def get_issue(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True、Issue の場合 False")],
    title: Annotated[bool, Field(description="title フィールドを取得するか")] = True,
    body: Annotated[bool, Field(description="body フィールドを取得するか")] = True,
    url: Annotated[bool, Field(description="url フィールドを取得するか")] = True,
    state: Annotated[bool, Field(description="state フィールドを取得するか（open / closed）")] = True,
    closed: Annotated[bool, Field(description="closed フィールドを取得するか（bool）")] = True,
    closed_at: Annotated[bool, Field(description="closedAt フィールドを取得するか")] = True,
    created_at: Annotated[bool, Field(description="createdAt フィールドを取得するか")] = True,
    updated_at: Annotated[bool, Field(description="updatedAt フィールドを取得するか")] = True,
    labels: Annotated[bool, Field(description="labels フィールドを取得するか")] = True,
    comments: Annotated[bool, Field(description="comments フィールドを取得するか")] = True,
    assignees: Annotated[bool, Field(description="assignees フィールドを取得するか")] = True,
    author: Annotated[bool, Field(description="author フィールドを取得するか")] = True,
    parent: Annotated[bool, Field(description="parent フィールドを取得するか（Sub-issue リンク）")] = True,
    sub_issues: Annotated[bool, Field(description="subIssues フィールドを取得するか（子 Issue リスト）")] = True,
    sub_issues_summary: Annotated[bool, Field(description="subIssuesSummary フィールドを取得するか")] = True,
) -> IssueSnapshot:
    """Issue / PR の情報を 1 コマンドで取得する。各 bool フラグでフィールドを絞れる（デフォルト全 True）。"""
    return _op_get_issue(
        number, is_pr,
        title=title, body=body, url=url, state=state, closed=closed,
        closed_at=closed_at, created_at=created_at, updated_at=updated_at,
        labels=labels, comments=comments, assignees=assignees, author=author,
        parent=parent, sub_issues=sub_issues, sub_issues_summary=sub_issues_summary,
    )


@mcp.tool(
    title="コメント投稿",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def comment(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True、Issue の場合 False")],
    sender: Annotated[str, Field(description="送信者名（ヘッダーの `@sender` になる。`@` は不要）")],
    receivers: Annotated[list[str], Field(description="宛先名の配列（複数可、`@` は不要）")],
    title: Annotated[str, Field(description="`## タイトル` 部分の 1 行")],
    body: Annotated[str, Field(description="タイトル配下の本文（Markdown 可）")],
) -> CommentResult:
    """Issue / PR に定型フォーマット（🤖 @sender → @receivers + ## title + body）でコメントを投稿する。"""
    return _op_comment(number, is_pr, sender, receivers, title, body)


@mcp.tool(
    title="選択肢付き質問コメント投稿",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def ask_questions(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    sender: Annotated[str, Field(description="送信者名（`@` は不要）")],
    receivers: Annotated[list[str], Field(description="宛先名の配列")],
    title: Annotated[str, Field(description="コメント全体の `## タイトル`")],
    intro: Annotated[str, Field(description="質問リストの前に置く前置き文（空文字なら省略）")],
    questions: Annotated[list[Question], Field(description="質問リスト")],
) -> CommentResult:
    """選択肢 + 推奨マーク付きの確認質問コメントを投稿する。各質問は選択肢 A / B / C ... で提示し、ユーザーは記号で返信する。"""
    return _op_ask_questions(number, is_pr, sender, receivers, title, intro, questions)


@mcp.tool(
    title="コメント返信（追記）",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def reply_comment(
    comment_node_id: Annotated[str, Field(description="追記対象コメントの GraphQL node_id")],
    sender: Annotated[str, Field(description="送信者名")],
    receivers: Annotated[list[str], Field(description="宛先名の配列")],
    title: Annotated[str, Field(description="追記ブロックの `## タイトル`")],
    body: Annotated[str, Field(description="追記ブロックの本文")],
) -> CommentResult:
    """既存コメントに `---` 区切りで定型ブロックを追記する。"""
    return _op_reply_comment(comment_node_id, sender, receivers, title, body)


@mcp.tool(
    title="原文履歴保存コメント",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def save_original_body_comment(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    original_body: Annotated[str, Field(description="残したいオリジナル本文")],
) -> NodeIdResult:
    """原文を「履歴保存」コメントとして投稿し即 Resolve する。issue-triager 用の頻出パターン。"""
    return _op_save_original_body_comment(number, is_pr, original_body)


@mcp.tool(
    title="コメント一括 Resolve",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def resolve_comments(
    node_ids: Annotated[list[str], Field(description="Resolve 対象コメントの node_id 配列（1 件以上）")],
) -> ResolveResult:
    """1 件以上のコメントを一括で Resolve（minimizeComment mutation, classifier=RESOLVED）する。"""
    return _op_resolve_comments(node_ids)


@mcp.tool(
    title="宛先で絞ったコメント一覧",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def list_addressed_comments(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    addressee: Annotated[str, Field(description="宛先名。この名前を receivers に含むコメントだけ返す")],
    include_resolved: Annotated[bool, Field(description="Resolved 済みも含めるか。デフォルト False")] = False,
) -> list[AddressedComment]:
    """宛先が `@addressee` のコメントだけを抽出して返す（先頭ブロックのヘッダーをパース）。"""
    return _op_list_addressed_comments(number, is_pr, addressee, include_resolved)


@mcp.tool(
    title="ラベル追加",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def add_labels(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    labels: Annotated[list[str], Field(description="追加するラベル名の配列（既存ラベルは維持）")],
) -> LabelsResult:
    """ラベルを追加する（冪等）。"""
    return _op_add_labels(number, is_pr, labels)


@mcp.tool(
    title="ラベル除去",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def remove_labels(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    labels: Annotated[list[str], Field(description="除去するラベル名の配列（存在しないラベルは無視）")],
) -> LabelsResult:
    """ラベルを除去する。"""
    return _op_remove_labels(number, is_pr, labels)


@mcp.tool(
    title="フェーズ遷移（ラベル一括入れ替え）",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def transition_phase(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    remove_labels_: Annotated[list[str], Field(description="除去するラベル配列")] = [],  # noqa: B006
    add_labels_: Annotated[list[str], Field(description="追加するラベル配列")] = [],  # noqa: B006
) -> LabelsResult:
    """ラベルを 1 API 呼び出しで一括入れ替え（フェーズ遷移用の複合操作）。"""
    return _op_transition_phase(number, is_pr, remove_labels_, add_labels_)


@mcp.tool(
    title="assignee 設定",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def set_assignee(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    login: Annotated[str | None, Field(description="assignee 対象のログイン名。省略時は現在の認証ユーザー")] = None,
) -> AssigneesResult:
    """assignee を設定する（省略時は現在の GH ログインユーザー）。"""
    return _op_set_assignee(number, is_pr, login)


@mcp.tool(
    title="assignee 除去",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def remove_assignee(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    login: Annotated[str | None, Field(description="除去対象のログイン名。省略時は現在の認証ユーザー")] = None,
) -> AssigneesResult:
    """assignee を除去する。"""
    return _op_remove_assignee(number, is_pr, login)


@mcp.tool(
    title="本文を上書き",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def update_body(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    body: Annotated[str, Field(description="上書き後の本文（既存本文を完全置換）")],
) -> EmptyResult:
    """Issue / PR の本文を上書きする（既存本文を完全置換）。"""
    return _op_update_body(number, is_pr, body)


@mcp.tool(
    title="タイトルを更新",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def update_title(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    title: Annotated[str, Field(description="新しいタイトル")],
) -> EmptyResult:
    """Issue / PR のタイトルを更新する。"""
    return _op_update_title(number, is_pr, title)


@mcp.tool(
    title="Issue / PR クローズ",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def close(
    number: Annotated[int, Field(description="対象の Issue / PR 番号")],
    is_pr: Annotated[bool, Field(description="PR の場合 True")],
    reason: Annotated[Literal["completed", "not_planned", "duplicate"] | None, Field(description="Issue クローズ理由（Issue のみ）")] = None,
    delete_branch: Annotated[bool, Field(description="PR クローズ時にブランチも削除するか（PR のみ）")] = False,
) -> EmptyResult:
    """Issue / PR をクローズする。"""
    return _op_close(number, is_pr, reason, delete_branch)


@mcp.tool(
    title="子 Issue 作成",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def create_child_issue(
    parent_issue_number: Annotated[int, Field(description="親 Issue 番号（親子リンクの参照用、現時点では出力に含めるだけ）")],
    title: Annotated[str, Field(description="子 Issue のタイトル")],
    body: Annotated[str, Field(description="子 Issue の本文")],
    labels: Annotated[list[str], Field(description="子 Issue に付与するラベル配列")] = [],  # noqa: B006
) -> CreatedIssueResult:
    """子 Issue を作成し、GitHub の Sub-issue 機能で親と紐づける（子側から `parent` メタデータで親を辿れる）。"""
    return _op_create_child_issue(parent_issue_number, title, body, labels)


@mcp.tool(
    title="Draft PR 作成",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def create_draft_pr(
    head_branch: Annotated[str, Field(description="head ブランチ名(例: `subsystem/BE`)")],
    base_branch: Annotated[str, Field(description="base ブランチ名(Stacked PR 用、例: `story/A`)")],
    title: Annotated[str, Field(description="PR タイトル")],
    body: Annotated[str, Field(description="PR 本文")],
) -> CreatedPRResult:
    """Draft PR を作成する（Stacked PR の base 明示に対応）。"""
    return _op_create_draft_pr(head_branch, base_branch, title, body)


@mcp.tool(
    title="Draft PR を Ready 化",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def mark_pr_ready(
    pr_number: Annotated[int, Field(description="対象 PR 番号")],
) -> EmptyResult:
    """Draft PR を Ready 化する。"""
    return _op_mark_pr_ready(pr_number)


@mcp.tool(
    title="PR マージ",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def merge_pr(
    pr_number: Annotated[int, Field(description="対象 PR 番号")],
    strategy: Annotated[Literal["squash", "merge", "rebase"] | None, Field(description="マージ戦略（デフォルト squash）")] = None,
) -> EmptyResult:
    """PR をマージする（デフォルト squash + delete branch）。"""
    return _op_merge_pr(pr_number, strategy)


@mcp.tool(
    title="ワークツリー作成",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def worktree_create(
    branch_type: Annotated[Literal["feat", "fix", "docs", "chore", "refactor", "test"], Field(description="ブランチ種別")],
    title: Annotated[str, Field(description="ブランチタイトル（英数字ケバブケース。例: my-feature）")],
) -> WorktreeCreateResult:
    """ブランチ `{type}/{title}` とワークツリー（`.claude/worktrees/` 配下）を作成する。"""
    return _op_create_worktree(branch_type, title)


@mcp.tool(
    title="ワークツリー削除",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def worktree_remove(
    branch: Annotated[str, Field(description="削除対象のブランチ名（例: feat/my-feature）")],
) -> WorktreeRemoveResult:
    """ワークツリーとブランチを両方削除する。"""
    return _op_remove_worktree(branch)


if __name__ == "__main__":
    mcp.run()

"""gh-kit の GitHub 操作関数群で使う DTO 定義。

MCP サーバー / github_ops.py / worktree_tool.py が共通で使う型を集約する。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Choice(BaseModel):
    """ask_questions の 1 個の選択肢。"""

    label: str = Field(description="選択肢の要約ラベル（1〜数語）")
    reason: str = Field(description="この選択肢を選ぶ理由・説明（1 文程度）")


class Question(BaseModel):
    """ask_questions で投稿する 1 個の質問。"""

    question: str = Field(description="質問文")
    background: str = Field(description="質問の背景説明（なぜこの確認が必要か、1〜2 文）")
    choices: list[Choice] = Field(description="選択肢のリスト（A/B/C... と順に対応）")
    recommended_index: int = Field(default=-1, description="推奨する選択肢の 0-indexed（-1 で推奨なし）")
    recommended_reason: str = Field(default="", description="推奨の理由（1 文程度、recommended_index が -1 の場合は空文字）")


class ParsedComment(BaseModel):
    """コメント本文の先頭ブロックをパースした結果。"""

    sender: str = Field(description="送信者名（@ プレフィックスなし）")
    receivers: list[str] = Field(description="宛先名の配列（@ プレフィックスなし）")
    title: str = Field(description="`## タイトル` 部分の 1 行")
    body: str = Field(description="タイトル配下の本文")


class AddressedComment(BaseModel):
    """list_addressed_comments の戻り値要素。"""

    node_id: str = Field(description="GraphQL node_id")
    sender: str = Field(description="送信者名")
    receivers: list[str] = Field(description="宛先名の配列")
    title: str = Field(description="`## タイトル`")
    body: str = Field(description="タイトル配下の本文")
    author: str | None = Field(description="投稿者の GitHub ログイン名（欠落時 None）")
    url: str = Field(description="コメントの html URL")
    is_resolved: bool = Field(description="Resolved 済みか")


class CommentResult(BaseModel):
    """コメント投稿系の戻り値。"""

    node_id: str = Field(description="投稿コメントの GraphQL node_id")
    url: str = Field(description="コメントの html URL")


class NodeIdResult(BaseModel):
    """`save_original_body_comment` の戻り値。"""

    node_id: str = Field(description="投稿コメントの GraphQL node_id")


class ResolveResult(BaseModel):
    """`resolve_comments` の戻り値。"""

    resolved_count: int = Field(description="Resolve した件数")


class LabelsResult(BaseModel):
    """ラベル操作系の戻り値。"""

    current_labels: list[str] = Field(description="操作後のラベル一覧")


class AssigneesResult(BaseModel):
    """assignee 操作系の戻り値。"""

    assignees: list[str] = Field(description="操作後の assignee ログイン名一覧")


class EmptyResult(BaseModel):
    """副作用のみで返り値を持たない関数用の空戻り値。"""


class CreatedIssueResult(BaseModel):
    """`create_child_issue` の戻り値。"""

    issue_number: int = Field(description="作成した Issue 番号")
    url: str = Field(description="Issue の html URL")
    parent_issue_number: int = Field(description="親 Issue 番号（参照用）")


class CreatedPRResult(BaseModel):
    """`create_draft_pr` の戻り値。"""

    pr_number: int = Field(description="作成した PR 番号")
    url: str = Field(description="PR の html URL")


class WorktreeCreateResult(BaseModel):
    """`create_worktree` の戻り値。"""

    branch: str = Field(description="作成したブランチ名")
    worktree_path: str = Field(description="ワークツリーの絶対パス")
    base_ref: str = Field(description="分岐元の base ref（`origin/<current>` or `HEAD`）")


class WorktreeRemoveResult(BaseModel):
    """`remove_worktree` の戻り値。"""

    branch: str = Field(description="削除対象のブランチ名")
    worktree_path: str = Field(description="削除したワークツリーの絶対パス")
    branch_deleted: bool = Field(description="ブランチが削除できたか（未マージ等で失敗した場合 False）")


class Label(BaseModel):
    """gh issue view の labels 要素。"""

    id: str = ""
    name: str
    color: str = ""
    description: str = ""


class UserRef(BaseModel):
    """gh issue view の author / assignees 要素。"""

    id: str = ""
    login: str
    name: str = ""
    is_bot: bool = Field(default=False, alias="is_bot")

    model_config = {"populate_by_name": True}


class IssueRef(BaseModel):
    """他 Issue への参照（parent / subIssues で使う）。"""

    id: str = ""
    number: int
    title: str = ""
    url: str = ""
    state: str = ""


class IssueCommentEntry(BaseModel):
    """gh issue view の comments 要素。"""

    id: str
    body: str
    created_at: str = Field(default="", alias="createdAt")
    author: UserRef | None = None
    url: str = ""
    is_minimized: bool = Field(default=False, alias="isMinimized")

    model_config = {"populate_by_name": True}


class SubIssuesSummary(BaseModel):
    """gh issue view の subIssuesSummary。"""

    total: int = 0
    completed: int = 0
    percent_completed: float = Field(default=0.0, alias="percentCompleted")

    model_config = {"populate_by_name": True}


class IssueSnapshot(BaseModel):
    """`get_issue` の戻り値。指定されなかった / GitHub 側で欠落しているフィールドは None。"""

    number: int | None = None
    title: str | None = None
    body: str | None = None
    url: str | None = None
    state: str | None = None
    closed: bool | None = None
    closed_at: str | None = Field(default=None, alias="closedAt")
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    labels: list[Label] | None = None
    comments: list[IssueCommentEntry] | None = None
    assignees: list[UserRef] | None = None
    author: UserRef | None = None
    parent: IssueRef | None = None
    sub_issues: list[IssueRef] | None = Field(default=None, alias="subIssues")
    sub_issues_summary: SubIssuesSummary | None = Field(default=None, alias="subIssuesSummary")

    model_config = {"populate_by_name": True}

"""MCP ツールの Pydantic DTO 集約。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Choice(BaseModel):
    """質問の選択肢 1 件。"""

    label: str
    reason: str


class Question(BaseModel):
    """ask_questions の質問 1 件。"""

    question: str
    background: str
    choices: list[Choice]
    recommended_index: int = -1
    recommended_reason: str = ""


class CommentBlock(BaseModel):
    """コメント本文の `---` 区切りブロック 1 件のパース結果。"""

    sender: str | None = None
    receiver: str | None = None
    body: str


class AddressedComment(BaseModel):
    """list_addressed_comments が返す自分宛コメント 1 件。"""

    node_id: str
    blocks: list[CommentBlock]
    author: str | None = None
    url: str
    is_resolved: bool = False


class UserRef(BaseModel):
    """ユーザーへの参照。"""

    login: str


class IssueCommentEntry(BaseModel):
    """スナップショット内のコメント 1 件。"""

    id: str
    body: str
    created_at: str | None = None
    author: UserRef | None = None
    url: str | None = None
    is_minimized: bool = False


class ReviewThread(BaseModel):
    """list_review_threads が返すレビュースレッド 1 件。"""

    node_id: str
    path: str
    line: int | None = None
    start_line: int | None = None
    is_resolved: bool = False
    comments: list[IssueCommentEntry] = []


class SearchResultItem(BaseModel):
    """search_issues_and_prs が返す検索結果 1 件。"""

    number: int
    is_pr: bool
    title: str
    state: str
    url: str


class CommentResult(BaseModel):
    """コメント投稿・返信の結果。"""

    node_id: str
    url: str


class ResolveResult(BaseModel):
    """コメント / レビュースレッドの一括 Resolve の結果。"""

    resolved_count: int


class LabelsResult(BaseModel):
    """ラベル追加・除去・フェーズ遷移の結果。"""

    current_labels: list[str]


class AssigneesResult(BaseModel):
    """assignee 設定・除去の結果。"""

    assignees: list[str]


class EmptyResult(BaseModel):
    """副作用のみで返すフィールドを持たないツールの結果。"""


class CreatedIssueResult(BaseModel):
    """子 Issue 作成の結果。"""

    issue_number: int
    url: str
    parent_issue_number: int


class CreatedPRResult(BaseModel):
    """Draft PR 作成の結果。"""

    pr_number: int
    url: str


class WorktreeCreateResult(BaseModel):
    """worktree 作成の結果。"""

    branch: str
    worktree_path: str
    base_ref: str


class WorktreeRemoveResult(BaseModel):
    """worktree 削除の結果。"""

    branch: str
    worktree_path: str


class Label(BaseModel):
    """ラベル 1 件。"""

    name: str
    id: int | None = None
    color: str | None = None
    description: str | None = None


class IssueRef(BaseModel):
    """親・子 Issue への参照。"""

    number: int
    title: str | None = None
    url: str | None = None
    state: Literal["OPEN", "CLOSED", "MERGED"] | None = None


class SubIssuesSummary(BaseModel):
    """子 Issue の集計。"""

    total: int
    completed: int
    percent_completed: float


class IssueSnapshot(BaseModel):
    """get_issue_or_pr が返す Issue / PR のスナップショット。

    取得しなかった / GitHub 側で欠落しているフィールドは None。
    """

    number: int
    title: str | None = None
    body: str | None = None
    url: str | None = None
    state: Literal["OPEN", "CLOSED", "MERGED"] | None = None
    closed: bool | None = None
    closed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    labels: list[Label] | None = []
    comments: list[IssueCommentEntry] | None = []
    assignees: list[UserRef] | None = []
    author: UserRef | None = None
    parent: IssueRef | None = None
    sub_issues: list[IssueRef] | None = []
    sub_issues_summary: SubIssuesSummary | None = None


class MonitorAck(BaseModel):
    """モニター HTTP API の受理結果。"""

    ok: bool

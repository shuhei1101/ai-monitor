"""MCP ツールの Pydantic DTO 集約。"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


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


class CommitEntry(BaseModel):
    """コミット表 1 行分の入力。"""

    commit: str
    summary: str


class PageRangeEntry(BaseModel):
    """ページ範囲表 1 行分の入力。"""

    page: str
    # 単一 commit のときは None（範囲セルが commit 単体になる）
    start_commit: str | None = None
    commit: str


class PlainFormat(BaseModel):
    """本文だけのコメント。"""

    type: Literal["plain"] = "plain"
    body: str


class CommitsFormat(BaseModel):
    """本文 + commit 表のコメント。"""

    type: Literal["commits"] = "commits"
    body: str
    entries: list[CommitEntry]


class PagesFormat(BaseModel):
    """本文 + ページ範囲表のコメント。"""

    type: Literal["pages"] = "pages"
    body: str
    entries: list[PageRangeEntry]


type CommentFormat = Annotated[
    PlainFormat | CommitsFormat | PagesFormat, Field(discriminator="type")
]


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
    # 指摘箇所の周辺 diff（インラインコメントのみ設定される）
    diff_hunk: str | None = None


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


class CreatedLabelResult(BaseModel):
    """ラベル作成の結果。"""

    name: str
    # 本呼び出しで作成したか（既存なら False）
    created: bool


class LabelsResult(BaseModel):
    """ラベル追加・除去・フェーズ遷移の結果。"""

    current_labels: list[str]


class AssigneesResult(BaseModel):
    """assignee 設定・除去の結果。"""

    assignees: list[str]


class EmptyResult(BaseModel):
    """副作用のみで返すフィールドを持たないツールの結果。"""


class CreatedIssueResult(BaseModel):
    """Issue 作成の結果。"""

    issue_number: int
    url: str
    # 親へ Sub-issue リンクした場合のみ入る（intake 起票は親を持たない）
    parent_issue_number: int | None = None


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
    # PR の head / base ブランチ名（Issue は None）。子ブランチの分岐元・Stacked PR の親の特定に使う
    head_ref: str | None = None
    base_ref: str | None = None
    parent: IssueRef | None = None
    sub_issues: list[IssueRef] | None = []
    sub_issues_summary: SubIssuesSummary | None = None


class MonitorAck(BaseModel):
    """モニター HTTP API の受理結果。"""

    ok: bool


class WikiPage(BaseModel):
    """取得した Wiki ページ 1 件。"""

    url: str
    body: str


class WikiPageFailure(BaseModel):
    """取得できなかった Wiki ページ 1 件。"""

    url: str
    reason: str


class WikiPagesResult(BaseModel):
    """read_wiki_pages が返す取得結果。"""

    pages: list[WikiPage]
    failures: list[WikiPageFailure] = []

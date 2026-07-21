"""ai-monitor の GitHub 操作 + モニター連絡 MCP サーバー（stdio）。"""
from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Literal

import yaml
from githubkit import GitHub
from githubkit.exception import RequestFailed
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from models import (
    AddressedComment,
    AssigneesResult,
    CommentBlock,
    CommentResult,
    CreatedIssueResult,
    CreatedPRResult,
    EmptyResult,
    IssueCommentEntry,
    IssueRef,
    IssueSnapshot,
    Label,
    LabelsResult,
    MonitorAck,
    Question,
    ResolveResult,
    ReviewThread,
    SearchResultItem,
    SubIssuesSummary,
    UserRef,
    WorktreeCreateResult,
    WorktreeRemoveResult,
)

SETTINGS_PATH = Path.home() / ".config" / "ai-monitor" / "settings.yaml"

# ユーザー専用ラベル（エージェントからの除去を拒否する）
IN_DISCUSSION_LABEL = "議論中"

# 選択肢の記号（A. B. C. ...）
CHOICE_LETTERS = "ABCDEFGHIJ"

_MINIMIZE_MUTATION = (
    "mutation($id: ID!) { minimizeComment(input: { subjectId: $id, classifier: RESOLVED })"
    " { minimizedComment { isMinimized } } }"
)
_IS_MINIMIZED_QUERY = "query($id: ID!) { node(id: $id) { ... on IssueComment { isMinimized } } }"
_COMMENT_BODY_QUERY = "query($id: ID!) { node(id: $id) { ... on IssueComment { body databaseId } } }"
_MARK_READY_MUTATION = (
    "mutation($id: ID!) { markPullRequestReadyForReview(input: { pullRequestId: $id })"
    " { pullRequest { isDraft } } }"
)
_RESOLVE_THREAD_MUTATION = (
    "mutation($id: ID!) { resolveReviewThread(input: { threadId: $id }) { thread { isResolved } } }"
)
_REVIEW_THREADS_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes { id isResolved path startLine line comments(first: 50) { nodes { id body author { login } createdAt url } } }
      }
    }
  }
}
"""

_client = None

mcp = FastMCP("ai-monitor-tools")

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_DESTRUCTIVE = ToolAnnotations(destructiveHint=True)


# ---- 内部ヘルパー ----


def _get_client() -> GitHub:
    """設定の github_token から githubkit クライアントを生成・共有する。"""
    global _client
    if _client is None:
        # 初回呼び出し時に設定ファイルを読み込む
        settings = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8"))
        # github_token で GitHub クライアントを生成してモジュール内に保持する
        _client = GitHub(settings["github_token"])
    # 2 回目以降は保持済みの同一インスタンスを返す
    return _client


def _get_repo() -> tuple[str, str]:
    """git の remote URL から (owner, repo) を解決する。"""
    # git remote get-url origin で remote URL を取得する
    url = _run_git(["remote", "get-url", "origin"]).stdout.strip()
    # https / ssh の各形式をパースして (owner, repo) を返す
    matched = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if matched is None:
        raise ValueError(f"remote URL を解析できません: {url}")
    return (matched.group(1), matched.group(2))


def _get_current_login() -> str:
    """認証中ユーザーのログイン名を返す。"""
    # 認証中ユーザーを取得し、ログイン名を返す
    return _get_client().rest.users.get_authenticated().parsed_data.login


def _get_labels(number: int) -> list[str]:
    """操作後の現在ラベル名一覧を返す。"""
    owner, repo = _get_repo()
    # 対象を取得し、ラベル名の一覧を返す
    data = _get_client().rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data
    return [label.name for label in data.labels]


def _get_assignees(number: int) -> list[str]:
    """操作後の現在 assignee 一覧を返す。"""
    owner, repo = _get_repo()
    # 対象を取得し、assignee のログイン名一覧を返す
    data = _get_client().rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data
    return [user.login for user in data.assignees]


def _minimize_comment(node_id: str) -> None:
    """GraphQL minimizeComment mutation（classifier=RESOLVED）を実行する。"""
    # minimizeComment mutation（classifier=RESOLVED）を実行する
    _get_client().graphql(_MINIMIZE_MUTATION, {"id": node_id})


def _create_issue_comment(number: int, body: str) -> CommentResult:
    """REST でコメントを投稿し node_id / url を返す。"""
    owner, repo = _get_repo()
    # コメントを投稿する
    resp = _get_client().rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=number, body=body
    ).parsed_data
    # 応答の node_id / url を CommentResult で返す
    return CommentResult(node_id=resp.node_id, url=resp.html_url)


def _parse_comment_blocks(body: str) -> list[CommentBlock]:
    """`---` 区切りブロックの from / to と本文をパースする。"""
    blocks: list[CommentBlock] = []
    # 本文を --- 区切りでブロックに分割する
    for chunk in re.split(r"\n-{3,}\n", body):
        # 各ブロック先頭の > from: / > to: 行を抽出して取り除く
        sender: str | None = None
        receiver: str | None = None
        lines = chunk.strip().splitlines()
        while lines:
            from_match = re.match(r">\s*from:\s*@?(\S+)\s*$", lines[0])
            to_match = re.match(r">\s*to:\s*@?(\S+)\s*$", lines[0])
            if from_match:
                sender = from_match.group(1)
            elif to_match:
                receiver = to_match.group(1)
            else:
                break
            lines.pop(0)
        # 残りを本文とした CommentBlock を投稿順に積む
        blocks.append(CommentBlock(sender=sender, receiver=receiver, body="\n".join(lines).strip()))
    return blocks


def _format_block(sender: str, receiver: str | None, body: str, is_reply: bool = False) -> str:
    """from / to ヘッダー + 本文の定型ブロックを組み立てる。"""
    # > from: 行（receiver があれば > to: 行も）を組み立てる
    header = f"> from: {_ensure_at(sender)}"
    if receiver is not None:
        header += f"\n> to: {_ensure_at(receiver)}"
    # ヘッダーと本文を連結して返す（is_reply=True なら先頭に --- を付ける）
    block = f"{header}\n\n{body}"
    if is_reply:
        block = f"---\n{block}"
    return block


def _ensure_at(name: str) -> str:
    """先頭に @ がなければ付与する。"""
    # 先頭が @ でなければ付与して返す
    return name if name.startswith("@") else f"@{name}"


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    """git CLI 呼び出しの単一入口。"""
    # git を check=True で実行し、CompletedProcess を返す
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True)


def _repo_root() -> Path:
    """共通 .git からメインリポジトリのルートを解決する。"""
    # 共通 .git の場所を取得し、その親をメインリポジトリのルートとして返す
    common = _run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"]).stdout.strip()
    return Path(common).parent


def _worktree_path(branch: str) -> Path:
    """ブランチ名から .claude/worktrees/ 配下の絶対パスを求める。"""
    # メインリポジトリのルートを求める
    root = _repo_root()
    # ブランチ名の / を - に置換した絶対パスを返す
    return root / ".claude" / "worktrees" / branch.replace("/", "-")


def _resolve_base_ref() -> str:
    """origin/{current} or HEAD の分岐元 base ref を返す。"""
    # リモートに現在ブランチと同名のブランチがあるか確認する
    current = _run_git(["branch", "--show-current"]).stdout.strip()
    try:
        _run_git(["rev-parse", "--verify", f"origin/{current}"])
    except subprocess.CalledProcessError:
        # 無い場合、HEAD を返す
        return "HEAD"
    # リモートにある場合、origin/{current} を返す
    return f"origin/{current}"


def _resolve_project() -> str:
    """CWD の git remote から監視対象プロジェクト名を解決する。"""
    # remote URL をパースして settings.yaml の projects から repo 一致の name を返す
    owner, repo = _get_repo()
    slug = f"{owner}/{repo}"
    settings = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8"))
    for project in settings.get("projects", []):
        if project.get("repo") == slug:
            return project["name"]
    # 未登録リポジトリは owner/name をそのまま返す
    return slug


def _load_port() -> int:
    """設定ファイルからモニターの待受ポートを読む。"""
    settings = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8"))
    return settings.get("port", 8765)


def _is_minimized(node_id: str) -> bool:
    """コメントの Resolved（minimize）状態を取得する。"""
    data = _get_client().graphql(_IS_MINIMIZED_QUERY, {"id": node_id})
    return bool(data["node"]["isMinimized"])


# ---- GitHub 操作ツール ----


@mcp.tool(title="Issue・PR情報取得", annotations=_READ_ONLY)
def get_issue_or_pr(
    number: int,
    is_pr: bool,
    title: bool = True,
    body: bool = True,
    url: bool = True,
    state: bool = True,
    closed: bool = True,
    closed_at: bool = True,
    created_at: bool = True,
    updated_at: bool = True,
    labels: bool = True,
    comments: bool = True,
    assignees: bool = True,
    author: bool = True,
    parent: bool = True,
    sub_issues: bool = True,
    sub_issues_summary: bool = True,
) -> IssueSnapshot:
    """Issue / PR の情報を取得してスナップショットに変換する。"""
    client = _get_client()
    owner, repo = _get_repo()

    # REST で Issue / PR の基本情報を取得する（PR は is_pr でエンドポイントを切り替え）
    if is_pr:
        data = client.rest.pulls.get(owner=owner, repo=repo, pull_number=number).parsed_data
    else:
        data = client.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data
    merged = bool(getattr(data, "merged_at", None))
    state_value = "MERGED" if merged else data.state.upper()

    # 取得フラグが True のフィールドを追加取得する
    comments_value = None
    if comments:
        raw_comments = client.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=number
        ).parsed_data
        comments_value = [
            IssueCommentEntry(
                id=c.node_id,
                body=c.body,
                created_at=getattr(c, "created_at", None) and str(c.created_at),
                author=UserRef(login=c.user.login) if getattr(c, "user", None) else None,
                url=c.html_url,
                is_minimized=_is_minimized(c.node_id),
            )
            for c in raw_comments
        ]

    parent_value = None
    if parent and not is_pr:
        try:
            p = client.rest.issues.get_parent(owner=owner, repo=repo, issue_number=number).parsed_data
            parent_value = IssueRef(number=p.number, title=p.title, url=p.html_url, state=p.state.upper())
        except RequestFailed as e:
            # 親リンクなしは 404 で返るため None のままにする
            if e.response.status_code != 404:
                raise

    sub_issues_value = None
    if sub_issues and not is_pr:
        subs = client.rest.issues.list_sub_issues(owner=owner, repo=repo, issue_number=number).parsed_data
        sub_issues_value = [
            IssueRef(number=s.number, title=s.title, url=s.html_url, state=s.state.upper()) for s in subs
        ]

    summary_value = None
    if sub_issues_summary and not is_pr:
        raw_summary = getattr(data, "sub_issues_summary", None)
        if raw_summary is not None:
            summary_value = SubIssuesSummary(
                total=raw_summary.total,
                completed=raw_summary.completed,
                percent_completed=raw_summary.percent_completed,
            )

    # 結果をイシュースナップショットに変換して返す（取得しなかったフィールドは None）
    return IssueSnapshot(
        number=data.number,
        title=data.title if title else None,
        body=data.body if body else None,
        url=data.html_url if url else None,
        state=state_value if state else None,
        closed=(data.state == "closed") if closed else None,
        closed_at=(str(data.closed_at) if data.closed_at else None) if closed_at else None,
        created_at=(str(data.created_at) if data.created_at else None) if created_at else None,
        updated_at=(str(data.updated_at) if data.updated_at else None) if updated_at else None,
        labels=[
            Label(
                name=label.name,
                id=getattr(label, "id", None),
                color=getattr(label, "color", None),
                description=getattr(label, "description", None),
            )
            for label in data.labels
        ]
        if labels
        else None,
        comments=comments_value,
        assignees=[UserRef(login=user.login) for user in data.assignees] if assignees else None,
        author=(UserRef(login=data.user.login) if getattr(data, "user", None) else None) if author else None,
        parent=parent_value,
        sub_issues=sub_issues_value,
        sub_issues_summary=summary_value,
    )


@mcp.tool(title="コメント投稿")
def comment(number: int, is_pr: bool, sender: str, body: str, receiver: str | None = None) -> CommentResult:
    """定型ブロックでコメントを投稿する。"""
    # from / to ヘッダー + 本文を組み立てる
    text = _format_block(sender, receiver, body)
    # 投稿して CommentResult を返す
    return _create_issue_comment(number, text)


@mcp.tool(title="質問投稿")
def ask_questions(
    number: int,
    is_pr: bool,
    sender: str,
    intro: str,
    questions: list[Question],
    receiver: str | None = None,
) -> CommentResult:
    """選択肢 + 推奨付きの質問コメントを投稿する。"""
    # intro と各質問から質問本文を組み立てる（空文字のセクション・推奨なしの推奨行は省略）
    sections: list[str] = []
    if intro:
        sections.append(intro)
    for q in questions:
        part = f"## {q.question}"
        if q.background:
            part += f"\n\n{q.background}"
        choice_lines = [
            f"- {CHOICE_LETTERS[i]}. {choice.label}: {choice.reason}" for i, choice in enumerate(q.choices)
        ]
        part += "\n\n" + "\n".join(choice_lines)
        if q.recommended_index >= 0:
            recommended = f"推奨: {CHOICE_LETTERS[q.recommended_index]}. {q.choices[q.recommended_index].label}"
            if q.recommended_reason:
                recommended += f" — {q.recommended_reason}"
            part += f"\n\n{recommended}"
        sections.append(part)
    # ヘッダーを付ける
    text = _format_block(sender, receiver, "\n\n".join(sections))
    # 投稿して CommentResult を返す
    return _create_issue_comment(number, text)


@mcp.tool(title="コメント返信")
def reply_comment(comment_node_id: str, sender: str, body: str, receiver: str | None = None) -> CommentResult:
    """既存コメントに `---` 区切りで定型ブロックを追記する。"""
    client = _get_client()
    owner, repo = _get_repo()
    # 既存コメントの現在本文を取得する
    node = client.graphql(_COMMENT_BODY_QUERY, {"id": comment_node_id})["node"]
    # --- 区切りの追記ブロックを組み立てる
    block = _format_block(sender, receiver, body, is_reply=True)
    # 既存本文の末尾に連結してコメントを更新し、CommentResult を返す
    resp = client.rest.issues.update_comment(
        owner=owner, repo=repo, comment_id=node["databaseId"], body=f"{node['body']}\n\n{block}"
    ).parsed_data
    return CommentResult(node_id=resp.node_id, url=resp.html_url)


@mcp.tool(title="コメント一括Resolve")
def resolve_comments(node_ids: list[str]) -> ResolveResult:
    """複数コメントの Resolve をまとめて実行する。"""
    # node_ids を 1 件ずつ Resolve する
    for node_id in node_ids:
        _minimize_comment(node_id)
    # 実行件数を ResolveResult で返す
    return ResolveResult(resolved_count=len(node_ids))


@mcp.tool(title="宛先コメント一覧", annotations=_READ_ONLY)
def list_addressed_comments(
    number: int, is_pr: bool, addressee: str, include_resolved: bool = False
) -> list[AddressedComment]:
    """自分宛のコメントだけをブロック配列付きで返す。"""
    client = _get_client()
    owner, repo = _get_repo()
    # コメント一覧と各コメントの isMinimized を取得する
    raw_comments = client.rest.issues.list_comments(owner=owner, repo=repo, issue_number=number).parsed_data
    results: list[AddressedComment] = []
    for c in raw_comments:
        minimized = _is_minimized(c.node_id)
        # 各コメント本文をブロック配列にパースする
        blocks = _parse_comment_blocks(c.body)
        last = blocks[-1]
        # 最後のブロックの to が addressee のもの・to なしのユーザー投稿・from が addressee のもの（自身の投稿）だけに絞る
        is_addressed = (
            last.receiver == addressee
            or (last.receiver is None and last.sender is None)
            or last.sender == addressee
        )
        if not is_addressed:
            continue
        # include_resolved が False なら Resolved 済みを除外する
        if not include_resolved and minimized:
            continue
        results.append(
            AddressedComment(
                node_id=c.node_id,
                blocks=blocks,
                author=c.user.login if getattr(c, "user", None) else None,
                url=c.html_url,
                is_resolved=minimized,
            )
        )
    return results


@mcp.tool(title="Issue・PR検索", annotations=_READ_ONLY)
def search_issues_and_prs(
    query: str,
    sort: Literal[
        "comments",
        "reactions",
        "reactions-+1",
        "reactions--1",
        "reactions-smile",
        "reactions-thinking_face",
        "reactions-heart",
        "reactions-tada",
        "interactions",
        "created",
        "updated",
    ]
    | None = None,
    order: Literal["desc", "asc"] = "desc",
    limit: int = 10,
    page: int = 1,
) -> list[SearchResultItem]:
    """キーワードでリポジトリ内の Issue / PR を横断検索して一覧を返す。"""
    client = _get_client()
    # 対象リポジトリを解決し、検索クエリに repo: を付与する
    owner, repo = _get_repo()
    kwargs: dict = {"q": f"repo:{owner}/{repo} {query}", "per_page": limit, "page": page}
    # 検索 API を sort / order / per_page / page 付きで呼ぶ
    if sort is not None:
        kwargs["sort"] = sort
        kwargs["order"] = order
    data = client.rest.search.issues_and_pull_requests(**kwargs).parsed_data
    # 各要素を SearchResultItem に変換して配列で返す
    return [
        SearchResultItem(
            number=item.number,
            is_pr=getattr(item, "pull_request", None) is not None,
            title=item.title,
            state=item.state,
            url=item.html_url,
        )
        for item in data.items
    ]


@mcp.tool(title="インラインコメント投稿")
def create_review_comment(
    pr_number: int,
    path: str,
    line: int,
    sender: str,
    body: str,
    side: Literal["RIGHT", "LEFT"] = "RIGHT",
    start_line: int | None = None,
    receiver: str | None = None,
) -> CommentResult:
    """PR の特定ファイル・行に紐づくレビューコメントを投稿する。"""
    client = _get_client()
    owner, repo = _get_repo()
    # from / to ヘッダー + 本文を組み立てる
    text = _format_block(sender, receiver, body)
    # PR の head commit SHA を取得する
    sha = client.rest.pulls.get(owner=owner, repo=repo, pull_number=pr_number).parsed_data.head.sha
    # REST でレビューコメントを投稿し、CommentResult を返す（範囲指定時は start_line も指定）
    kwargs: dict = dict(
        owner=owner, repo=repo, pull_number=pr_number, body=text, commit_id=sha, path=path, line=line, side=side
    )
    if start_line is not None:
        kwargs["start_line"] = start_line
    resp = client.rest.pulls.create_review_comment(**kwargs).parsed_data
    return CommentResult(node_id=resp.node_id, url=resp.html_url)


@mcp.tool(title="レビュースレッド一覧", annotations=_READ_ONLY)
def list_review_threads(pr_number: int, include_resolved: bool = False) -> list[ReviewThread]:
    """PR のレビュースレッド一覧を取得する。"""
    client = _get_client()
    owner, repo = _get_repo()
    # GraphQL で PR のレビュースレッド一覧を取得する
    data = client.graphql(_REVIEW_THREADS_QUERY, {"owner": owner, "repo": repo, "number": pr_number})
    nodes = data["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    threads: list[ReviewThread] = []
    for node in nodes:
        # include_resolved が False の場合、解決済みスレッドを除外する
        if not include_resolved and node["isResolved"]:
            continue
        # レビュースレッドの配列に変換して返す
        thread_comments = [
            IssueCommentEntry(
                id=c["id"],
                body=c["body"],
                created_at=c.get("createdAt"),
                author=UserRef(login=c["author"]["login"]) if c.get("author") else None,
                url=c.get("url"),
            )
            for c in node["comments"]["nodes"]
        ]
        threads.append(
            ReviewThread(
                node_id=node["id"],
                path=node["path"],
                line=node["line"],
                start_line=node["startLine"],
                is_resolved=node["isResolved"],
                comments=thread_comments,
            )
        )
    return threads


@mcp.tool(title="レビュースレッド一括Resolve")
def resolve_review_threads(thread_node_ids: list[str]) -> ResolveResult:
    """レビュースレッドを一括で解決する。"""
    client = _get_client()
    # thread_node_ids を 1 件ずつ resolveReviewThread mutation で解決する
    for thread_id in thread_node_ids:
        client.graphql(_RESOLVE_THREAD_MUTATION, {"id": thread_id})
    # 件数を ResolveResult で返す
    return ResolveResult(resolved_count=len(thread_node_ids))


@mcp.tool(title="ラベル追加")
def add_labels(number: int, is_pr: bool, labels: list[str]) -> LabelsResult:
    """ラベルを追加して付与後の一覧を返す。"""
    owner, repo = _get_repo()
    # REST でラベルを追加する
    _get_client().rest.issues.add_labels(owner=owner, repo=repo, issue_number=number, labels=labels)
    # 現在一覧を取り直して LabelsResult で返す
    return LabelsResult(current_labels=_get_labels(number))


@mcp.tool(title="ラベル除去", annotations=_DESTRUCTIVE)
def remove_labels(number: int, is_pr: bool, labels: list[str]) -> LabelsResult:
    """ラベルを除去して除去後の一覧を返す（議論中は対象外）。"""
    # labels に議論中が含まれていれば ValueError を投げる（API は呼ばない）
    if IN_DISCUSSION_LABEL in labels:
        raise ValueError(f"{IN_DISCUSSION_LABEL} ラベルは除去対象外です（外せるのはユーザーのみ）")
    owner, repo = _get_repo()
    client = _get_client()
    # REST でラベルを 1 件ずつ除去する（付与されていないラベルは無視）
    for name in labels:
        try:
            client.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name=name)
        except RequestFailed as e:
            if e.response.status_code != 404:
                raise
    # 現在一覧を取り直して LabelsResult で返す
    return LabelsResult(current_labels=_get_labels(number))


@mcp.tool(title="フェーズ遷移")
def transition_phase(
    number: int,
    is_pr: bool,
    remove_labels_: list[str] | None = None,
    add_labels_: list[str] | None = None,
) -> LabelsResult:
    """ラベルの除去 + 追加を 1 呼び出しで実行する。"""
    # remove_labels_ に議論中が含まれていれば ValueError を投げる（API は呼ばない）
    if remove_labels_ and IN_DISCUSSION_LABEL in remove_labels_:
        raise ValueError(f"{IN_DISCUSSION_LABEL} ラベルは除去対象外です（外せるのはユーザーのみ）")
    owner, repo = _get_repo()
    client = _get_client()
    # remove_labels_ の除去 → add_labels_ の追加の順で実行する
    for name in remove_labels_ or []:
        try:
            client.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name=name)
        except RequestFailed as e:
            if e.response.status_code != 404:
                raise
    if add_labels_:
        client.rest.issues.add_labels(owner=owner, repo=repo, issue_number=number, labels=list(add_labels_))
    # 現在一覧を取り直して LabelsResult で返す
    return LabelsResult(current_labels=_get_labels(number))


@mcp.tool(title="assignee設定")
def set_assignee(number: int, is_pr: bool) -> AssigneesResult:
    """認証ユーザーを assignee に設定して現況を返す。"""
    # 認証ユーザーのログイン名を求める
    login = _get_current_login()
    owner, repo = _get_repo()
    # REST で assignee に追加する
    _get_client().rest.issues.add_assignees(owner=owner, repo=repo, issue_number=number, assignees=[login])
    # 現在一覧を取り直して AssigneesResult で返す
    return AssigneesResult(assignees=_get_assignees(number))


@mcp.tool(title="assignee除去", annotations=_DESTRUCTIVE)
def remove_assignee(number: int, is_pr: bool) -> AssigneesResult:
    """認証ユーザーの assignee を除去して現況を返す。"""
    # 認証ユーザーのログイン名を求める
    login = _get_current_login()
    owner, repo = _get_repo()
    # REST で assignee から除去する
    _get_client().rest.issues.remove_assignees(owner=owner, repo=repo, issue_number=number, assignees=[login])
    # 現在一覧を取り直して AssigneesResult で返す
    return AssigneesResult(assignees=_get_assignees(number))


@mcp.tool(title="本文更新")
def update_body(number: int, is_pr: bool, body: str) -> EmptyResult:
    """本文を完全置換で更新する。"""
    owner, repo = _get_repo()
    # REST の更新で body を完全置換し、EmptyResult を返す
    _get_client().rest.issues.update(owner=owner, repo=repo, issue_number=number, body=body)
    return EmptyResult()


@mcp.tool(title="タイトル更新")
def update_title(number: int, is_pr: bool, title: str) -> EmptyResult:
    """タイトルを更新する。"""
    owner, repo = _get_repo()
    # REST の更新で title を更新し、EmptyResult を返す
    _get_client().rest.issues.update(owner=owner, repo=repo, issue_number=number, title=title)
    return EmptyResult()


@mcp.tool(title="クローズ", annotations=_DESTRUCTIVE)
def close(
    number: int,
    is_pr: bool,
    reason: Literal["completed", "not_planned", "duplicate"] | None = None,
    delete_branch: bool = False,
) -> EmptyResult:
    """Issue / PR をクローズする。"""
    client = _get_client()
    owner, repo = _get_repo()
    # 対象の種類に応じてクローズの更新を実行する
    kwargs: dict = {"state": "closed"}
    if reason is not None:
        kwargs["state_reason"] = reason
    client.rest.issues.update(owner=owner, repo=repo, issue_number=number, **kwargs)
    if is_pr and delete_branch:
        head_ref = client.rest.pulls.get(owner=owner, repo=repo, pull_number=number).parsed_data.head.ref
        client.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{head_ref}")
    # EmptyResult を返す
    return EmptyResult()


@mcp.tool(title="Issue再オープン")
def reopen_issue(number: int) -> EmptyResult:
    """クローズ済み Issue を再オープンする。"""
    owner, repo = _get_repo()
    # REST の更新で state=open + state_reason=reopened にし、EmptyResult を返す
    _get_client().rest.issues.update(
        owner=owner, repo=repo, issue_number=number, state="open", state_reason="reopened"
    )
    return EmptyResult()


@mcp.tool(title="子Issue作成")
def create_child_issue(
    parent_issue_number: int, title: str, body: str, labels: list[str] | None = None
) -> CreatedIssueResult:
    """Sub-issue リンク付きで子 Issue を作成する。"""
    client = _get_client()
    owner, repo = _get_repo()
    # REST でタイトル / 本文 / ラベル付きの Issue を作成する
    created = client.rest.issues.create(
        owner=owner, repo=repo, title=title, body=body, labels=labels or []
    ).parsed_data
    # 作成した Issue の REST ID で親へ Sub-issue リンクを付与する
    client.rest.issues.add_sub_issue(
        owner=owner, repo=repo, issue_number=parent_issue_number, sub_issue_id=created.id
    )
    # CreatedIssueResult を返す
    return CreatedIssueResult(
        issue_number=created.number, url=created.html_url, parent_issue_number=parent_issue_number
    )


@mcp.tool(title="DraftPR作成")
def create_draft_pr(head_branch: str, base_branch: str, title: str, body: str) -> CreatedPRResult:
    """base 明示で Draft PR を作成する。"""
    owner, repo = _get_repo()
    # REST で draft=true・base 明示の PR を作成し、CreatedPRResult を返す
    created = _get_client().rest.pulls.create(
        owner=owner, repo=repo, title=title, body=body, head=head_branch, base=base_branch, draft=True
    ).parsed_data
    return CreatedPRResult(pr_number=created.number, url=created.html_url)


@mcp.tool(title="PR_Ready化")
def mark_pr_ready(pr_number: int) -> EmptyResult:
    """Draft を解除して Ready 状態にする。"""
    client = _get_client()
    owner, repo = _get_repo()
    # PR の GraphQL node_id を取得する
    node_id = client.rest.pulls.get(owner=owner, repo=repo, pull_number=pr_number).parsed_data.node_id
    # markPullRequestReadyForReview mutation を実行し、EmptyResult を返す
    client.graphql(_MARK_READY_MUTATION, {"id": node_id})
    return EmptyResult()


@mcp.tool(title="PRマージ", annotations=_DESTRUCTIVE)
def merge_pr(pr_number: int, strategy: Literal["squash", "merge", "rebase"] | None = None) -> EmptyResult:
    """既定 squash + ブランチ削除で PR をマージする。"""
    client = _get_client()
    owner, repo = _get_repo()
    # strategy（省略時 squash）で REST マージを実行する
    client.rest.pulls.merge(owner=owner, repo=repo, pull_number=pr_number, merge_method=strategy or "squash")
    # head のリモートブランチを削除し、EmptyResult を返す
    head_ref = client.rest.pulls.get(owner=owner, repo=repo, pull_number=pr_number).parsed_data.head.ref
    client.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{head_ref}")
    return EmptyResult()


@mcp.tool(title="worktree作成")
def worktree_create(branch: str) -> WorktreeCreateResult:
    """ブランチと worktree を .claude/worktrees/ 配下に作成し、Draft PR 用の空 commit を push する。"""
    # 分岐元（origin/{current} or HEAD）を求める
    base_ref = _resolve_base_ref()
    # 配置先の worktree パスを求める（.claude/worktrees/ が無ければパスごと作成する）
    path = _worktree_path(branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    # base ref からブランチと worktree を作成する
    _run_git(["worktree", "add", "-b", branch, str(path), base_ref])
    # Draft PR は head と base が同一 commit だと 422 になるため、空 commit を作って push する
    _run_git(["-C", str(path), "commit", "--allow-empty", "-m", "chore: Draft PR 用の空 commit"])
    _run_git(["-C", str(path), "push", "-u", "origin", branch])
    return WorktreeCreateResult(branch=branch, worktree_path=str(path), base_ref=base_ref)


@mcp.tool(title="worktree削除", annotations=_DESTRUCTIVE)
def worktree_remove(branch: str) -> WorktreeRemoveResult:
    """worktree とローカルブランチを削除する。"""
    # 対象の worktree パスを求める
    path = _worktree_path(branch)
    # worktree を削除し、ローカルブランチを強制削除（-D）する
    _run_git(["worktree", "remove", "--force", str(path)])
    _run_git(["branch", "-D", branch])
    # WorktreeRemoveResult を返す
    return WorktreeRemoveResult(branch=branch, worktree_path=str(path))


# ---- モニター連絡ツール ----


@mcp.tool(title="作業完了報告")
def report_completion(agent_name: str, number: int) -> MonitorAck:
    """自ターン終了をモニターの HTTP API へ通知する。"""
    # CWD から project を求める
    project = _resolve_project()
    # agent_name / number / project を JSON にして POST /completions へ送信する
    payload = {"agent_name": agent_name, "number": number, "project": project}
    req = urllib.request.Request(
        f"http://127.0.0.1:{_load_port()}/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # 200 応答を MonitorAck に変換して返す
    with urllib.request.urlopen(req, timeout=5):
        pass
    return MonitorAck(ok=True)


@mcp.tool(title="監視対象追加")
def add_watch_targets(agent_name: str, number: int, watch_numbers: list[int]) -> MonitorAck:
    """作成した派生 PR を自セッションの監視面として台帳に登録する。"""
    # CWD から project を求める
    project = _resolve_project()
    # agent_name / number / watch_numbers / project を JSON にして POST /watch-targets へ送信する
    payload = {"agent_name": agent_name, "number": number, "watch_numbers": watch_numbers, "project": project}
    req = urllib.request.Request(
        f"http://127.0.0.1:{_load_port()}/watch-targets",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # 200 応答を MonitorAck に変換して返す
    with urllib.request.urlopen(req, timeout=5):
        pass
    return MonitorAck(ok=True)


@mcp.tool(title="監視対象除去", annotations=_DESTRUCTIVE)
def remove_watch_targets(agent_name: str, number: int, watch_numbers: list[int]) -> MonitorAck:
    """自セッションの監視面から番号を取り除く。"""
    # CWD から project を求める
    project = _resolve_project()
    # agent_name / number / watch_numbers / project を JSON にして DELETE /watch-targets へ送信する
    payload = {"agent_name": agent_name, "number": number, "watch_numbers": watch_numbers, "project": project}
    req = urllib.request.Request(
        f"http://127.0.0.1:{_load_port()}/watch-targets",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    # 200 応答を MonitorAck に変換して返す
    with urllib.request.urlopen(req, timeout=5):
        pass
    return MonitorAck(ok=True)


if __name__ == "__main__":
    mcp.run()

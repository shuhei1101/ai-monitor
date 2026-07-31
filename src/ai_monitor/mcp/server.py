"""ai-monitor の GitHub 操作 + モニター連絡 MCP サーバー（Streamable HTTP）。"""
from __future__ import annotations

import functools
import inspect
import logging
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from anyio import to_thread
from githubkit import GitHub
from githubkit.exception import RequestFailed
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from ai_monitor.features.agents.types import Agent
from ai_monitor.features.notify.service import build_targets, notify_event, send_notification
from ai_monitor.features.notify.types import SendResult
from ai_monitor.features.sessions.registry import SessionRegistry
from ai_monitor.integrations.github.labels import remove_label
from ai_monitor.mcp.models import (
    AddressedComment,
    AssigneesResult,
    CommentBlock,
    CommentFormat,
    CommentResult,
    CommitsFormat,
    CreatedIssueResult,
    CreatedLabelResult,
    CreatedPRResult,
    EmptyResult,
    IssueCommentEntry,
    IssueRef,
    IssueSnapshot,
    Label,
    LabelsResult,
    MonitorAck,
    PlainFormat,
    Question,
    ResolveResult,
    ReviewThread,
    SearchResultItem,
    SubIssuesSummary,
    UserRef,
    WorktreeCreateResult,
    WorktreeRemoveResult,
)
from ai_monitor.mcp.wiki import read_wiki_pages
from ai_monitor.shared.settings import LabelSettings, MonitoredProject, Settings

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path.home() / ".config" / "ai-monitor" / "settings.yaml"

# 呼び出し元が対象プロジェクトを名乗るリクエストヘッダ
PROJECT_HEADER = "X-Project"


# 選択肢の記号（A. B. C. ...）
CHOICE_LETTERS = "ABCDEFGHIJ"

# 同名ラベルが既に存在するときに GitHub が返すステータス
HTTP_UNPROCESSABLE = 422

# マージ可否の計算完了を待つ試行回数と間隔
MERGEABLE_POLL_ATTEMPTS = 10
MERGEABLE_POLL_INTERVAL_SEC = 2

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
        nodes { id isResolved path startLine line comments(first: 50) { nodes { id body diffHunk author { login } createdAt url } } }
      }
    }
  }
}
"""

_client = None

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_DESTRUCTIVE = ToolAnnotations(destructiveHint=True)


class ProjectNotFoundError(Exception):
    """対象の監視対象プロジェクトを解決できない。"""


class SessionNotFoundError(Exception):
    """セッション台帳に対象セッションが無い。"""


# ---- 内部ヘルパー ----


def _log_tool_call[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """MCP ツールの実行と失敗をログに出すデコレータ。"""
    signature = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # 対象番号を引数から解決する（受け取らないツールは None）
        try:
            number = signature.bind_partial(*args, **kwargs).arguments.get("number")
        except TypeError:
            number = None
        started = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.warning(
                "MCP ツールが失敗しました: tool=%s number=%s", func.__name__, number, exc_info=True
            )
            raise
        logger.info(
            "MCP ツールを実行しました: tool=%s number=%s elapsed_ms=%s",
            func.__name__,
            number,
            int((time.perf_counter() - started) * 1000),
        )
        return result

    return wrapper


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


def _resolve_project(ctx: Context, *, projects: list[MonitoredProject]) -> MonitoredProject:
    """リクエストヘッダ X-Project から対象の監視対象プロジェクトを解決する。"""
    # リクエストコンテキストから X-Project ヘッダを取り出す
    name = ctx.request_context.request.headers.get(PROJECT_HEADER)
    if not name:
        logger.warning("プロジェクト名の指定が無い呼び出しを拒否しました: header=%s", PROJECT_HEADER)
        raise ProjectNotFoundError(f"{PROJECT_HEADER} ヘッダが指定されていません")
    # projects から名前が一致する設定を探す
    for project in projects:
        if project.name == name:
            return project
    logger.warning("未登録のプロジェクト名を拒否しました: project=%s", name)
    raise ProjectNotFoundError(
        f"設定に無いプロジェクト名です: {name}（設定済み: {[p.name for p in projects]}）"
    )


def _bind(tool: Callable[..., Any], **deps: Any) -> Callable[..., Any]:
    """ツール関数に依存を束ね、公開シグネチャからその引数を隠す。"""
    signature = inspect.signature(tool, eval_str=True)
    # そのツールが受け取る依存だけを束ねる
    bound = {name: value for name, value in deps.items() if name in signature.parameters}

    @functools.wraps(tool)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return tool(*args, **kwargs, **bound)

    # MCP はシグネチャから引数スキーマを作るため、束ねた引数を取り除く
    visible = [p for p in signature.parameters.values() if p.name not in bound]
    wrapper.__signature__ = signature.replace(parameters=visible)  # type: ignore[attr-defined]
    return wrapper


def _to_thread(tool: Callable[..., Any]) -> Callable[..., Any]:
    """同期のツール関数をワーカースレッドで実行する非同期関数に包む。"""

    # 受け取った引数のまま tool を呼ぶ包みを定義する（イベントループを塞がないよう別スレッドで走らせる）
    @functools.wraps(tool)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await to_thread.run_sync(functools.partial(tool, *args, **kwargs))

    # 名前・docstring・公開シグネチャは functools.wraps が引き継ぐ（MCP がスキーマ生成に使う）
    return wrapper


def _wait_mergeable(pr_number: int, *, owner: str, repo: str) -> Any:
    """GitHub のマージ可否計算が終わるまで PR を取り直し、確定後のスナップショットを返す。

    GitHub は base 更新のたびに非同期で計算し、確定するまで mergeable に null を返す。
    その状態でマージを投げると 405 になるため、確定を待ってから実行する。
    戻り値が Any なのは、githubkit の PullRequest 型が API バージョン別モジュールにあり、
    型注釈のために特定バージョンへ依存させたくないため。
    """
    client = _get_client()
    for attempt in range(MERGEABLE_POLL_ATTEMPTS):
        # 計算中は間隔を空けて取り直す
        if attempt:
            time.sleep(MERGEABLE_POLL_INTERVAL_SEC)
        pr = client.rest.pulls.get(owner=owner, repo=repo, pull_number=pr_number).parsed_data
        if pr.mergeable is not None:
            return pr
    logger.warning(
        "マージ可否が確定しませんでした: pr_number=%s attempts=%s", pr_number, MERGEABLE_POLL_ATTEMPTS
    )
    return pr


def _get_current_login() -> str:
    """認証中ユーザーのログイン名を返す。"""
    # 認証中ユーザーを取得し、ログイン名を返す
    return _get_client().rest.users.get_authenticated().parsed_data.login


def _get_labels(number: int, *, owner: str, repo: str) -> list[str]:
    """操作後の現在ラベル名一覧を返す。"""
    # 対象を取得し、ラベル名の一覧を返す
    data = _get_client().rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data
    return [label.name for label in data.labels]


def _get_assignees(number: int, *, owner: str, repo: str) -> list[str]:
    """操作後の現在 assignee 一覧を返す。"""
    # 対象を取得し、assignee のログイン名一覧を返す
    data = _get_client().rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data
    return [user.login for user in data.assignees]


def _minimize_comment(node_id: str) -> None:
    """GraphQL minimizeComment mutation（classifier=RESOLVED）を実行する。"""
    # minimizeComment mutation（classifier=RESOLVED）を実行する
    _get_client().graphql(_MINIMIZE_MUTATION, {"id": node_id})


def _create_issue_comment(number: int, body: str, *, owner: str, repo: str) -> CommentResult:
    """REST でコメントを投稿し node_id / url を返す。"""
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
    for chunk in re.split(r"\n-{3,}[ \t]*(?:\n|\Z)", body):
        # 先頭 / 末尾の区切り線で生じる空要素を捨てる（末尾の区切り線の有無でブロック数を変えないため）
        if not chunk.strip():
            continue
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


def _format_block(sender: str, receiver: str | None, body: str, needs_separator: bool = False) -> str:
    """from / to ヘッダー + 本文 + 末尾の区切り線の定型ブロックを組み立てる。"""
    # > from: 行（receiver があれば > to: 行も）を組み立てる
    header = f"> from: {_ensure_at(sender)}"
    if receiver is not None:
        header += f"\n> to: {_ensure_at(receiver)}"
    # ヘッダーと本文を連結する（needs_separator=True なら先頭に --- を付ける）
    block = f"{header}\n\n{body}"
    if needs_separator:
        block = f"---\n{block}"
    # 末尾に区切り線を足して返す（ユーザーが続きに書き足してそのまま次のブロックにできる状態にする）
    return f"{block}\n\n---\n"


def _ends_with_separator(body: str) -> bool:
    """本文の末尾（末尾の空白・改行を除く）が `---` かを返す。"""
    # 末尾の空白・改行を除いた文字列を取り出す
    stripped = body.rstrip()
    if not stripped:
        return False
    # 末尾行が区切り線と一致するかを返す
    return stripped.splitlines()[-1].strip() == "---"


def _render_format(format: CommentFormat) -> str:
    """本文フォーマットから、コメントに載せる本文（表を持つ形式は表も）を組み立てる。"""
    # 表を持たない形式は本文をそのまま返す
    if isinstance(format, PlainFormat):
        return format.body
    # 表を持つ形式は行が 1 件も無いと表にならないので呼び出し側の誤りとして弾く
    if not format.entries:
        raise ValueError("表を持つ format には entries が 1 件以上必要です")
    # type ごとに列見出しと各行のセルを決める
    if isinstance(format, CommitsFormat):
        headers = ("commit", "内容")
        rows = [(f"`{entry.commit}`", entry.summary) for entry in format.entries]
    else:
        headers = ("対象ページ", "commit 範囲")
        rows = [
            # 起点 commit があれば範囲、無ければ単一 commit を範囲セルにする
            (f"`{entry.page}`", f"`{entry.start_commit}..{entry.commit}`" if entry.start_commit else f"`{entry.commit}`")
            for entry in format.entries
        ]
    # 本文 + 空行 + 表 を連結して返す
    table = [f"| {headers[0]} | {headers[1]} |", "| --- | --- |"]
    table += [f"| {left} | {right} |" for left, right in rows]
    return f"{format.body}\n\n" + "\n".join(table) + "\n"


def _ensure_at(name: str) -> str:
    """先頭に @ がなければ付与する。"""
    # 先頭が @ でなければ付与して返す
    return name if name.startswith("@") else f"@{name}"


def _run_git(args: list[str], *, cwd: str) -> subprocess.CompletedProcess[str]:
    """指定リポジトリで git CLI を実行する単一入口。"""
    # MCP は常駐プロセスでプロセスの CWD が対象と一致しないため、-C で対象リポジトリを明示する
    return subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _repo_root(*, cwd: str) -> Path:
    """対象リポジトリの共通 .git からメインリポジトリのルートを解決する。"""
    # 共通 .git の場所を取得し、その親をメインリポジトリのルートとして返す
    common = _run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd).stdout.strip()
    return Path(common).parent


def _worktree_path(branch: str, *, cwd: str) -> Path:
    """ブランチ名から .claude/worktrees/ 配下の絶対パスを求める。"""
    # メインリポジトリのルートを求める
    root = _repo_root(cwd=cwd)
    # ブランチ名の / を - に置換した絶対パスを返す
    return root / ".claude" / "worktrees" / branch.replace("/", "-")


def _branch_exists(branch: str, *, cwd: str) -> bool:
    """指定リポジトリにローカルブランチがあるかを返す。"""
    # 後片付けの判定に使うので、無いこと（非 0 終了）は失敗ではなく結果として扱う
    found = subprocess.run(
        ["git", "-C", cwd, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False, capture_output=True, text=True,
    )
    return found.returncode == 0


def _is_minimized(node_id: str) -> bool:
    """コメントの Resolved（minimize）状態を取得する。"""
    data = _get_client().graphql(_IS_MINIMIZED_QUERY, {"id": node_id})
    return bool(data["node"]["isMinimized"])


# ---- GitHub 操作ツール ----


@_log_tool_call
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
    head_ref: bool = True,
    base_ref: bool = True,
    parent: bool = True,
    sub_issues: bool = True,
    sub_issues_summary: bool = True,
    *,
    ctx: Context,
    settings: Settings,
) -> IssueSnapshot:
    """Issue / PR の情報を取得してスナップショットに変換する。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)

    # REST で Issue / PR の基本情報を取得する（PR は is_pr でエンドポイントを切り替え）
    if is_pr:
        data = client.rest.pulls.get(owner=owner, repo=repo, pull_number=number).parsed_data
    else:
        data = client.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data
    merged = bool(getattr(data, "merged_at", None))
    state_value = "MERGED" if merged else data.state.upper()

    # head / base ブランチ名は PR の応答から取り出す（Issue はブランチを持たないため None）
    head_ref_value = data.head.ref if (head_ref and is_pr) else None
    base_ref_value = data.base.ref if (base_ref and is_pr) else None

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
        head_ref=head_ref_value,
        base_ref=base_ref_value,
        parent=parent_value,
        sub_issues=sub_issues_value,
        sub_issues_summary=summary_value,
    )


@_log_tool_call
def comment(
    number: int,
    is_pr: bool,
    sender: str,
    format: CommentFormat,
    receiver: str | None = None,
    *,
    ctx: Context,
    settings: Settings,
) -> CommentResult:
    """定型ブロックでコメントを投稿する。"""
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # format の type に応じて本文（表を含む場合は表も）を組み立てる
    body = _render_format(format)
    # from / to ヘッダー + 本文を組み立てる
    text = _format_block(sender, receiver, body)
    # 投稿して CommentResult を返す
    return _create_issue_comment(number, text, owner=owner, repo=repo)


@_log_tool_call
def ask_questions(
    number: int,
    is_pr: bool,
    sender: str,
    intro: str,
    questions: list[Question],
    receiver: str | None = None,
    *,
    ctx: Context,
    settings: Settings,
) -> CommentResult:
    """選択肢 + 推奨付きの質問コメントを投稿する。"""
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
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
    return _create_issue_comment(number, text, owner=owner, repo=repo)


@_log_tool_call
def reply_comment(
    comment_node_id: str,
    sender: str,
    format: CommentFormat,
    receiver: str | None = None,
    *,
    ctx: Context,
    settings: Settings,
) -> CommentResult:
    """既存コメントに `---` 区切りで定型ブロックを追記する。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # 既存コメントの現在本文を取得する
    node = client.graphql(_COMMENT_BODY_QUERY, {"id": comment_node_id})["node"]
    # 照会は IssueComment だけを対象にしているため、インライン指摘等は本文のない node が返る
    if not node or "body" not in node:
        raise ValueError(
            f"会話欄のコメントではないため追記できません: {comment_node_id}"
            "（インライン指摘への指摘は create_review_comment で新規投稿する）"
        )
    # format の type に応じて本文（表を含む場合は表も）を組み立てる
    body = _render_format(format)
    # 既存本文が区切り線で終わっていなければ、追記ブロックの先頭に --- を足す
    block = _format_block(
        sender, receiver, body, needs_separator=not _ends_with_separator(node["body"])
    )
    # 既存本文の末尾に連結してコメントを更新し、CommentResult を返す
    resp = client.rest.issues.update_comment(
        owner=owner, repo=repo, comment_id=node["databaseId"], body=f"{node['body']}\n\n{block}"
    ).parsed_data
    return CommentResult(node_id=resp.node_id, url=resp.html_url)


@_log_tool_call
def resolve_comments(node_ids: list[str]) -> ResolveResult:
    """複数コメントの Resolve をまとめて実行する。"""
    # node_ids を 1 件ずつ Resolve する
    for node_id in node_ids:
        _minimize_comment(node_id)
    # 実行件数を ResolveResult で返す
    return ResolveResult(resolved_count=len(node_ids))


@_log_tool_call
def list_addressed_comments(
    number: int,
    is_pr: bool,
    addressee: str,
    include_resolved: bool = False,
    *,
    ctx: Context,
    settings: Settings,
) -> list[AddressedComment]:
    """自分宛のコメントだけをブロック配列付きで返す。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
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


@_log_tool_call
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
    *,
    ctx: Context,
    settings: Settings,
) -> list[SearchResultItem]:
    """キーワードでリポジトリ内の Issue / PR を横断検索して一覧を返す。"""
    client = _get_client()
    # 対象リポジトリを解決し、検索クエリに repo: を付与する
    slug = _resolve_project(ctx, projects=settings.projects).repo
    kwargs: dict = {"q": f"repo:{slug} {query}", "per_page": limit, "page": page}
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


@_log_tool_call
def create_review_comment(
    pr_number: int,
    path: str,
    line: int,
    sender: str,
    body: str,
    side: Literal["RIGHT", "LEFT"] = "RIGHT",
    start_line: int | None = None,
    receiver: str | None = None,
    *,
    ctx: Context,
    settings: Settings,
) -> CommentResult:
    """PR の特定ファイル・行に紐づくレビューコメントを投稿する。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
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


@_log_tool_call
def list_review_threads(
    pr_number: int, include_resolved: bool = False, *, ctx: Context, settings: Settings
) -> list[ReviewThread]:
    """PR のレビュースレッド一覧を取得する。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
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
                diff_hunk=c.get("diffHunk"),
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


@_log_tool_call
def resolve_review_threads(thread_node_ids: list[str]) -> ResolveResult:
    """レビュースレッドを一括で解決する。"""
    client = _get_client()
    # thread_node_ids を 1 件ずつ resolveReviewThread mutation で解決する
    for thread_id in thread_node_ids:
        client.graphql(_RESOLVE_THREAD_MUTATION, {"id": thread_id})
    # 件数を ResolveResult で返す
    return ResolveResult(resolved_count=len(thread_node_ids))


@_log_tool_call
def create_label(
    name: str, color: str, description: str = "", *, ctx: Context, settings: Settings
) -> CreatedLabelResult:
    """リポジトリにラベル定義を作る（同名が既にあれば何もしない）。"""
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # ラベル作成 API を名前・色・説明で呼ぶ
    try:
        _get_client().rest.issues.create_label(
            owner=owner, repo=repo, name=name, color=color, description=description
        )
    except RequestFailed as exc:
        # 同名が既に存在する 422 だけは成功扱いにする（既存の色と説明は変えない）
        if exc.response.status_code != HTTP_UNPROCESSABLE:
            raise
        return CreatedLabelResult(name=name, created=False)
    logger.info("ラベルを作成しました: name=%s", name)
    return CreatedLabelResult(name=name, created=True)


@_log_tool_call
def add_labels(
    number: int, is_pr: bool, labels: list[str], *, ctx: Context, settings: Settings
) -> LabelsResult:
    """ラベルを追加して付与後の一覧を返す。"""
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # REST でラベルを追加する
    _get_client().rest.issues.add_labels(owner=owner, repo=repo, issue_number=number, labels=labels)
    # 現在一覧を取り直して LabelsResult で返す
    return LabelsResult(current_labels=_get_labels(number, owner=owner, repo=repo))


@_log_tool_call
def remove_labels(
    number: int,
    is_pr: bool,
    labels: list[str],
    *,
    ctx: Context,
    settings: Settings,
    label_settings: LabelSettings,
) -> LabelsResult:
    """ラベルを除去して除去後の一覧を返す（議論中は対象外）。"""
    # labels に議論中が含まれていれば ValueError を投げる（API は呼ばない）
    if label_settings.in_discussion in labels:
        raise ValueError(
            f"{label_settings.in_discussion} ラベルは除去対象外です（外せるのはユーザーのみ）"
        )
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    client = _get_client()
    # REST でラベルを 1 件ずつ除去する（付与されていないラベルは無視）
    for name in labels:
        try:
            client.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name=name)
        except RequestFailed as e:
            if e.response.status_code != 404:
                raise
    # 現在一覧を取り直して LabelsResult で返す
    return LabelsResult(current_labels=_get_labels(number, owner=owner, repo=repo))


@_log_tool_call
def transition_phase(
    number: int,
    is_pr: bool,
    remove_labels_: list[str] | None = None,
    add_labels_: list[str] | None = None,
    *,
    ctx: Context,
    settings: Settings,
    label_settings: LabelSettings,
) -> LabelsResult:
    """ラベルの除去 + 追加を 1 呼び出しで実行する。"""
    # remove_labels_ に議論中が含まれていれば ValueError を投げる（API は呼ばない）
    if remove_labels_ and label_settings.in_discussion in remove_labels_:
        raise ValueError(
            f"{label_settings.in_discussion} ラベルは除去対象外です（外せるのはユーザーのみ）"
        )
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
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
    return LabelsResult(current_labels=_get_labels(number, owner=owner, repo=repo))


@_log_tool_call
def set_assignee(number: int, is_pr: bool, *, ctx: Context, settings: Settings) -> AssigneesResult:
    """認証ユーザーを assignee に設定して現況を返す。"""
    # 認証ユーザーのログイン名を求める
    login = _get_current_login()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # REST で assignee に追加する
    _get_client().rest.issues.add_assignees(owner=owner, repo=repo, issue_number=number, assignees=[login])
    # 現在一覧を取り直して AssigneesResult で返す
    return AssigneesResult(assignees=_get_assignees(number, owner=owner, repo=repo))


@_log_tool_call
def remove_assignee(number: int, is_pr: bool, *, ctx: Context, settings: Settings) -> AssigneesResult:
    """認証ユーザーの assignee を除去して現況を返す。"""
    # 認証ユーザーのログイン名を求める
    login = _get_current_login()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # REST で assignee から除去する
    _get_client().rest.issues.remove_assignees(owner=owner, repo=repo, issue_number=number, assignees=[login])
    # 現在一覧を取り直して AssigneesResult で返す
    return AssigneesResult(assignees=_get_assignees(number, owner=owner, repo=repo))


@_log_tool_call
def update_body(number: int, is_pr: bool, body: str, *, ctx: Context, settings: Settings) -> EmptyResult:
    """本文を完全置換で更新する。"""
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # REST の更新で body を完全置換し、EmptyResult を返す
    _get_client().rest.issues.update(owner=owner, repo=repo, issue_number=number, body=body)
    return EmptyResult()


@_log_tool_call
def update_title(number: int, is_pr: bool, title: str, *, ctx: Context, settings: Settings) -> EmptyResult:
    """タイトルを更新する。"""
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # REST の更新で title を更新し、EmptyResult を返す
    _get_client().rest.issues.update(owner=owner, repo=repo, issue_number=number, title=title)
    return EmptyResult()


@_log_tool_call
def close(
    number: int,
    is_pr: bool,
    reason: Literal["completed", "not_planned", "duplicate"] | None = None,
    delete_branch: bool = False,
    *,
    ctx: Context,
    settings: Settings,
) -> EmptyResult:
    """Issue / PR をクローズする。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
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


@_log_tool_call
def reopen_issue(number: int, *, ctx: Context, settings: Settings) -> EmptyResult:
    """クローズ済み Issue を再オープンする。"""
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # REST の更新で state=open + state_reason=reopened にし、EmptyResult を返す
    _get_client().rest.issues.update(
        owner=owner, repo=repo, issue_number=number, state="open", state_reason="reopened"
    )
    return EmptyResult()


@_log_tool_call
def create_child_issue(
    parent_issue_number: int,
    title: str,
    body: str,
    labels: list[str] | None = None,
    *,
    ctx: Context,
    settings: Settings,
) -> CreatedIssueResult:
    """Sub-issue リンク付きで子 Issue を作成する。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
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


def _build_defect_body(
    project_name: str,
    repo: str,
    agent_name: str,
    number: int,
    body: str,
    source_pages: list[str],
    workaround: str | None,
) -> str:
    """不具合 Issue の本文を定型セクションに組み立てる。"""
    # 報告元（どのプロジェクトのどの対象で起きたか）
    sections = [
        "## 報告元\n\n"
        "| 項目 | 値 |\n| --- | --- |\n"
        f"| プロジェクト | {project_name} |\n"
        f"| エージェント | {agent_name} |\n"
        f"| 対象 | {repo}#{number} |"
    ]
    # 該当ページは特定できないことがあるので、空ならセクションごと出さない
    if source_pages:
        listed = "\n".join(f"- `{page}`" for page in source_pages)
        sections.append(f"## 該当ページ\n\n{listed}")
    sections.append(f"## 事象\n\n{body}")
    # 回避策の有無がそのまま「ワークフローが止まっているか」を表す
    if workaround:
        sections.append(f"## 回避策\n\n{workaround}")
    else:
        sections.append("## 回避策\n\nなし（回避できず作業を中断した）")
    return "\n\n".join(sections) + "\n"


@_log_tool_call
def create_defect_issue(
    title: str,
    body: str,
    agent_name: str,
    number: int,
    source_pages: list[str] | None = None,
    workaround: str | None = None,
    *,
    ctx: Context,
    settings: Settings,
    label_settings: LabelSettings,
) -> CreatedIssueResult:
    """ai-monitor 自身のリポジトリへ不具合 Issue を作成する。"""
    # 起票先は呼び出し元セッションのプロジェクトではなく設定で決まる
    if not settings.ai_monitor_repo:
        raise ValueError("不具合 Issue の起票先が未設定です: settings.yaml の ai_monitor_repo を設定してください")
    owner, repo = settings.ai_monitor_repo.split("/", 1)
    project = _resolve_project(ctx, projects=settings.projects)
    # 承認する相手が常にユーザーなので assignee は認証ユーザーで固定する
    login = _get_current_login()
    text = _build_defect_body(
        project.name, project.repo, agent_name, number, body, list(source_pages or []), workaround
    )
    # AI の報告であることを示すラベルだけを付ける
    # （確認ラベルはユーザーが付けるまで付けない = 改修フローに乗せない）
    created = _get_client().rest.issues.create(
        owner=owner,
        repo=repo,
        title=title,
        body=text,
        assignees=[login],
        labels=[label_settings.ai_defect_report],
    ).parsed_data
    logger.warning(
        "不具合が報告されました: project=%s agent_name=%s number=%s issue_number=%s"
        " source_pages=%s workaround=%s",
        project.name,
        agent_name,
        number,
        created.number,
        list(source_pages or []),
        "あり" if workaround else "なし",
    )
    # 承認するまで Issue が動かないので、溜めずにその場で知らせる
    notify_event(
        "defect_report",
        f"不具合が報告されました: {title}",
        f"報告元: {project.name} {project.repo}#{number}（{agent_name}）",
        settings.notifies,
        targets=build_targets(settings.notifies),
        repo=settings.ai_monitor_repo,
        number=created.number,
    )
    return CreatedIssueResult(issue_number=created.number, url=created.html_url)


@_log_tool_call
def create_intake_issue(
    title: str,
    body: str,
    *,
    ctx: Context,
    settings: Settings,
    label_settings: LabelSettings,
) -> CreatedIssueResult:
    """親を持たない intake Issue を作成する。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # REST でタイトル / 本文と固定ラベル付きの Issue を作成する
    # （呼び出し側に選ばせず、レイヤー判定を必ず intake-issue-triager に通す）
    created = client.rest.issues.create(
        owner=owner,
        repo=repo,
        title=title,
        body=body,
        labels=[label_settings.layer_intake, label_settings.confirm_intake_issue_triager],
    ).parsed_data
    # Sub-issue リンクは付けずに CreatedIssueResult を返す
    return CreatedIssueResult(issue_number=created.number, url=created.html_url)


@_log_tool_call
def create_draft_pr(
    head_branch: str, base_branch: str, title: str, body: str, *, ctx: Context, settings: Settings
) -> CreatedPRResult:
    """base 明示で Draft PR を作成する。"""
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # REST で draft=true・base 明示の PR を作成し、CreatedPRResult を返す
    created = _get_client().rest.pulls.create(
        owner=owner, repo=repo, title=title, body=body, head=head_branch, base=base_branch, draft=True
    ).parsed_data
    return CreatedPRResult(pr_number=created.number, url=created.html_url)


@_log_tool_call
def mark_pr_ready(pr_number: int, *, ctx: Context, settings: Settings) -> EmptyResult:
    """Draft を解除して Ready 状態にする。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # PR の GraphQL node_id を取得する
    node_id = client.rest.pulls.get(owner=owner, repo=repo, pull_number=pr_number).parsed_data.node_id
    # markPullRequestReadyForReview mutation を実行し、EmptyResult を返す
    client.graphql(_MARK_READY_MUTATION, {"id": node_id})
    return EmptyResult()


@_log_tool_call
def merge_pr(
    pr_number: int,
    strategy: Literal["squash", "merge", "rebase"] | None = None,
    *,
    ctx: Context,
    settings: Settings,
) -> EmptyResult:
    """既定 squash + ブランチ削除で PR をマージする。"""
    client = _get_client()
    owner, repo = _resolve_project(ctx, projects=settings.projects).repo.split("/", 1)
    # マージ可否の計算が終わるのを待って PR を取得する
    pr = _wait_mergeable(pr_number, owner=owner, repo=repo)
    # strategy（省略時 squash）で REST マージを実行する
    client.rest.pulls.merge(owner=owner, repo=repo, pull_number=pr_number, merge_method=strategy or "squash")
    # head のリモートブランチを削除し、EmptyResult を返す
    client.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{pr.head.ref}")
    return EmptyResult()


@_log_tool_call
def worktree_create(
    branch: str, base_ref: str, *, ctx: Context, settings: Settings
) -> WorktreeCreateResult:
    """ブランチと worktree を .claude/worktrees/ 配下に作成し、Draft PR 用の空 commit を push する。"""
    # 対象プロジェクトを解決する
    project = _resolve_project(ctx, projects=settings.projects)
    # 配置先の worktree パスを求める（.claude/worktrees/ が無ければパスごと作成する）
    path = _worktree_path(branch, cwd=project.local_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # base_ref からブランチと worktree を作成する
    _run_git(["worktree", "add", "-b", branch, str(path), base_ref], cwd=project.local_path)
    # Draft PR は head と base が同一 commit だと 422 になるため、空 commit を作って push する
    _run_git(["commit", "--allow-empty", "-m", "chore: Draft PR 用の空 commit"], cwd=str(path))
    _run_git(["push", "-u", "origin", branch], cwd=str(path))
    return WorktreeCreateResult(branch=branch, worktree_path=str(path), base_ref=base_ref)


@_log_tool_call
def worktree_remove(branch: str, *, ctx: Context, settings: Settings) -> WorktreeRemoveResult:
    """worktree とローカルブランチを削除する。"""
    # 対象プロジェクトを解決する
    project = _resolve_project(ctx, projects=settings.projects)
    # 対象の worktree パスを求める
    path = _worktree_path(branch, cwd=project.local_path)
    # 残っているものだけ消す（worktree を作らずに終わったブランチ・片付け済みのブランチにも呼ばれる）
    if path.exists():
        _run_git(["worktree", "remove", "--force", str(path)], cwd=project.local_path)
    if _branch_exists(branch, cwd=project.local_path):
        _run_git(["branch", "-D", branch], cwd=project.local_path)
    # WorktreeRemoveResult を返す
    return WorktreeRemoveResult(branch=branch, worktree_path=str(path))


# ---- モニター連絡ツール ----


@_log_tool_call
def report_completion(
    agent_name: str,
    number: int,
    *,
    ctx: Context,
    settings: Settings,
    registry: SessionRegistry,
    agents: list[Agent],
) -> MonitorAck:
    """自ターンの終了を通知して処理中ラベルを外し、セッションの生存時刻を更新する。"""
    # 対象プロジェクトを解決する
    project = _resolve_project(ctx, projects=settings.projects)
    # project / agent_name / number でセッションを検索する
    session = registry.find(project.name, agent_name, number)
    if session is None:
        logger.warning(
            "台帳に無いセッションからの完了報告を拒否しました: project=%s agent_name=%s number=%s",
            project.name,
            agent_name,
            number,
        )
        raise SessionNotFoundError(f"台帳にセッションがありません: {project.name}/{agent_name}/{number}")
    # 対象から処理中ラベルを除去する（未付与は無視される冪等操作）
    processing_label = next((a.processing_label for a in agents if a.name == agent_name), None)
    if processing_label is not None:
        remove_label(project, number, processing_label)
    # セッションの生存時刻を更新して受理結果を返す
    registry.touch(session.session_name)
    logger.info(
        "作業完了報告を受信しました: project=%s agent_name=%s number=%s",
        project.name,
        agent_name,
        number,
    )
    return MonitorAck(ok=True)


@_log_tool_call
def add_watch_targets(
    agent_name: str,
    number: int,
    watch_numbers: list[int],
    *,
    ctx: Context,
    settings: Settings,
    registry: SessionRegistry,
) -> MonitorAck:
    """作成した派生 PR の番号を自セッションの監視面として台帳に登録する。"""
    # 対象プロジェクトを解決する
    project = _resolve_project(ctx, projects=settings.projects)
    # 監視面へ番号を追加して受理結果を返す
    try:
        registry.add_watch(project.name, agent_name, number, watch_numbers)
    except KeyError as exc:
        logger.warning(
            "台帳に無いセッションへの監視面追加を拒否しました: project=%s agent_name=%s number=%s",
            project.name,
            agent_name,
            number,
        )
        raise SessionNotFoundError(
            f"台帳にセッションがありません: {project.name}/{agent_name}/{number}"
        ) from exc
    logger.info(
        "監視面へ番号を追加しました: project=%s agent_name=%s number=%s watch_numbers=%s",
        project.name,
        agent_name,
        number,
        watch_numbers,
    )
    return MonitorAck(ok=True)


@_log_tool_call
def remove_watch_targets(
    agent_name: str,
    number: int,
    watch_numbers: list[int],
    *,
    ctx: Context,
    settings: Settings,
    registry: SessionRegistry,
) -> MonitorAck:
    """自セッションの監視面から番号を取り除く。"""
    # 対象プロジェクトを解決する
    project = _resolve_project(ctx, projects=settings.projects)
    # 監視面から番号を取り除いて受理結果を返す
    try:
        registry.remove_watch(project.name, agent_name, number, watch_numbers)
    except KeyError as exc:
        logger.warning(
            "台帳に無いセッションへの監視面除去を拒否しました: project=%s agent_name=%s number=%s",
            project.name,
            agent_name,
            number,
        )
        raise SessionNotFoundError(
            f"台帳にセッションがありません: {project.name}/{agent_name}/{number}"
        ) from exc
    logger.info(
        "監視面から番号を除去しました: project=%s agent_name=%s number=%s watch_numbers=%s",
        project.name,
        agent_name,
        number,
        watch_numbers,
    )
    return MonitorAck(ok=True)


@_log_tool_call
def notify(
    sender: str,
    title: str,
    body: str,
    number: int | None = None,
    *,
    ctx: Context,
    settings: Settings,
) -> SendResult:
    """設定した Webhook（Discord / Slack）へメッセージを送る。"""
    # 対象プロジェクトを解決する（対象へのリンク生成に使う）
    project = _resolve_project(ctx, projects=settings.projects)
    # 有効な送信先を組み立てて全件へ送る（契機の可否はモニター側の判定なので参照しない）
    targets = build_targets(settings.notifies)
    return send_notification(
        sender, title, body, targets=targets, repo=project.repo, number=number,
    )


def build_mcp_app(
    settings: Settings, *, registry: SessionRegistry, agents: list[Agent], label_settings: LabelSettings
) -> Any:
    """全ツールを登録した Streamable HTTP の ASGI アプリを返す。"""
    # MCP サーバーのインスタンスを作る
    mcp = FastMCP("ai-monitor-tools")
    # 全ツールに設定・台帳・エージェント一覧・ラベル設定を束ねて登録する（束ねた引数は公開シグネチャから隠す）
    for tool, title, tool_annotations in (
        (get_issue_or_pr, "Issue・PR情報取得", _READ_ONLY),
        (comment, "コメント投稿", None),
        (ask_questions, "質問投稿", None),
        (reply_comment, "コメント返信", None),
        (resolve_comments, "コメント一括Resolve", None),
        (list_addressed_comments, "宛先コメント一覧", _READ_ONLY),
        (search_issues_and_prs, "Issue・PR検索", _READ_ONLY),
        (_log_tool_call(read_wiki_pages), "Wikiページ取得", _READ_ONLY),
        (create_review_comment, "インラインコメント投稿", None),
        (list_review_threads, "レビュースレッド一覧", _READ_ONLY),
        (resolve_review_threads, "レビュースレッド一括Resolve", None),
        (create_label, "ラベル作成", None),
        (add_labels, "ラベル追加", None),
        (remove_labels, "ラベル除去", _DESTRUCTIVE),
        (transition_phase, "フェーズ遷移", None),
        (set_assignee, "assignee設定", None),
        (remove_assignee, "assignee除去", _DESTRUCTIVE),
        (update_body, "本文更新", None),
        (update_title, "タイトル更新", None),
        (close, "クローズ", _DESTRUCTIVE),
        (reopen_issue, "Issue再オープン", None),
        (create_child_issue, "子Issue作成", None),
        (create_intake_issue, "新規Issue起票", None),
        (create_defect_issue, "不具合Issue起票", None),
        (create_draft_pr, "DraftPR作成", None),
        (mark_pr_ready, "PR_Ready化", None),
        (merge_pr, "PRマージ", _DESTRUCTIVE),
        (worktree_create, "worktree作成", None),
        (worktree_remove, "worktree削除", _DESTRUCTIVE),
        (report_completion, "作業完了報告", None),
        (add_watch_targets, "監視対象追加", None),
        (remove_watch_targets, "監視対象除去", _DESTRUCTIVE),
        (notify, "通知送出", None),
    ):
        # 登録するのはツールそのものではなく、ワーカースレッドで実行する非同期の包み
        mcp.add_tool(
            _to_thread(
                _bind(tool, settings=settings, registry=registry, agents=agents, label_settings=label_settings)
            ),
            title=title,
            annotations=tool_annotations,
        )
    # Streamable HTTP の ASGI アプリを生成して返す
    return mcp.streamable_http_app()

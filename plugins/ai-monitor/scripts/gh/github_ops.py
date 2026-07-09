"""ai-monitor の GitHub 操作関数群

MCP サーバー（mcp/server.py）から直接 import して呼ばれる。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comment_formatter import format_block
from models import (
    AddressedComment,
    AssigneesResult,
    CommentResult,
    CreatedIssueResult,
    CreatedPRResult,
    EmptyResult,
    IssueSnapshot,
    LabelsResult,
    NodeIdResult,
    ParsedComment,
    Question,
    ResolveResult,
)


def _run_gh(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """gh CLI を呼んで CompletedProcess を返す。失敗時は CalledProcessError を投げる。"""
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        input=stdin,
        check=True,
        encoding="utf-8",
    )


def _get_repo() -> str:
    """現在のリポジトリの `owner/name` を返す。"""
    proc = _run_gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
    return proc.stdout.strip()


def _get_current_login() -> str:
    """認証中の GitHub ユーザーのログイン名を返す。"""
    proc = _run_gh(["api", "user", "--jq", ".login"])
    return proc.stdout.strip()


def _issue_or_pr(is_pr: bool) -> str:
    """`gh` のサブコマンド名（`issue` or `pr`）を返す。"""
    return "pr" if is_pr else "issue"


def _get_labels(number: int, is_pr: bool) -> list[str]:
    """Issue / PR の現在のラベル名一覧を返す。"""
    proc = _run_gh([_issue_or_pr(is_pr), "view", str(number), "--json", "labels", "--jq", ".labels[].name"])
    return [line for line in proc.stdout.strip().split("\n") if line]


def _get_assignees(number: int, is_pr: bool) -> list[str]:
    """Issue / PR の現在の assignee ログイン名一覧を返す。"""
    proc = _run_gh([_issue_or_pr(is_pr), "view", str(number), "--json", "assignees", "--jq", ".assignees[].login"])
    return [line for line in proc.stdout.strip().split("\n") if line]


def _minimize_comment(node_id: str) -> None:
    """GraphQL の minimizeComment mutation で 1 コメントを Resolve（classifier=RESOLVED）する。"""
    mutation = (
        "mutation($id: ID!) {"
        " minimizeComment(input: {subjectId: $id, classifier: RESOLVED}) {"
        " minimizedComment { isMinimized } } }"
    )
    _run_gh(["api", "graphql", "-f", f"query={mutation}", "-f", f"id={node_id}"])


def _create_issue_comment(number: int, body: str) -> CommentResult:
    """Issue / PR にコメントを投稿し node_id と html_url を返す。PR も /issues エンドポイント。"""
    proc = _run_gh([
        "api", f"repos/{_get_repo()}/issues/{number}/comments",
        "-X", "POST",
        "-f", f"body={body}",
        "--jq", "{node_id, html_url}",
    ])
    payload = json.loads(proc.stdout)
    return CommentResult(node_id=payload["node_id"], url=payload["html_url"])


_HEADER_RE = re.compile(r"^>\s*🤖\s*@(\S+?),?\s*→\s*(.+)$")
_TITLE_RE = re.compile(r"^##\s+(.+)$")


def _parse_comment_body(body: str) -> ParsedComment | None:
    """コメント本文の先頭ブロックから sender / receivers / title / body を抽出。

    定型フォーマットに一致しなければ None を返す。
    """
    lines = body.split("\n")
    header_idx: int | None = None
    header_match: re.Match[str] | None = None
    for i, line in enumerate(lines):
        m = _HEADER_RE.match(line.strip())
        if m:
            header_idx = i
            header_match = m
            break
    if header_idx is None or header_match is None:
        return None
    sender = header_match.group(1).rstrip(",")
    receivers_raw = header_match.group(2)
    receivers = [tok.strip().lstrip("@").rstrip(",") for tok in receivers_raw.split(",") if tok.strip()]

    title = ""
    title_idx: int | None = None
    for i in range(header_idx + 1, len(lines)):
        m2 = _TITLE_RE.match(lines[i])
        if m2:
            title = m2.group(1).strip()
            title_idx = i
            break

    body_start = (title_idx + 1) if title_idx is not None else (header_idx + 1)
    inner_body = "\n".join(lines[body_start:]).strip()
    return ParsedComment(sender=sender, receivers=receivers, title=title, body=inner_body)


def _extract_url_and_number(stdout: str) -> tuple[str, int]:
    """`gh issue create` / `gh pr create` の出力から URL と番号を抽出する。"""
    url = stdout.strip().split("\n")[-1]
    number = int(url.rsplit("/", 1)[-1])
    return url, number


def get_issue(
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
    """Issue / PR の情報を取得する。各 bool フラグで欲しいフィールドを絞れる（デフォルト全 True）。"""
    field_map = {
        "title": title,
        "body": body,
        "url": url,
        "state": state,
        "closed": closed,
        "closedAt": closed_at,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "labels": labels,
        "comments": comments,
        "assignees": assignees,
        "author": author,
        "parent": parent,
        "subIssues": sub_issues,
        "subIssuesSummary": sub_issues_summary,
    }
    fields = [name for name, enabled in field_map.items() if enabled]
    proc = _run_gh([_issue_or_pr(is_pr), "view", str(number), "--json", ",".join(fields)])
    data = json.loads(proc.stdout)
    return IssueSnapshot.model_validate(data)


def comment(number: int, is_pr: bool, sender: str, receivers: list[str], title: str, body: str) -> CommentResult:
    """Issue / PR に定型フォーマットでコメント投稿。"""
    formatted = format_block(sender, receivers, title, body)
    return _create_issue_comment(number, formatted)


def ask_questions(
    number: int,
    is_pr: bool,
    sender: str,
    receivers: list[str],
    title: str,
    intro: str,
    questions: list[Question],
) -> CommentResult:
    """選択肢 + 推奨付きの確認質問コメントを投稿する。

    各質問は「質問文 / 背景 / 選択肢（理由付き）/ 推奨（記号 + 理由）」の形式で提示され、
    ユーザーは記号で返信する。
    """
    lines: list[str] = []
    if intro:
        lines.append(intro)
        lines.append("")
    for q in questions:
        lines.append(f"## {q.question}")
        lines.append("")
        if q.background:
            lines.append("**背景:**")
            lines.append(q.background)
            lines.append("")
        lines.append("**選択肢:**")
        for j, choice in enumerate(q.choices):
            letter = chr(ord("A") + j)
            lines.append(f"- {letter}. {choice.label}: {choice.reason}")
        lines.append("")
        if 0 <= q.recommended_index < len(q.choices):
            rec_letter = chr(ord("A") + q.recommended_index)
            lines.append(f"**推奨:** {rec_letter}")
            if q.recommended_reason:
                lines.append(q.recommended_reason)
            lines.append("")
    body = "\n".join(lines).rstrip()
    formatted = format_block(sender, receivers, title, body)
    return _create_issue_comment(number, formatted)


def reply_comment(comment_node_id: str, sender: str, receivers: list[str], title: str, body: str) -> CommentResult:
    """既存コメントに `---` 区切りで定型ブロックを追記。"""
    query = (
        "query($id: ID!) { node(id: $id) {"
        " ... on IssueComment { body url }"
        " ... on PullRequestReviewComment { body url } } }"
    )
    proc = _run_gh(["api", "graphql", "-f", f"query={query}", "-f", f"id={comment_node_id}"])
    node = json.loads(proc.stdout)["data"]["node"]
    reply = format_block(sender, receivers, title, body, is_reply=True)
    new_body = node["body"].rstrip() + "\n\n" + reply
    mutation = (
        "mutation($id: ID!, $body: String!) {"
        " updateIssueComment(input: {id: $id, body: $body}) {"
        " issueComment { id url } } }"
    )
    proc = _run_gh([
        "api", "graphql",
        "-f", f"query={mutation}",
        "-f", f"id={comment_node_id}",
        "-f", f"body={new_body}",
    ])
    resp = json.loads(proc.stdout)["data"]["updateIssueComment"]["issueComment"]
    return CommentResult(node_id=resp["id"], url=resp["url"])


def save_original_body_comment(number: int, is_pr: bool, original_body: str) -> NodeIdResult:
    """原文を「履歴保存」コメントとして投稿し即 Resolve。"""
    body = (
        "> 🤖 @issue-triager → 履歴保存\n\n"
        "## ユーザーが最初に書いた本文（整文前の原本）\n\n"
        "<details>\n<summary>展開</summary>\n\n"
        f"{original_body}\n\n"
        "</details>"
    )
    resp = _create_issue_comment(number, body)
    _minimize_comment(resp.node_id)
    return NodeIdResult(node_id=resp.node_id)


def resolve_comments(node_ids: list[str]) -> ResolveResult:
    """複数コメントを一括 Resolve。"""
    for node_id in node_ids:
        _minimize_comment(node_id)
    return ResolveResult(resolved_count=len(node_ids))


def list_addressed_comments(
    number: int,
    is_pr: bool,
    addressee: str,
    include_resolved: bool = False,
) -> list[AddressedComment]:
    """宛先が `@addressee` のコメントだけを返す（先頭ブロックのヘッダーをパース）。"""
    owner, repo_name = _get_repo().split("/", 1)
    query = (
        "query($owner: String!, $repo: String!, $number: Int!) {"
        " repository(owner: $owner, name: $repo) {"
        " issueOrPullRequest(number: $number) {"
        " ... on Issue { comments(first: 100) { nodes { id body url author { login } isMinimized } } }"
        " ... on PullRequest { comments(first: 100) { nodes { id body url author { login } isMinimized } } }"
        " } } }"
    )
    proc = _run_gh([
        "api", "graphql",
        "-f", f"query={query}",
        "-f", f"owner={owner}",
        "-f", f"repo={repo_name}",
        "-F", f"number={number}",
    ])
    payload = json.loads(proc.stdout)
    container = payload["data"]["repository"]["issueOrPullRequest"] or {}
    nodes: list[dict] = container.get("comments", {}).get("nodes", [])
    addressee_normalized = addressee.lstrip("@")
    result: list[AddressedComment] = []
    for n in nodes:
        if not include_resolved and n.get("isMinimized"):
            continue
        parsed = _parse_comment_body(str(n.get("body", "")))
        if parsed is None:
            continue
        if addressee_normalized not in [r.lstrip("@") for r in parsed.receivers]:
            continue
        author_field = n.get("author") or {}
        author_login = author_field.get("login") if isinstance(author_field, dict) else None
        result.append(AddressedComment(
            node_id=n["id"],
            sender=parsed.sender,
            receivers=parsed.receivers,
            title=parsed.title,
            body=parsed.body,
            author=author_login,
            url=n["url"],
            is_resolved=bool(n.get("isMinimized", False)),
        ))
    return result


def add_labels(number: int, is_pr: bool, labels: list[str]) -> LabelsResult:
    """ラベル追加（冪等）。"""
    cmd = [_issue_or_pr(is_pr), "edit", str(number)]
    for lbl in labels:
        cmd += ["--add-label", lbl]
    _run_gh(cmd)
    return LabelsResult(current_labels=_get_labels(number, is_pr))


def remove_labels(number: int, is_pr: bool, labels: list[str]) -> LabelsResult:
    """ラベル除去。"""
    cmd = [_issue_or_pr(is_pr), "edit", str(number)]
    for lbl in labels:
        cmd += ["--remove-label", lbl]
    _run_gh(cmd)
    return LabelsResult(current_labels=_get_labels(number, is_pr))


def transition_phase(
    number: int,
    is_pr: bool,
    remove_labels_: list[str] | None = None,
    add_labels_: list[str] | None = None,
) -> LabelsResult:
    """ラベル一括入れ替え。"""
    cmd = [_issue_or_pr(is_pr), "edit", str(number)]
    for lbl in remove_labels_ or []:
        cmd += ["--remove-label", lbl]
    for lbl in add_labels_ or []:
        cmd += ["--add-label", lbl]
    _run_gh(cmd)
    return LabelsResult(current_labels=_get_labels(number, is_pr))


def set_assignee(number: int, is_pr: bool, login: str | None = None) -> AssigneesResult:
    """assignee 設定。login 省略時は現在の認証ユーザー。"""
    target = login or _get_current_login()
    _run_gh([_issue_or_pr(is_pr), "edit", str(number), "--add-assignee", target])
    return AssigneesResult(assignees=_get_assignees(number, is_pr))


def remove_assignee(number: int, is_pr: bool, login: str | None = None) -> AssigneesResult:
    """assignee 除去。login 省略時は現在の認証ユーザー。"""
    target = login or _get_current_login()
    _run_gh([_issue_or_pr(is_pr), "edit", str(number), "--remove-assignee", target])
    return AssigneesResult(assignees=_get_assignees(number, is_pr))


def update_body(number: int, is_pr: bool, body: str) -> EmptyResult:
    """本文を上書き。"""
    _run_gh([_issue_or_pr(is_pr), "edit", str(number), "--body-file", "-"], stdin=body)
    return EmptyResult()


def update_title(number: int, is_pr: bool, title: str) -> EmptyResult:
    """タイトルを更新。"""
    _run_gh([_issue_or_pr(is_pr), "edit", str(number), "--title", title])
    return EmptyResult()


def close_issue_or_pr(
    number: int,
    is_pr: bool,
    reason: str | None = None,
    delete_branch: bool = False,
) -> EmptyResult:
    """Issue / PR クローズ。"""
    cmd = [_issue_or_pr(is_pr), "close", str(number)]
    if reason and not is_pr:
        cmd += ["--reason", reason]
    if delete_branch and is_pr:
        cmd += ["--delete-branch"]
    _run_gh(cmd)
    return EmptyResult()


def create_child_issue(
    parent_issue_number: int,
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> CreatedIssueResult:
    """子 Issue を作成し、GitHub の Sub-issue 機能で親と紐づける。

    紐づけは REST API `POST /repos/{owner}/{repo}/issues/{parent}/sub_issues` を使う。
    子側からは `gh issue view --json parent` で親 Issue 番号を取得できる。
    """
    cmd = ["issue", "create", "--title", title, "--body", body]
    for lbl in labels or []:
        cmd += ["--label", lbl]
    proc = _run_gh(cmd)
    url, number = _extract_url_and_number(proc.stdout)

    # Sub-issue リンクを張る（GitHub Issue の親子メタデータとして記録される）
    repo = _get_repo()
    child_rest_id = int(_run_gh([
        "api", f"repos/{repo}/issues/{number}", "--jq", ".id",
    ]).stdout.strip())
    _run_gh([
        "api", f"repos/{repo}/issues/{parent_issue_number}/sub_issues",
        "-X", "POST",
        "-F", f"sub_issue_id={child_rest_id}",
    ])

    return CreatedIssueResult(issue_number=number, url=url, parent_issue_number=parent_issue_number)


def create_draft_pr(head_branch: str, base_branch: str, title: str, body: str) -> CreatedPRResult:
    """Draft PR を作成。"""
    proc = _run_gh([
        "pr", "create", "--draft",
        "--base", base_branch,
        "--head", head_branch,
        "--title", title,
        "--body", body,
    ])
    url, number = _extract_url_and_number(proc.stdout)
    return CreatedPRResult(pr_number=number, url=url)


def mark_pr_ready(pr_number: int) -> EmptyResult:
    """Draft → Ready 化。"""
    _run_gh(["pr", "ready", str(pr_number)])
    return EmptyResult()


def merge_pr(pr_number: int, strategy: str | None = None) -> EmptyResult:
    """PR マージ（デフォルト squash + delete branch）。"""
    strategy_flag = {"squash": "--squash", "merge": "--merge", "rebase": "--rebase"}[strategy or "squash"]
    _run_gh(["pr", "merge", str(pr_number), strategy_flag, "--delete-branch"])
    return EmptyResult()

"""gh-kit のコメント定型フォーマット組み立てモジュール。

github_ops.py の comment / reply_comment / save_original_body_comment から呼ばれる内部モジュール。
規約: docs/wiki/規約/コメント.md
"""
from __future__ import annotations

from collections.abc import Sequence


def format_block(
    sender: str,
    receivers: Sequence[str],
    title: str,
    body: str,
    is_reply: bool = False,
) -> str:
    """定型コメントブロックを 1 個組み立てる。

    フォーマット:
        > 🤖 @{sender} → @{receiver_1}, @{receiver_2}, ...
        <空行>
        ## {title}
        <空行>
        {body}

    is_reply=True の場合、先頭に `---\\n\\n` の区切りを付与する（既存コメントへの追記用）。
    """
    receiver_tokens = ", ".join(_ensure_at(r) for r in receivers)
    sender_token = _ensure_at(sender)
    header = f"> 🤖 {sender_token} → {receiver_tokens}"

    lines: list[str] = []
    if is_reply:
        lines.append("---")
        lines.append("")
    lines.append(header)
    lines.append("")
    lines.append(f"## {title}")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


def _ensure_at(name: str) -> str:
    """先頭に `@` が無ければ付与する。既に付いていればそのまま返す。"""
    return name if name.startswith("@") else f"@{name}"

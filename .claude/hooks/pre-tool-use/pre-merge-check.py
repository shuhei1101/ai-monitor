"""workspace / pre-merge-check — PreToolUse(Bash) hook.

`git merge <branch>` 検出時に2段階の事前チェックを行う。

チェック1（master取り込み確認）: masterが対象ブランチの祖先かを確認。
  否 → ブロック（先にmasterを取り込むよう案内）

チェック2（dry-runマージ）: コンフリクト有無を事前確認。
  コンフリクトあり → git merge --abort してブロック
  コンフリクトなし → git merge --abort して通過

適用除外: `git merge master/main`（上流取り込み）
env: WORK_GUARD=false/0/no/off で無効化可能
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# master/main への上流取り込みは安全なのでチェック不要
_SAFE_MERGE = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?merge\s+(?:--\S+\s+)*(?:origin/)?(master|main)\b"
)
# -C <path> オプションとブランチ名を抽出
_MERGE_CMD = re.compile(
    r"\bgit(?:\s+-C\s+(\S+))?\s+merge\s+(?:--\S+\s+)*([^\s-]\S*)"
)


def _extract_merge_info(command: str) -> tuple[str | None, str | None]:
    """コマンド文字列からgit作業ディレクトリとマージ対象ブランチを抽出する。"""
    m = _MERGE_CMD.search(command)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _build_git_args(git_dir: str | None) -> list[str]:
    """git_dirからgitコマンドの引数リストを組み立てる。"""
    if git_dir:
        resolved = os.path.normpath(os.path.join(os.getcwd(), git_dir))
        return ["git", "-C", resolved]
    return ["git"]


def _block(reason: str) -> None:
    """ブロックレスポンスをstdoutに出力する。"""
    sys.stdout.buffer.write(
        json.dumps({"decision": "block", "additionalContext": reason}, ensure_ascii=False).encode("utf-8")
    )


def main() -> None:
    """pre-mergeチェックのエントリポイント。"""
    if os.environ.get("WORK_GUARD", "true").lower() in ("false", "0", "no", "off"):
        return

    payload = json.loads(sys.stdin.read())
    command = payload.get("tool_input", {}).get("command", "")

    # git merge を含まないコマンドはスキップ
    if not re.search(r"\bgit\s+(?:-C\s+\S+\s+)?merge\b", command):
        return

    # master/main への上流取り込みはチェック不要
    if _SAFE_MERGE.search(command):
        return

    git_dir, branch = _extract_merge_info(command)
    if not branch:
        return

    git_args = _build_git_args(git_dir)

    # masterがブランチの祖先かを確認（masterを取り込み済みかどうか）
    # returncode=0 → masterはbranchの祖先（取り込み済み）
    ancestor_check = subprocess.run(
        git_args + ["merge-base", "--is-ancestor", "master", branch],
        capture_output=True,
    )
    if ancestor_check.returncode != 0:
        _block(
            f"`{branch}` は `master` の最新内容を取り込んでいません。\n"
            "先に以下を実行してから再度マージしてください:\n\n"
            f"```bash\ngit -C <worktree> merge master\n```"
        )
        return

    # dry-runマージでコンフリクト有無を確認
    dry_run = subprocess.run(
        git_args + ["merge", "--no-commit", "--no-ff", branch],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    # dry-run後は常にabort（成功・失敗問わずMERGE_HEADが残るため）
    subprocess.run(git_args + ["merge", "--abort"], capture_output=True)

    if dry_run.returncode != 0:
        conflict_info = dry_run.stdout.strip() or dry_run.stderr.strip()
        _block(
            f"`{branch}` とのマージでコンフリクトが発生します。\n\n"
            f"コンフリクト詳細:\n```\n{conflict_info}\n```\n\n"
            "コンフリクトを解消してから再度マージしてください。"
        )


if __name__ == "__main__":
    main()

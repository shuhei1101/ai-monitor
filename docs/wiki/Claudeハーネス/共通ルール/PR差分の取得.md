# PR差分の取得

PR の差分は、対象ブランチの worktree で git を実行して読む。

## 取得手順

MCP `get_issue_or_pr` の戻り値から `base_ref` / `head_ref` を取り、worktree（`.claude/worktrees/{head_ref の / を - に置換}`）へ移動する。

```bash
git fetch origin
git diff --stat origin/{base_ref}...HEAD              # 変更ファイルと増減行数
git diff origin/{base_ref}...HEAD -- {ファイルパス}    # 対象ファイルの差分
```

- 3 点ドット（`...`）で取る。GitHub の PR 差分と同じ merge-base 起点になり、`create_review_comment` の `line` がそのまま通る（2 点差分で取った行番号を渡すと 422 になる）
- 先に `--stat` で全体像を見て、読む必要があるファイルだけ本文を取る
- 特定の commit 以降だけを見る場合は `git diff {commit}..HEAD` で起点を差し替える（commit ID の出所は共通ルール『コミット報告』）

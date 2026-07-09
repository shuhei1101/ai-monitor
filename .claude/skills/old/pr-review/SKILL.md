---
name: gh-kit:pr-review
description: 1 件の PR をレビューし、合格かつ assignees がなければユーザーへの確認コメントを投稿する（確認:pr-merger ラベルはユーザーが手動付与）
---

# pr-review

PR を 1 件レビューし、合格時はユーザーへの確認コメントを投稿する。
`確認:pr-merger` ラベルはユーザーが手動で付与する（AI による自動付与は禁止）。
マージ責務は持たない（`pr-merge` スキルが実行する）。

## 入力

| 引数 | 内容 |
| --- | --- |
| PR 番号 | 例: 42 |
| ベースブランチ | 例: `master` |
| ヘッドブランチ | 例: `feat/foo-bar` |
| リポジトリ root | メインリポジトリの絶対パス |
| 現在 assignees 一覧 | assignees の有無を判定するのに使う |

## ステップ 0: Wiki チェックリストを読み込む

`GH_KIT_CHECKLIST_PAGES` が設定されている場合に限り、指定されたチェックリストページをリモート Wiki から取得してコンテキストに注入する。
ページが存在しない場合は警告を出力して続行する。

```bash
REPO_SLUG=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
IFS=',' read -ra PAGES <<< "${GH_KIT_CHECKLIST_PAGES:-共通チェックリスト}"
for PAGE in "${PAGES[@]}"; do
  PAGE=$(echo "$PAGE" | xargs)  # trim whitespace
  CONTENT=$(curl -fsSL "https://raw.githubusercontent.com/wiki/${REPO_SLUG}/${PAGE}.md" 2>/dev/null)
  if [ -n "$CONTENT" ]; then
    echo "# Wiki チェックリスト: $PAGE"
    echo "$CONTENT"
  else
    echo "[INFO] Wiki チェックリストページが見つかりません: ${PAGE}.md" >&2
  fi
done
```

取得できたチェックリスト内容は、ステップ 3 のレビューで確認項目として観点メニューと合わせて参照する。

## ステップ 1: 観点メニューを取得

```bash
curl -fsSL "https://raw.githubusercontent.com/wiki/$(gh repo view --json nameWithOwner --jq '.nameWithOwner')/観点メニュー.md"
```

ステップ 3 で参照する。

## ステップ 2: PR 情報を取得

```bash
gh pr view {N} --json number,title,body,headRefName,baseRefName,labels,assignees,statusCheckRollup,comments,reviews,isDraft
gh pr diff {N} > /tmp/pr-{N}.diff
```

CI が failure なら `failed` で返して停止。

## ステップ 2.5: PR 本文チェックリスト未消化チェック（最優先）

**このチェックは他のすべての verdict より優先される。**

ステップ 2 で取得した PR 本文を対象に、未消化チェックリスト（`- [ ]`）が 1 件以上残っていないか確認する。

```bash
# PR 本文の未消化チェックリスト数を確認（行頭の実チェックボックスのみ。インラインコード内の `- [ ]` は除外）
UNCHECKED=$(gh pr view {N} --json body --jq '.body' | python3 -c "
import sys, re
body = sys.stdin.read()
print(len(re.findall(r'^[ \t]*[-*] \[ \]', body, re.MULTILINE)))
")
echo "未消化チェックリスト数: $UNCHECKED"
```

| 条件 | 動作 |
| --- | --- |
| `- [ ]` の件数 >= 1 | **即座に `$GH_KIT_LABEL_CONFIRM_PR_IMPLEMENT` ラベルを付与して差し戻し（ステップ 7-A へスキップ）** |
| `- [ ]` の件数 == 0 | ステップ 3 以降に進む |

`- [ ]` が残っている場合は以下を実行して処理を終了する:

```bash
# 確認:pr-implementer ラベルを付与（$GH_KIT_LABEL_CONFIRM_PR_IMPLEMENT）
gh pr edit {N} --add-label "$GH_KIT_LABEL_CONFIRM_PR_IMPLEMENT"

# 差し戻しコメントを投稿
gh pr comment {N} --body "$(cat <<'EOF'
## レビュー差し戻し: PR 本文にチェックリスト未消化が残っています

PR 本文に `- [ ]` が残っているため、レビューを開始できません。

**対応手順:**
1. `pr-implement` スキルのステップ 7.5 に従い、実装済みタスクを `- [x]` に更新してください
2. 未実装タスクが残る場合は、その理由を PR コメントに記載してください
3. 全チェックが完了したら再度 Ready にしてください
EOF
)"
```

verdict = `needs-fix`（`確認:pr-implementer` ラベル付与 + changes-requested 相当の差し戻し扱い）でスキルを終了する。

## ステップ 2.6: Issue 照合チェック（スキップ禁止）

**このチェックはステップ 3 のコードレビューと独立して必ず実行する。**

PR 本文から紐づく Issue を特定し、「実装内容が Issue で定義した問題を解決しているか」を確認する。

```bash
# PR 本文から Issue 番号を抽出
ISSUE_N=$(gh pr view {N} --json body --jq '.body' | grep -oP '(?:Refs|Closes|Fixes) #\K[0-9]+' | head -1)
if [ -z "$ISSUE_N" ]; then
  echo "[WARN] PR 本文から Issue 番号を抽出できませんでした。Issue 照合チェックをスキップします。" >&2
else
  gh issue view "$ISSUE_N" --json number,title,body,comments
fi
```

Issue が取得できた場合、以下の観点で照合する:

| 観点 | 確認内容 |
| --- | --- |
| 問題解決 | Issue で定義された問題・課題が、この PR の変更によって解決されているか |
| スコープ過不足 | Issue のスコープが過不足なく実装されているか（漏れ・余分な変更がないか） |
| issue-reviewer 方針反映 | issue-reviewer が確定した採用方針・QA 回答が実装に反映されているか |

Issue 照合チェックの finding は severity = `major` 以上として扱い、ステップ 4 の finding に含める。
Issue が取得できない場合はチェックをスキップし、レビューコメントに「Issue 照合チェック: スキップ（Issue 番号未取得）」と記載する。

## ステップ 3: ファイル走査とルール注入

変更ファイルを Read で読む。Read 時に PreToolUse フックがファイル系ルールを自動注入する — これが第一審査基準。
ステップ 1 で取得した観点メニューと組み合わせて変更 diff を審査する。

注入ルール由来の finding は body 冒頭に「ルール: {名}」を明記する。

## ステップ 4: findings を作成

各 finding の構造:

| フィールド | 内容 |
| --- | --- |
| `path` | ファイルパス |
| `line` | 行番号 |
| `side` | `RIGHT` / `LEFT` |
| `severity` | `blocker` / `critical` / `major` / `minor` / `nit` |
| `body` | コメント本文（Markdown）— なぜ問題か + 提案を 2〜4 行 |

## ステップ 5: gh CLI でレビュー投稿

```bash
gh pr review {N} \
  --approve|--comment|--request-changes \
  --body-file <(cat <<'EOF'
{観点別サマリ}
EOF
)
# inline コメントが必要なら gh api repos/:owner/:repo/pulls/{N}/comments を使う
```

event 判定（優先度順）:

| 優先度 | 条件 | event | verdict | 次の動作 |
| --- | --- | --- | --- | --- |
| 1（最優先） | PR 本文に `- [ ]` が 1 件以上残っている | ステップ 2.5 で処理済み | `needs-fix`（`確認:pr-implementer`（`$GH_KIT_LABEL_CONFIRM_PR_IMPLEMENT`）ラベル付与） | ステップ 7-A へスキップ（ここには到達しない） |
| 2 | blocker / critical / major を含む | `--request-changes` | `changes-requested` | ステップ 7-A（ラベルなし） |
| 3 | minor / nit のみ + assignees なし | `--approve` | `approved-pending-user-merge` | ステップ 7-D（ユーザーへの説明コメント投稿、ラベル付与なし） |
| 4 | minor / nit のみ + assignees あり | `--approve` | `approved-user-review-pending` | ステップ 7-B（ラベルなし） |

## ステップ 7-A: changes-requested

マージしない。verdict = `changes-requested`、message に主要 finding を要約。

## ステップ 7-B: approved-user-review-pending

マージしない。verdict = `approved-user-review-pending`、message に「ユーザー確認待ち（assignees 設定済み）」と理由。

ユーザーが内容を確認したら、以下の操作をすることでマージフローへ進む:
1. PR に `確認:pr-merger` ラベルを手動で付与する
2. assignees を外す（自身を remove する）

`pr-merger-auto` は `確認:pr-merger` ラベル付きの PR（assignees なし）を検知したとき、マージを実行する。

## ステップ 7-D: approved-pending-user-merge

**AI による `確認:pr-merger` ラベル付与は禁止。ラベルはユーザーが手動で付与する。**

以下のコメントを投稿し、ユーザーに手動で `確認:pr-merger` を付与してもらうよう案内する:

```bash
gh pr comment {PR_NUMBER} --body "$(cat <<'EOF'
## レビュー承認済み — マージにはユーザー確認が必要です

このPRはレビューを通過しました。

マージを実行する場合は、以下の手順で進めてください:

1. PR の内容を確認する
2. 問題なければ `確認:pr-merger` ラベルを手動で付与する
3. `pr-merger-auto` が自動的にマージを実行します

**AI は `確認:pr-merger` ラベルを自動付与しません（誤マージ防止のため）。**
EOF
)"
```

| 状況 | verdict |
| --- | --- |
| コメント投稿成功 | `approved-pending-user-merge` |
| その他失敗 | `failed` |

## ステップ 7-C: Drop（PR Close without merge）

PR を `--close` した場合（failed / conflict）も `processing:*` ラベルを除去する（Issue は Close しない）。

```bash
ISSUE_N=$(gh pr view {PR_NUMBER} --json body --jq '.body' | grep -oP '(?:Refs|Closes|Fixes) #\K[0-9]+' | head -1)
if [ -n "$ISSUE_N" ]; then
  gh issue edit "$ISSUE_N" \
    --remove-label "$GH_KIT_LABEL_PROCESSING_PR_PLANNER" \
    --remove-label "$GH_KIT_LABEL_PROCESSING_PR_IMPLEMENTER" \
    --remove-label "$GH_KIT_LABEL_PROCESSING_PR_REVIEWER"
fi
```

## 制約

| No | 禁止 |
| --- | --- |
| 1 | 自身の中でサブエージェントを起動しない |
| 2 | `git push --force` を使わない |
| 3 | assignees が設定されている PR を AI 単独でマージしない |
| 4 | 変更行から離れた箇所に inline コメントを付けない |

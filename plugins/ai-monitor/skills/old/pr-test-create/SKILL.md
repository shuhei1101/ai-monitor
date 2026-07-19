---
name: ai-monitor:pr-test-create
description: "PR のテスト計画を立案し、テストコードを作成する。dev-kit のテスト仕様書を第一参照し、プロジェクト既存テストを補助参照して方式を決定する。pr-test-creator エージェントから呼ばれる。"
---

# pr-test-create

PR に紐づく Issue の内容を読み、テスト計画を立案してテストコードを作成する。
実装コードの変更は行わない — 実装は `/ai-monitor:pr-implement` が担当。

## 入力

| 引数 | 必須 | 内容 |
| --- | --- | --- |
| PR 番号 | 必須 | 例: 42 |
| branch | 必須 | 例: `feat/issue-42-router` |
| base ブランチ | 必須 | 通常 `master` |
| Issue 番号 | 必須 | 紐づく Issue 番号 |
| 採用方針 | 必須 | Issue コメントの `issue-reviewer` 結果から抽出 |
| 分割スコープ | 任意 | この PR で扱うスコープ（1 Issue 複数 PR 時） |

## ステップ 1: ワークツリー復帰 + remote 同期

```bash
WT=".claude/worktrees/$(echo {branch} | tr '/' '-')"
if [ ! -d "$WT" ]; then
  echo "worktree missing, please call ai-monitor-tools worktree_create MCP for branch={branch}" >&2
  exit 1
fi
git -C "$WT" fetch origin
git -C "$WT" reset --hard origin/{branch}
```

## ステップ 2: テスト方式を決定する

以下の優先順位でテスト方式を確認する。

### 2-1. dev-kit テスト仕様書を第一参照

プロジェクトの言語・フレームワークに対応する `dev-kit` のテストルールを読む。

```bash
# 例: Python プロジェクトの場合
cat "${CLAUDE_PLUGIN_ROOT}/../dev-kit/rules/python/testing/テスト戦略.md"
cat "${CLAUDE_PLUGIN_ROOT}/../dev-kit/rules/python/testing/pytest.md"
cat "${CLAUDE_PLUGIN_ROOT}/../dev-kit/rules/python/testing/モック.md"
```

該当言語のルールが存在しない場合はステップ 2-2 へ進む。

### 2-2. プロジェクトの既存テストを補助参照

対象プロジェクトの既存テストコードを読み、テスト方式（フレームワーク・ファイル命名・ディレクトリ構造）を推定する。

```bash
find "$WT" -type f -name "test_*.py" -o -name "*.test.ts" -o -name "*.spec.ts" | head -10
```

## ステップ 3: テスト計画を立案する

Issue の内容（採用方針・分割スコープ）と、ステップ 2 で確認したテスト方式をもとに以下を決定する。

| 項目 | 内容 |
| --- | --- |
| テスト種別 | 結合テスト・単体テスト・スモークテスト等（プロジェクト方式に従う） |
| テスト対象 | 変更される機能・ファイル・ユースケース |
| テストケース | 正常系・異常系・境界値等の一覧 |
| ファイルパス | 新規作成または更新するテストファイルのパス |

## ステップ 4: テストコードを作成する

ステップ 3 の計画に従ってテストコードを作成・更新する。

- テストは「まだ実装コードが存在しない」状態で書く（TDD 原則）
- 実装コードがなくてもインポートやシグネチャが想定できる範囲でテストを記述する
- 実行すると現時点では失敗するテストでよい

## ステップ 5: PR の実装予定タスクを更新する

PR 本文の「実装予定タスク」のテスト作成チェックボックスを完了に更新する。

```bash
# PR 本文を取得して更新
BODY=$(gh pr view {PR_NUMBER} --json body --jq '.body')
# "自動テスト作成/変更" チェックボックスを完了済みに変更
UPDATED=$(echo "$BODY" | sed 's/- \[ \] 自動テスト作成\/変更/- [x] 自動テスト作成\/変更/')
gh pr edit {PR_NUMBER} --body "$UPDATED"
```

## ステップ 6: push

```bash
git -C "$WT" add -A
git -C "$WT" commit -m "test: テストコードを作成 — {テスト種別} for #{Issue 番号}"
git -C "$WT" push origin {branch}
```

## ステップ 7: 戻り値

```json
{
  "branch": "feat/issue-42-router",
  "pr_number": 42,
  "test_files": ["tests/test_example.py"],
  "test_plan": "結合テスト 3 件（正常系 1、異常系 2）",
  "commits_added": 1
}
```

## 制約

| 禁止 |
| --- |
| 実装コードの変更はしない（テストコードのみ） |
| 新規ブランチ・新規 PR は作成しない |
| マージはしない |
| スモークテストは自動実行しない（課金が発生する） |
| `git push --force` は使わない |

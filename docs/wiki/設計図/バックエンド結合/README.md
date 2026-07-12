# バックエンド結合

ai-monitor 自身のバックエンド 1 操作 = MCP ツール（`plugins/ai-monitor/mcp/server.py`）ごとの処理フロー集。
1 ファイル = 1 MCP ツール = 結合テスト 1 ファイル。
モニターの GitHub 操作は本 MCP 経由に限定する（`議論中` の除去エンドポイントは提供しない = 外せるのはユーザーのみ）。

## 参照

| No | ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `get_issue` | [Issue情報取得](./Issue情報取得.md) | Issue / PR の情報を 1 コマンドで取得（フィールドフラグで絞り込み） | 未作成 |
| 2 | `list_addressed_comments` | [宛先コメント一覧](./宛先コメント一覧.md) | 宛先 `@addressee` のコメントだけ抽出（既定で Resolved 除外） | 未作成 |

## コメント

| No | ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `comment` | [コメント投稿](./コメント投稿.md) | 定型フォーマット（🤖 @sender → @receivers + ## title）で投稿 | - |
| 2 | `ask_questions` | [質問投稿](./質問投稿.md) | 選択肢 + 推奨マーク付きの確認質問コメントを投稿 | 未作成 |
| 3 | `reply_comment` | [コメント返信](./コメント返信.md) | 既存コメントに `---` 区切りで定型ブロックを追記 | 未作成 |
| 4 | `save_original_body_comment` | [原文履歴保存](./原文履歴保存.md) | 原文を履歴保存コメントとして投稿し即 Resolve | 未作成 |
| 5 | `resolve_comments` | [コメント一括Resolve](./コメント一括Resolve.md) | minimizeComment mutation で一括 Resolve | 未作成 |

## ラベル

| No | ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `add_labels` | [ラベル追加](./ラベル追加.md) | ラベル追加（冪等）。`議論中` の付与もここ | 未作成 |
| 2 | `remove_labels` | [ラベル除去](./ラベル除去.md) | ラベル除去。`議論中` は対象外（契約） | 未作成 |
| 3 | `transition_phase` | [フェーズ遷移](./フェーズ遷移.md) | ラベル一括入れ替え（`確認:*` の付け替え） | - |

## assignee

| No | ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `set_assignee` | [assignee設定](./assignee設定.md) | assignee 設定（省略時は認証ユーザー） | 未作成 |
| 2 | `remove_assignee` | [assignee除去](./assignee除去.md) | assignee 除去 | 未作成 |

## 本文・状態

| No | ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `update_body` | [本文更新](./本文更新.md) | 本文を完全置換 | 未作成 |
| 2 | `update_title` | [タイトル更新](./タイトル更新.md) | タイトル更新 | 未作成 |
| 3 | `close` | [クローズ](./クローズ.md) | Issue / PR クローズ（reason / delete_branch） | 未作成 |
| 4 | `mark_pr_ready` | [PR_Ready化](./PR_Ready化.md) | Draft PR を Ready 化 | 未作成 |

## Issue / PR 作成・マージ

| No | ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `create_child_issue` | [子Issue作成](./子Issue作成.md) | 子 Issue 作成 + Sub-issue リンク付与 | 未作成 |
| 2 | `create_draft_pr` | [DraftPR作成](./DraftPR作成.md) | Draft PR 作成（Stacked PR の base 明示） | 未作成 |
| 3 | `merge_pr` | [PRマージ](./PRマージ.md) | PR マージ（既定 squash + ブランチ削除） | 未作成 |

## worktree

| No | ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `worktree_create` | [worktree作成](./worktree作成.md) | ブランチ + worktree 作成 | 未作成・実装 `worktree_tool.py` 欠落中 |
| 2 | `worktree_remove` | [worktree削除](./worktree削除.md) | worktree + ブランチ削除 | 〃 |

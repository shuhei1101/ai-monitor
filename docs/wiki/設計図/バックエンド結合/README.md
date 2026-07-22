# バックエンド結合

ai-monitor 自身のバックエンド 1 操作（MCP ツール / 注入 CLI）ごとの処理フロー集。
1 ファイル = 1 操作 = 結合テスト 1 ファイル。
エージェントの GitHub 操作もモニターへの連絡も本 MCP 経由に限定する（`議論中` の除去エンドポイントは提供しない = 外せるのはユーザーのみ）。

## 参照

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `get_issue_or_pr` | [Issue・PR情報取得](./Issue・PR情報取得.py.md) | Issue / PR の情報を 1 コマンドで取得（フィールドフラグで絞り込み） | - |
| `list_addressed_comments` | [宛先コメント一覧](./宛先コメント一覧.py.md) | 自分宛コメントをブロック配列付きで抽出（to なしのユーザーコメント含む・既定で Resolved 除外） | - |
| `search_issues_and_prs` | [Issue・PR検索](./Issue・PR検索.py.md) | キーワードで Issue / PR を横断検索（関連度順・open / closed とも） | - |

## コメント

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `comment` | [コメント投稿](./コメント投稿.py.md) | 定型フォーマット（from / to ヘッダー + 本文）で投稿 | - |
| `ask_questions` | [質問投稿](./質問投稿.py.md) | 選択肢 + 推奨マーク付きの確認質問コメントを投稿 | - |
| `reply_comment` | [コメント返信](./コメント返信.py.md) | 既存コメントに `---` 区切りで定型ブロックを追記 | - |
| `resolve_comments` | [コメント一括Resolve](./コメント一括Resolve.py.md) | minimizeComment mutation で一括 Resolve | - |
| `create_review_comment` | [インラインコメント投稿](./インラインコメント投稿.py.md) | PR の特定ファイル・行に紐づくレビューコメントを投稿 | - |
| `list_review_threads` | [レビュースレッド一覧](./レビュースレッド一覧.py.md) | インライン指摘のスレッドを取得（既定で解決済みを除外） | - |
| `resolve_review_threads` | [レビュースレッド一括Resolve](./レビュースレッド一括Resolve.py.md) | resolveReviewThread mutation で一括解決 | - |

## ラベル

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `add_labels` | [ラベル追加](./ラベル追加.py.md) | ラベル追加（冪等）。`議論中` の付与もここ | - |
| `remove_labels` | [ラベル除去](./ラベル除去.py.md) | ラベル除去。`議論中` は対象外（制約） | - |
| `transition_phase` | [フェーズ遷移](./フェーズ遷移.py.md) | ラベル一括入れ替え（`確認:*` の付け替え） | - |

## assignee

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `set_assignee` | [assignee設定](./assignee設定.py.md) | 認証ユーザーを assignee に設定 | - |
| `remove_assignee` | [assignee除去](./assignee除去.py.md) | 認証ユーザーの assignee を除去 | - |

## 本文・状態

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `update_body` | [本文更新](./本文更新.py.md) | 本文を完全置換 | - |
| `update_title` | [タイトル更新](./タイトル更新.py.md) | タイトル更新 | - |
| `close` | [クローズ](./クローズ.py.md) | Issue / PR クローズ（reason / delete_branch） | - |
| `reopen_issue` | [Issue再オープン](./Issue再オープン.py.md) | クローズ済み Issue の再オープン（バグ差し戻し用） | - |
| `mark_pr_ready` | [PR_Ready化](./PR_Ready化.py.md) | Draft PR を Ready 化 | - |

## Issue / PR 作成・マージ

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `create_child_issue` | [子Issue作成](./子Issue作成.py.md) | 子 Issue 作成 + Sub-issue リンク付与 | - |
| `create_draft_pr` | [DraftPR作成](./DraftPR作成.py.md) | Draft PR 作成（Stacked PR の base 明示） | - |
| `merge_pr` | [PRマージ](./PRマージ.py.md) | PR マージ（既定 squash + ブランチ削除） | - |

## worktree

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `worktree_create` | [worktree作成](./worktree作成.py.md) | ブランチ + worktree 作成 | - |
| `worktree_remove` | [worktree削除](./worktree削除.py.md) | worktree + ブランチ削除 | - |

## 注入

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `read_agent_docs` | [エージェントドキュメント注入](./エージェントドキュメント注入.py.md) | 対応表で ○ の付いた参照ドキュメント一式を標準出力に展開 | CLI（SKILL.md の動的注入から呼ぶ） |
| `read_urls` | [URLドキュメント注入](./URLドキュメント注入.py.md) | 指定 URL の本文を md コードブロックで包んで標準出力に展開 | CLI（SKILL.md の動的注入 / フェーズ内の実行時取得から呼ぶ） |
| `build_wiki_index` | [Wiki索引注入](./Wiki索引注入.py.md) | 監視対象プロジェクトの Wiki の README `## 目次` 表を再帰的に集め、raw URL に変換した「ページ / 概要」2 列表を標準出力に展開 | CLI（SKILL.md の動的注入から呼ぶ・エージェントは索引だけで任意ページを直接読める） |

## モニター

| ツール | リンク | 概要 | 補足 |
| --- | --- | --- | --- |
| `report_completion` | [作業完了報告](./作業完了報告.py.md) | エージェントのターン終了通知（生存更新 + `処理中:*` 除去） | 内部でモニターの `POST /completions` を呼ぶ |
| `add_watch_targets` | [監視対象追加](./監視対象追加.py.md) | 作成した派生 PR を自セッションの監視面として台帳に登録 | 内部でモニターの `POST /watch-targets` を呼ぶ |
| `remove_watch_targets` | [監視対象除去](./監視対象除去.py.md) | 監視面から番号を除去 | 内部でモニターの `DELETE /watch-targets` を呼ぶ |
| - | [エージェント起動検知](./エージェント起動検知.py.md) | 確認ラベル + assignee なしの検知 → セッション作成 or 再開送信 | polling 直轄（HTTP なし） |
| - | [intake自動クローズ](./intake自動クローズ.py.md) | 全 Sub-issue closed の intake を自動クローズ | polling 直轄（HTTP なし） |
| - | [epic一括解放](./epic一括解放.py.md) | epic close 検知で配下の全セッションを一括解放 | polling 直轄（HTTP なし） |
| - | [個別解放](./個別解放.py.md) | 独立系セッションを担当面の close / merge 検知で解放 | polling 直轄（HTTP なし） |
| - | [タイムアウト検知](./タイムアウト検知.py.md) | 処理中のまま超過したセッションの kill + 台帳修復 | heartbeat 直轄（HTTP なし） |

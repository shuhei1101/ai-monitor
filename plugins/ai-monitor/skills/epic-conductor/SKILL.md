---
name: ai-monitor:epic-issue-triage
description: epic Issue の本文整形 + ユースケース一覧 / 横断要件確定、および子 story 起票（2 段階呼び出し）
argument-hint: "[issue-number]"
arguments: "issue_number"
---

# epic-issue-triage

## 入力

- Issue 番号: $issue_number

## 使用する定数

- フェーズ終了ラベル: !`echo "$AI_MONITOR_LABEL_PHASE_END"`
- 再開:子story起票 ラベル: !`echo "$AI_MONITOR_LABEL_RESUME_CREATE_STORY"`

## コメント返信ルール（共通）

!`python "${CLAUDE_PLUGIN_ROOT}/scripts/gh/read_urls.py" "${WIKI_BASE}/規約/コメント.md"`

## エピック Issue 本文テンプレート

!`python "${CLAUDE_PLUGIN_ROOT}/scripts/gh/read_urls.py" "${WIKI_BASE}/テンプレート/イシュー本文/エピック.md"`


## 起動判定

Issue の状態を確認して、実行するフェーズを 1 つ選ぶ。

MCP `get_issue` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false

判定は上から順に見て最初にマッチしたフェーズを実行する。

| 状態 | 実行フェーズ |
| --- | --- |
| 再開:子story起票 ラベルあり + フェーズ終了 ラベルあり | フェーズ F（子 story 起票完了処理） |
| 再開:子story起票 ラベルあり + 自分宛のコメントが 1 件以上ある | フェーズ E（子 story 起票 応答ループ） |
| 再開:子story起票 ラベルあり | フェーズ D（子 story 起票 初回） |
| フェーズ終了 ラベルあり | フェーズ C（要件確定完了処理） |
| 自分宛のコメントが 1 件以上ある | フェーズ B（要件確定 応答ループ） |
| それ以外 | フェーズ A（要件確定 初回） |


## フェーズ A: 要件確定 初回

### A1. 親 Issue の本文を取得

起動判定で取得した `parent.number` を使って親 intake Issue の本文を読む。

MCP `get_issue` を呼ぶ:
- `number`: 起動判定の `parent.number`
- `is_pr`: false

### A2. 本文の骨組み作成 + 概要 / 背景

エピック Issue 本文テンプレートの構成に沿って、以下 5 セクションの骨組みを作成する:

- `## 前提条件`
- `## 概要`
- `## 背景`
- `## ユースケース一覧`
- `## 横断要件`

親 Issue の内容から、この epic の範囲に該当する部分を抽出して以下を書く:
- `## 前提条件`: 親子リンクで表現できない**追加依存**のみ記載（別 Issue / 別 PR との順序依存 等）。該当なしなら「なし」
- `## 概要`: この epic の対象範囲を 1〜3 行で
- `## 背景`: なぜこの epic が必要か（親 Issue の背景から）

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: 骨組み + 概要 / 背景を反映した本文

### A3. ユースケース一覧の草案作成

`## ユースケース一覧` の草案を作成する。

- **業務ドメイン視点の 1 単位** で書く（「{ユーザー} が {何} をする」）
- 実装用語（API / DB カラム / コンポーネント名）は使わない
- 1 行 = 1 ユースケース = 1 story の想定
- `対応 story` 列は現時点では `未起票`（フェーズ D で埋める）
- 「ユースケース / 概要 / 対応 story / 補足」の 4 列表

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: `## ユースケース一覧` を追記した本文

### A4. 横断要件の草案作成

`## 横断要件` の草案を作成する。

- **複数の UC に共通で効く要件** をまとめる
- 単一 UC に閉じる要件は対応 story 側に委譲するのでここに書かない
- カテゴリ: 非機能（セキュリティ / 性能 / 対応環境 / 可用性 / 監査）+ 機能側横断（同時性 / 通知 / 統一 UI 挙動 など）
- 「カテゴリ / 要件 / 対象 UC / 補足」の 4 列表
- `対象 UC` は A3 のユースケース番号を参照（全 UC 共通なら `全 UC`）

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: `## 横断要件` を追記した本文

### A5. 完了報告

MCP `comment` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `epic-issue-triager`
- `receivers`:
  - {ユーザーログイン名}（`gh api user --jq '.login'` で取得）
- `title`: `要件確定 草案`
- `body`:
  ```
  epic Issue の本文を整形しました。

  - `## 概要` / `## 背景`: 整文
  - `## ユースケース一覧`: 草案（{件数} 件）
  - `## 横断要件`: 草案（{件数} 件）

  - 問題なければ `フェーズ終了` ラベル付与 → `確認:epic-pr-initializer` に引き継ぎ
  - 修正が必要なら assignee を外してフィードバックコメントを記入
  ```

### A6. ユーザーへの質問投稿

以下の観点から、今回の epic に該当するものだけを抽出し、AI 側で推奨案を用意して MCP `ask_questions` で投稿する。該当しない観点はコメントに含めない。

| 観点 | 質問 | 選択肢例 | 推奨 |
| --- | --- | --- | --- |
| ユースケースの網羅性 | 「これで全 UC 網羅ですか？」 | A. これで OK / B. 追加すべき UC あり（{候補: 削除・キャンセル・エラー復旧 等}） | A |
| ユースケース間の依存関係 | 「UC {A} と UC {B} は？」 | A. 独立 / B. 連携必要（データ共有） / C. 実行順序に制約あり | A |
| ユースケースの粒度 | 「UC {X} の粒度は？」 | A. 1 story で完結 / B. 複数 story に分割 / C. 他 UC と統合 | A |
| アクター / ロール分岐 | 「ロール別に挙動を分けますか？」 | A. 全ロール同じ / B. 一般 vs 管理者 で分ける / C. さらに細かく分ける | A |
| 権限・アクセス制御 | 「各 UC の実行権限は？」 | A. 本人のみ / B. 管理者のみ / C. 全員 | A |
| 既存機能への影響 | 「既存 {類似機能} への影響は？」 | A. 影響なし / B. 既存を上書き / C. 既存を廃止 | A |
| 横断要件: 性能 | 「性能要件はありますか？」 | A. 特になし（一般水準で OK） / B. 特定要件あり（{数値}） | A |
| 横断要件: セキュリティ | 「セキュリティ要件で追加観点は？」 | A. 現在の記載で十分 / B. 追加あり（他ユーザー閲覧制限 / 監査ログ / PII 扱い 等） | A |
| 横断要件: 対応環境 | 「対応環境は？」 | A. PC のみ / B. PC + タブレット / C. PC + タブレット + スマホ | C |
| 横断要件: 同時性 | 「複数ユーザー同時操作は？」 | A. 許容（最新優先） / B. 検知して警告（楽観的ロック） / C. 排他（悲観的ロック） | B |
| 横断要件: 通知 | 「操作結果の通知は？」 | A. なし / B. 画面内トーストのみ / C. トースト + メール / D. トースト + メール + Push | B |
| 横断要件: 監査ログ | 「操作履歴を残しますか？」 | A. 残さない / B. 主要操作のみ / C. 全操作 | B |
| 横断要件: 国際化 / 多言語 | 「多言語対応は？」 | A. 単言語（日本語のみ） / B. 日英対応 / C. さらに追加 | A |
| データライフサイクル | 「削除の扱いは？」 | A. 論理削除（復元可） / B. 物理削除（即完全削除） / C. 論理→期限後物理 | C |
| エラーハンドリング方針 | 「想定外エラーの扱いは？」 | A. トーストのみ / B. トースト + ログ送信 / C. モーダル + ログ送信 | B |
| UI / UX パターン | 「UI パターンの希望は？」 | A. モーダル / B. ページ遷移 / C. インライン編集 / D. ステップ形式 | B |
| 業務用語の定義 | 「「{業務用語}」の意味は？」 | A. {案 X} / B. {案 Y} | A |
| 姉妹 epic との関係 | 「親 Intake に姉妹 epic があります。連携は？」 | A. 独立進行 / B. 依存あり（先に {先行 epic} を完了） | A |
| スコープ外の確認 | 「スコープ外にする機能はありますか？」 | A. なし（現状のスコープで OK） / B. あり（後続 Issue に切り出す） | A |


MCP `ask_questions` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `epic-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: `確認事項`
- `intro`: `以下の点についてご確認ください。記号（例: `A`）で返信いただければ、その方針で進めます。`
- `questions`: 上記観点表から抽出

### A7. assignee 設定

MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ B: 要件確定 応答ループ（assignee 外し起動）

### B1. 自分宛の未処理コメントを取得

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `epic-issue-triager`
- `include_resolved`: false

### B2. コメント内容に応じて返信 / 本文更新

| 内容 | 対応 |
| --- | --- |
| 明確かつ妥当な指示 | 該当セクション（概要 / 背景 / ユースケース一覧 / 横断要件）を `update_body` で更新 → 「本文を更新しました」と短く追記 |
| 不明確な指示・複数解釈可能 | 「この理解で合っていますか？」と確認の追記 |
| 妥当性に疑問がある指示 | 「ご指摘の方法だと {懸念点}。代替案として {案} はいかがでしょうか？」と返す |
| 質問 | 質問に回答するのみ、本文は触らない |

追記は MCP `reply_comment` を呼ぶ:
- `comment_node_id`: 返信対象コメントの node_id
- `sender`: `epic-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: 短い要約
- `body`: 返信本文

### B3. assignee 再設定

MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ C: 要件確定完了処理（`フェーズ終了` 付与起動）

### C1. 自分宛コメントを取得

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `epic-issue-triager`
- `include_resolved`: false

| 対象 | 扱い |
| --- | --- |
| 自身が投稿 → ユーザーが回答済 or 議論完了 / 本文反映済 | Resolve 対象 |
| 自身が投稿 → ユーザー未回答（選択肢提示・確認要求など） | Resolve NG |
| ユーザー → `@epic-issue-triager` 宛（AI 側が対応済） | Resolve 対象 |

Resolve NG が残る場合はフェーズ B に戻ってユーザーに確認質問を投げる。

### C2. 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: C1 で Resolve 対象に選別したコメントの `node_id` 配列

### C3. ラベル更新 + assignee 除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - !`echo "$AI_MONITOR_LABEL_CONFIRM_EPIC_ISSUE_TRIAGE"`
  - !`echo "$AI_MONITOR_LABEL_PHASE_END"`
- `add_labels_`:
  - !`echo "$AI_MONITOR_LABEL_CONFIRM_EPIC_PR_INITIALIZER"`

続けて MCP `remove_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ D: 子 story 起票 初回

epic PR で複合ユースケースシナリオ設計が確定した後、`再開:子story起票` ラベル付与により起動される。
`## ユースケース一覧` の各 UC ごとに子 story Issue を起票する。

### D1. ユースケース一覧の各 UC ごとに子 story Issue を起票

詳細な本文は書かず、story-issue-triager が起動時に `parent` メタデータで親を辿って埋める。`## ユースケース一覧` の各行について、MCP `create_child_issue` を呼ぶ（UC 件数分繰り返す）:
- `parent_issue_number`: $issue_number
- `title`: `story: {UC 名}`
- `body`: 空文字
- `labels`:
  - !`echo "$AI_MONITOR_LABEL_LAYER_STORY"`
  - !`echo "$AI_MONITOR_LABEL_CONFIRM_STORY_ISSUE_TRIAGE"`

### D2. 親 epic 本文の対応 story 列にリンクを埋める

D1 で作成した各子 Issue の番号を、親 epic の `## ユースケース一覧` の `対応 story` 列に埋める（`未起票` → `#{number}`）。

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: 対応 story 列を更新した本文

### D3. 完了報告 + assignee 設定

MCP `comment` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `epic-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: `子 story 起票完了`
- `body`:
  ```
  `## ユースケース一覧` の各 UC に対応する子 story を起票しました。
  - 作成した子 story: {リンク列挙}
  - 問題なければ `フェーズ終了` ラベル付与 → 再開ラベルとともに `確認:epic-issue-triager` から外れる
  - 起票内容に異論あれば assignee を外してフィードバックコメントを記入
  ```

続けて MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ E: 子 story 起票 応答ループ（assignee 外し起動）

### E1. 自分宛の未処理コメントを取得

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `epic-issue-triager`
- `include_resolved`: false

### E2. コメント内容に応じて返信 / 子 story 修正

| 内容 | 対応 |
| --- | --- |
| 子 story のタイトル / 本文の修正要望 | 該当子 Issue に対して MCP `update_title` / `update_body` で修正 → 「子 story #{番号} を更新しました」と短く追記 |
| 子 story の追加要望 | MCP `create_child_issue` で追加 → 親 epic の `## ユースケース一覧` にも行追加（`update_body`）→ 「追加しました」と短く追記 |
| 子 story の削除要望 | MCP `close`（`reason: not_planned`）→ 親 epic の対応 story 列を `未起票` に戻す（`update_body`）→ 「削除しました」と短く追記 |
| 不明確な指示・複数解釈可能 | 「この理解で合っていますか？」と確認の追記 |
| 質問 | 質問に回答するのみ、本文は触らない |

追記は MCP `reply_comment` を呼ぶ:
- `comment_node_id`: 返信対象コメントの node_id
- `sender`: `epic-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: 短い要約
- `body`: 返信本文

### E3. assignee 再設定

MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ F: 子 story 起票完了処理（`フェーズ終了` 付与起動）

### F1. 自分宛コメントを取得

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `epic-issue-triager`
- `include_resolved`: false

| 対象 | 扱い |
| --- | --- |
| 自身が投稿 → ユーザーが回答済 or 議論完了 / 本文反映済 | Resolve 対象 |
| 自身が投稿 → ユーザー未回答（選択肢提示・確認要求など） | Resolve NG |
| ユーザー → `@epic-issue-triager` 宛（AI 側が対応済） | Resolve 対象 |

Resolve NG が残る場合はフェーズ E に戻ってユーザーに確認質問を投げる。

### F2. 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: F1 で Resolve 対象に選別したコメントの `node_id` 配列

### F3. ラベル更新 + assignee 除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - !`echo "$AI_MONITOR_LABEL_CONFIRM_EPIC_ISSUE_TRIAGE"`
  - !`echo "$AI_MONITOR_LABEL_RESUME_CREATE_STORY"`
  - !`echo "$AI_MONITOR_LABEL_PHASE_END"`
- `add_labels_`:
  - （なし。役割を終えるので次ラベルなし）

続けて MCP `remove_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略

---
name: gh-kit:story-issue-triage
description: story Issue の本文整形 + ユースケース要件確定、および子 subsystem 起票（2 段階呼び出し）
argument-hint: "[issue-number]"
arguments: "issue_number"
---

# story-issue-triage

## 入力

- Issue 番号: $issue_number

## 使用する定数

- フェーズ終了ラベル: !`echo "$GH_KIT_LABEL_PHASE_END"`
- 再開:子subsystem起票 ラベル: !`echo "$GH_KIT_LABEL_RESUME_CREATE_SUBSYSTEM"`

## コメント返信ルール（共通）

!`python "${CLAUDE_PLUGIN_ROOT}/scripts/gh/read_urls.py" "${WIKI_BASE}/規約/コメント.md"`

## ストーリー Issue 本文テンプレート

!`python "${CLAUDE_PLUGIN_ROOT}/scripts/gh/read_urls.py" "${WIKI_BASE}/テンプレート/イシュー本文/ストーリー.md"`


## 起動判定

Issue の状態を確認して、実行するフェーズを 1 つ選ぶ。

MCP `get_issue` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false

判定は上から順に見て最初にマッチしたフェーズを実行する。

| 状態 | 実行フェーズ |
| --- | --- |
| 再開:子subsystem起票 ラベルあり + フェーズ終了 ラベルあり | フェーズ F（子 subsystem 起票完了処理） |
| 再開:子subsystem起票 ラベルあり + 自分宛のコメントが 1 件以上ある | フェーズ E（子 subsystem 起票 応答ループ） |
| 再開:子subsystem起票 ラベルあり | フェーズ D（子 subsystem 起票 初回） |
| フェーズ終了 ラベルあり | フェーズ C（要件確定完了処理） |
| 自分宛のコメントが 1 件以上ある | フェーズ B（要件確定 応答ループ） |
| それ以外 | フェーズ A（要件確定 初回） |


## フェーズ A: 要件確定 初回

### A1. 親 Issue の本文を取得

起動判定で取得した `parent.number` を使って親 epic Issue の本文を読む。

MCP `get_issue` を呼ぶ:
- `number`: 起動判定の `parent.number`
- `is_pr`: false

### A2. 本文の骨組み作成 + 前提条件 / 概要 / 背景

ストーリー Issue 本文テンプレートの構成に沿って、以下 4 セクションの骨組みを作成する:

- `## 前提条件`
- `## 概要`
- `## 背景`
- `## ユースケース要件`

親 epic の内容から、この story が対応する UC を特定して以下を書く:
- `## 前提条件`: 親子リンクで表現できない**追加依存**のみ記載（別 epic / 別 PR / 兄弟 story との順序依存 等）。該当なしなら「なし」
- `## 概要`: 1 UC を 1〜2 行で（「{アクター} が {何をする}」）
- `## 背景`: 「親 epic `#{親番号}` の `## ユースケース一覧` No.{UC 番号}「{UC 名}」に対応」の 1 行を必ず含める

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: 骨組み + 前提条件 / 概要 / 背景を反映した本文

### A3. UC タイプの判定

この story が扱う UC を以下のタイプに分類する。1 story = 1 UC なので基本 1 タイプ、複合的な場合は複数タイプを選ぶ。

| タイプ | 例 |
| --- | --- |
| 一覧 | 一覧画面、検索結果一覧 |
| 詳細 | 詳細画面、プレビュー |
| 編集 | 既存レコードの編集、プロフィール更新 |
| 新規 | 新規作成フォーム、投稿 |
| 削除 | 単体削除、一括削除 |
| 認証 | ログイン、サインアップ、パスワードリセット |
| ダウンロード | CSV エクスポート、レポート出力 |

該当タイプが上記に無い場合は「その他」として観点表を使わず、次の A4 は共通観点のみで草案を作る。

### A4. UC タイプ別観点表の取得

A3 で判定したタイプに対応する観点ページを `read_urls.py` で取得する。複数タイプなら複数取得。

- 一覧: !`echo "${WIKI_BASE}/観点/ユースケース要件_一覧.md"`
- 詳細: !`echo "${WIKI_BASE}/観点/ユースケース要件_詳細.md"`
- 編集: !`echo "${WIKI_BASE}/観点/ユースケース要件_編集.md"`
- 新規: !`echo "${WIKI_BASE}/観点/ユースケース要件_新規.md"`
- 削除: !`echo "${WIKI_BASE}/観点/ユースケース要件_削除.md"`
- 認証: !`echo "${WIKI_BASE}/観点/ユースケース要件_認証.md"`
- ダウンロード: !`echo "${WIKI_BASE}/観点/ユースケース要件_ダウンロード.md"`

### A5. ユースケース要件の草案作成

以下の順で `## ユースケース要件` の要件行を洗い出す。

1. 共通観点を歩く（全 UC 共通、下表）
2. A4 で取得したタイプ別観点表を歩く（該当行を要件化）
3. 各観点で **要件が発生する場合のみ** 行を立てる（該当なしは書かない）

**共通観点**（全 UC 共通で確認する）:

| No | 観点 | 洗い出す内容 |
| --- | --- | --- |
| 1 | 主目的 | この UC でユーザーが達成したい業務ゴール |
| 2 | 事前条件 | この UC を実行できる前提状態（ログイン済み / 特定ロール 等） |
| 3 | 成功時の状態 | 実行完了後にシステム / データがどうなるか |
| 4 | 失敗時の状態 | 実行失敗時にシステム / データがどうなるか |
| 5 | 状態遷移 | UC 内での画面遷移 / モーダル開閉 / タブ切替 |
| 6 | 権限 | 実行できるロール、権限の判定タイミング |
| 7 | 監査 | この UC の実行履歴を残す必要があるか |
| 8 | 通知 | UC 実行時に通知が発生するか、対象は誰か |
| 9 | 他 UC への影響 | 他 UC が使うデータへの副作用 |

**書き方ルール**:
- **ユーザー視点の 1 文** で書く（「{ユーザー} が {アクション} できる / される」）
- 実装用語（API / DB カラム / コンポーネント名）は使わない
- 横断要件（複数 UC 共通）はここに書かない（親 epic の `## 横断要件` に委譲）
- 親 epic の横断要件を参照する行は補足列に `epic 横断要件 #N に基づく` と明記
- 「No / 要件 / 補足」の 3 列表

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: `## ユースケース要件` を追記した本文

### A6. 完了報告

MCP `comment` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `story-issue-triager`
- `receivers`:
  - {ユーザーログイン名}（`gh api user --jq '.login'` で取得）
- `title`: `要件確定 草案`
- `body`:
  ```
  story Issue の本文を整形しました。

  - `## 前提条件` / `## 概要` / `## 背景`: 整文
  - `## ユースケース要件`: 草案（{件数} 件）

  - 問題なければ `フェーズ終了` ラベル付与 → `確認:story-pr-initializer` に引き継ぎ
  - 修正が必要なら assignee を外してフィードバックコメントを記入
  ```

### A7. ユーザーへの質問投稿

以下の観点から、今回の story に該当するものだけを抽出し、AI 側で推奨案を用意して MCP `ask_questions` で投稿する。該当しない観点はコメントに含めない。

| 観点 | 質問 | 選択肢例 | 推奨 |
| --- | --- | --- | --- |
| バリデーション詳細 | 「入力値の上限は？」 | A. 上限なし / B. {案 X: N 文字} / C. 別途要件あり | B |
| 空値・null 許容 | 「空欄を許容しますか？」 | A. 必須 / B. 任意 / C. 条件付き必須 | A |
| 境界値・エッジケース | 「特殊文字 / 多言語入力は？」 | A. 制限なし（そのまま保存） / B. 特定文字を弾く（{文字}） | A |
| 保存タイミング | 「保存方式は？」 | A. 明示ボタン / B. 自動保存（debounce） / C. 離脱時に確認 | A |
| 成功時のフィードバック | 「保存成功時の通知は？」 | A. トースト / B. モーダル / C. 遷移 / D. なし | A |
| エラーメッセージ表示位置 | 「バリデーションエラーの表示は？」 | A. フィールド直下（インライン） / B. トップサマリ / C. モーダル | A |
| 同時性・排他 | 「同時編集の扱いは？」 | A. 最新優先 / B. 楽観的ロックで警告 / C. 悲観的ロック | B |
| 権限 | 「この操作の実行権限は？」 | A. 本人のみ / B. 管理者含む / C. 全員 | A |
| 監査ログ | 「操作履歴を残しますか？」 | A. 残さない / B. 残す（{保管期間}） | B |
| 削除挙動 | 「削除は？」 | A. 論理削除（復元可） / B. 物理削除 / C. 論理→期限後物理 | C |
| 既存 UC との相互作用 | 「他 UC への影響は？」 | A. 影響なし / B. 影響あり（{内容}） | A |
| レスポンス速度要求 | 「レスポンス時間の要求は？」 | A. 特になし / B. {数値} 以内 | A |
| 通知 | 「関係者への通知は？」 | A. なし / B. 本人のみ / C. 本人 + 関係者 | A |
| リトライ・冪等性 | 「二重送信の許容は？」 | A. 冪等キーで排他 / B. UI で連打防止のみ / C. 許容 | A |
| キャンセル可能性 | 「操作の取り消しは？」 | A. 不可 / B. 一定期間内は可 / C. いつでも可 | A |
| タイムアウト | 「処理タイムアウトは？」 | A. デフォルト（30s） / B. 特定値（{値}） / C. なし | A |
| 検索・フィルタ | 「検索・フィルタ機能は？」（一覧系のみ） | A. なし / B. 基本のみ（名前検索） / C. 高度（複数条件） | B |
| 集計・レポート | 「集計値表示は？」 | A. なし / B. カウントのみ / C. 詳細集計 | A |
| 添付ファイル | 「添付ファイル対応は？」 | A. 不要 / B. 画像のみ / C. 任意ファイル | A |
| Undo | 「Undo は？」 | A. なし / B. 直前のみ / C. 一定期間内 | A |


MCP `ask_questions` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `story-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: `確認事項`
- `intro`: `以下の点についてご確認ください。記号（例: `A`）で返信いただければ、その方針で進めます。`
- `questions`: 上記観点表から抽出

### A8. assignee 設定

MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ B: 要件確定 応答ループ（assignee 外し起動）

### B1. 自分宛の未処理コメントを取得

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `story-issue-triager`
- `include_resolved`: false

### B2. コメント内容に応じて返信 / 本文更新

| 内容 | 対応 |
| --- | --- |
| 明確かつ妥当な指示 | 該当セクション（前提条件 / 概要 / 背景 / ユースケース要件）を `update_body` で更新 → 「本文を更新しました」と短く追記 |
| 不明確な指示・複数解釈可能 | 「この理解で合っていますか？」と確認の追記 |
| 妥当性に疑問がある指示 | 「ご指摘の方法だと {懸念点}。代替案として {案} はいかがでしょうか？」と返す |
| 質問 | 質問に回答するのみ、本文は触らない |

追記は MCP `reply_comment` を呼ぶ:
- `comment_node_id`: 返信対象コメントの node_id
- `sender`: `story-issue-triager`
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
- `addressee`: `story-issue-triager`
- `include_resolved`: false

| 対象 | 扱い |
| --- | --- |
| 自身が投稿 → ユーザーが回答済 or 議論完了 / 本文反映済 | Resolve 対象 |
| 自身が投稿 → ユーザー未回答(選択肢提示・確認要求など) | Resolve NG |
| ユーザー → `@story-issue-triager` 宛（AI 側が対応済） | Resolve 対象 |

Resolve NG が残る場合はフェーズ B に戻ってユーザーに確認質問を投げる。

### C2. 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: C1 で Resolve 対象に選別したコメントの `node_id` 配列

### C3. ラベル更新 + assignee 除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - !`echo "$GH_KIT_LABEL_CONFIRM_STORY_ISSUE_TRIAGE"`
  - !`echo "$GH_KIT_LABEL_PHASE_END"`
- `add_labels_`:
  - !`echo "$GH_KIT_LABEL_CONFIRM_STORY_PR_INITIALIZER"`

続けて MCP `remove_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ D: 子 subsystem 起票 初回

story PR で単一ユースケースシナリオ設計が確定した後、`再開:子subsystem起票` ラベル付与により起動される。
この UC の実装に必要な subsystem（BE / FE / DB / 外部連携 等）を洗い出し、それぞれ子 Issue として起票する。

### D1. 実装に必要な subsystem を洗い出す

`## ユースケース要件` と単一ユースケースシナリオを読み、実装分担単位（対象システム）ごとに分解する。

- 画面あり → FE 用の subsystem を切る
- API / DB 変更あり → BE 用の subsystem を切る
- 外部連携あり → 外部連携用の subsystem を切る
- 1 subsystem = 1 対象システムに閉じた実装単位

### D2. 各 subsystem に子 Issue を起票

詳細な本文は書かず、subsystem-issue-triager が起動時に `parent` メタデータで親を辿って埋める。D1 で洗い出した各 subsystem について、MCP `create_child_issue` を呼ぶ（件数分繰り返す）:
- `parent_issue_number`: $issue_number
- `title`: `subsystem: {対象システム名} — {概要}`
- `body`: 空文字
- `labels`:
  - !`echo "$GH_KIT_LABEL_LAYER_SUBSYSTEM"`
  - !`echo "$GH_KIT_LABEL_CONFIRM_SUBSYSTEM_ISSUE_TRIAGE"`

### D3. 完了報告 + assignee 設定

MCP `comment` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `story-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: `子 subsystem 起票完了`
- `body`:
  ```
  この UC の実装に必要な subsystem を起票しました。
  - 作成した子 subsystem: {リンク列挙}
  - 問題なければ `フェーズ終了` ラベル付与 → 再開ラベルとともに `確認:story-issue-triager` から外れる
  - 起票内容に異論あれば assignee を外してフィードバックコメントを記入
  ```

続けて MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ E: 子 subsystem 起票 応答ループ（assignee 外し起動）

### E1. 自分宛の未処理コメントを取得

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `story-issue-triager`
- `include_resolved`: false

### E2. コメント内容に応じて返信 / 子 subsystem 修正

| 内容 | 対応 |
| --- | --- |
| 子 subsystem のタイトル / 本文の修正要望 | 該当子 Issue に対して MCP `update_title` / `update_body` で修正 → 「子 subsystem #{番号} を更新しました」と短く追記 |
| 子 subsystem の追加要望 | MCP `create_child_issue` で追加 → 「追加しました」と短く追記 |
| 子 subsystem の削除要望 | MCP `close`（`reason: not_planned`）→ 「削除しました」と短く追記 |
| 不明確な指示・複数解釈可能 | 「この理解で合っていますか？」と確認の追記 |
| 質問 | 質問に回答するのみ、本文は触らない |

追記は MCP `reply_comment` を呼ぶ:
- `comment_node_id`: 返信対象コメントの node_id
- `sender`: `story-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: 短い要約
- `body`: 返信本文

### E3. assignee 再設定

MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ F: 子 subsystem 起票完了処理（`フェーズ終了` 付与起動）

### F1. 自分宛コメントを取得

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `story-issue-triager`
- `include_resolved`: false

| 対象 | 扱い |
| --- | --- |
| 自身が投稿 → ユーザーが回答済 or 議論完了 / 本文反映済 | Resolve 対象 |
| 自身が投稿 → ユーザー未回答(選択肢提示・確認要求など) | Resolve NG |
| ユーザー → `@story-issue-triager` 宛（AI 側が対応済） | Resolve 対象 |

Resolve NG が残る場合はフェーズ E に戻ってユーザーに確認質問を投げる。

### F2. 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: F1 で Resolve 対象に選別したコメントの `node_id` 配列

### F3. ラベル更新 + assignee 除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - !`echo "$GH_KIT_LABEL_CONFIRM_STORY_ISSUE_TRIAGE"`
  - !`echo "$GH_KIT_LABEL_RESUME_CREATE_SUBSYSTEM"`
  - !`echo "$GH_KIT_LABEL_PHASE_END"`
- `add_labels_`:
  - （なし。役割を終えるので次ラベルなし）

続けて MCP `remove_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略

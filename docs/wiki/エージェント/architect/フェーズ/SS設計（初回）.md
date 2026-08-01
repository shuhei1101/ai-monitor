# SS設計（初回）

親 subsystem Issue の SA と担当範囲を把握し、タスク一覧の先頭にある設計ページを作成して提案コメントを投稿する。

## 手順

### システム要件の確認

subsystem PR 本文の `## 紐づく Issue` から親 subsystem Issue 番号を取り出す。

MCP `get_issue_or_pr` を呼ぶ:
- `number`: 取り出した subsystem Issue の番号
- `is_pr`: false
- `parent`: true
- `comments`: false

`## システム要件（SA）` の機能 / 非機能要件と `### スコープ外` を読み、設計の対象範囲を確定する。

### 親 story の確認

MCP `get_issue_or_pr` を呼ぶ:
- `number`: subsystem Issue の `parent` の番号
- `is_pr`: false
- `comments`: false

`## ユースケース要件` を読み、SA が UC のどの要件に対応するかを確認する。

### 領域別アーキ調査

subsystem ブランチの worktree（`.claude/worktrees/{ブランチ名の / を - に置換}`。ブランチ名は subsystem PR の `head_ref`）へ移動し、`git pull --ff-only` でリモートの最新を取り込む。

親 story ブランチに commit 済みの単一 UC シナリオと、`## タスク一覧` の設計タスクが指す既存の設計 Wiki・実装コードを読み、変更の起点を把握する（設計 Wiki のオンデマンド取得は共通ルール『Wikiページのオンデマンド取得』）。
画面ありの subsystem では、epic の全体UI設計で確定した画面方向性を前提に画面構成・インターフェース定義（フロントエンド）を書く。

`チェックシート/設計変更影響調査.md` の前半（判定一覧の作成まで）を実施し、維持 / 修正 / 廃止の判定一覧を作る。

### 設計ページの作成

`## タスク一覧` の設計タスクを上流順（インターフェース → ER図 → 画面構成 → インターフェース定義（バックエンド / フロントエンド）（フロー）→ モジュール構成）に並べ、担当分の全ページを作成 / 更新して subsystem ブランチに commit push する。

ページごとにユーザーの確認を挟まない。
上流のページが変わると下流のページも直すことになるため、全ページを揃えてから 1 回で確認する。

`設計図/インターフェース定義/バックエンド/{論理名}.md` の `## インターフェース` を確定させた場合は、全ページの commit 後に subsystem-conductor へインターフェース確定報告を投稿する（後続 subsystem を起票するかの判断は story-conductor が行う）。

報告先は subsystem PR ではなく親 subsystem Issue にする。
subsystem PR に `確認:subsystem-conductor` を足すと `確認:architect` と 2 つ並び、両方が同時に起動してしまうため（規約『フェーズ索引の網羅』の 1 面 1 確認ラベル）。
別の面へ報告することで、subsystem PR の手番は architect が持ったまま設計を続けられる。

MCP `comment` を呼ぶ:
- `number`: 「システム要件の確認」で取り出した親 subsystem Issue の番号
- `is_pr`: false
- `sender`: `architect`
- `receiver`: `subsystem-conductor`
- `format`:
  - `type`: `plain`
  - `body`: インターフェース確定の報告（確定した結合ドキュメントのページ名 + リクエスト / レスポンスの要約）

続けて MCP `add_labels` を呼ぶ:
- `number`: 親 subsystem Issue の番号
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_CONDUCTOR` の値

待機には入らずに次の手順へ進む（設計を継続する）。

### 確認事項の投稿

確認したい論点を洗い出し、1 論点 = 1 コメントで投稿する。
投稿先は論点がページの特定箇所に紐づくかで分ける。

ページの特定の記述についての判断（この型でよいか・この分割でよいか 等）は、論点 1 件ごとに MCP `create_review_comment` を呼ぶ:
- `pr_number`: $pr_number
- `path`: 対象ページのパス
- `line`: 論点にあたる行
- `sender`: `architect`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `body`: その行で選んだ内容 + 他に取り得た選択肢 + 推奨（いま書いてある案）と理由

ページに紐づかない全体の方向性（進め方・スコープ・他ページとの整合 等）は、論点 1 件ごとに MCP `comment` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `sender`: `architect`
- `receiver`: ユーザーログイン名
- `format`:
  - `type`: `plain`
  - `body`: 論点 + 他に取り得た選択肢 + 推奨と理由

### 補足事項の投稿

commit した内容を読み返し、共通ルール『インラインコメント』に沿って補足事項を該当行へ投稿する。

### 提案コメントの投稿

MCP `comment` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `sender`: `architect`
- `receiver`: ユーザーログイン名
- `format`:
  - `type`: `plain`
  - `body`: 対象ページの設計提案（確定させたい内容の要約 + 承認・修正方法の案内）

対象ページにライブラリ選定論点がある場合は、続けて「ライブラリ候補の提示」を実行する。

### ライブラリ候補の提示

サブエージェント `ai-monitor:library-finder` で候補を 3〜5 個列挙し、候補ごとに `ai-monitor:library-researcher` を並列起動して観点別評価とコード例を取得する。

MCP `comment` を呼ぶ（設計提案とは別コメントにする）:
- `number`: $pr_number
- `is_pr`: true
- `sender`: `architect`
- `receiver`: ユーザーログイン名
- `format`:
  - `type`: `plain`
  - `body`: 候補比較（候補 / 観点別評価 / 推奨と理由の表）。`判定フローチャート/PoC要否.md` で PoC 実施と判定した場合は候補ごとの検証観点と成功条件も添える

- 要件を満たす候補が 1 つも見つからない場合、本文を不適合の理由 + 代替方針（自作 / 要件緩和 / 設計変更）の相談に差し替える

### 議論中 付与 + 待機

MCP `add_labels` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_IN_DISCUSSION` の値

続けて MCP `set_assignee` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `architect`
- `number`: $pr_number

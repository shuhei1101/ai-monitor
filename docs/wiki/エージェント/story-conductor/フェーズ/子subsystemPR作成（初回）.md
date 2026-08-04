# 子subsystem起票（初回）

single-scenario-writer の完了報告を受けて、単一シナリオを元に subsystem 分担を洗い出し、依存順の先頭グループのみを起票する。

単一ユースケースへの影響なしと確定した story では、シナリオ設計を挟まずに要件確定の次のターンで本フェーズへ入る。
この場合は完了報告コメントが無いため「完了報告の Resolve と起票結果の記録」の Resolve は行わない。

## 手順

### 単一シナリオの確認

epic ブランチ配下の worktree に切り替えて（成果物ブランチの worktree）、single-scenario-writer が commit した `docs/wiki/設計図/シナリオ/単一ユースケース/{UC名}.md` を読む。

単一 UC 影響なしの経路では新規シナリオが無いため、代わりに master 側の既存シナリオと story PR 本文の `## ユースケース要件` を材料にする。

### subsystem の洗い出しと依存順の決定

シナリオの結合フローから subsystem（FE / BE / 外部連携 等）を洗い出し、対象システムごとの担当範囲と依存順（例: BE → FE）を決める。

### scope ラベルの用意

`scope:*` はプロジェクトごとに値が違うため `constants.env` に無く、リポジトリに未作成のことがある。
Issue へのラベル付与 API は未作成のラベルをランダムな色で作ってしまうので、起票の前に用意する。

洗い出した subsystem の `scope` 1 件ごとに MCP `create_label` を呼ぶ:
- `name`: `scope:{識別子}`（識別子は親 system PR の `## 構成要件` で割り当てられたもの）
- `color`: `$AI_MONITOR_LABEL_COLOR_SCOPE` の値
- `description`: `$AI_MONITOR_LABEL_DESC_SCOPE` の値

既に存在する場合は `created: false` が返るだけで何も変わらない。

### 先頭グループのブランチ作成

依存のない先頭グループの subsystem について、1 件ごとに MCP `worktree_create` を呼ぶ:
- `branch`: `{type}/{scope}/{ドメイン}/{UC名}`（規約『ブランチ戦略』の命名形式）
- `base_ref`: `origin/{自分の story ブランチ}`

### 先頭グループの PR 作成

作成したブランチ 1 本ごとに MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成したブランチ
- `base_branch`: 自分の story ブランチ
- `title`: subsystem 名（`{UC名} {対象システム}` 形式）
- `body`: `## 紐づく Issue`（自 PR と同じ起点の Issue 番号）のみ
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_SUBSYSTEM` の値
  - 対象システムの `scope:*` ラベル
  - 親から引き継ぐラベル（`type:*` / `リバースエンジニアリング`）

本文の要件は subsystem-conductor が起動後に埋める。

### スタックへの接続

先頭グループは先行 PR が無いため、自 PR のスタックへ直接繋ぐ。

MCP `link_stack` を呼ぶ:
- `pull_requests`: 自 PR 番号と作成した PR 番号の配列（下から上）

### 確認ラベルの付与

作成した PR 1 件ごとに MCP `add_labels` を呼ぶ:
- `number`: PR 番号
- `is_pr`: true
- `labels`: `$AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_CONDUCTOR` の値

本文とスタックの接続を終えてから付ける（先に付けると材料が揃う前に担当が動き出す）。

### サブシステム一覧の記入

洗い出した subsystem を story PR 本文の `## サブシステム一覧` に全件記入する（書式は PR 本文テンプレート「ストーリー」。テンプレート定義順の位置に挿入する）。
起票した先頭グループの行は `対応 subsystem` 列に `#番号` を入れ、残りは `未作成` のままにする。

MCP `update_body` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `body`: 更新後本文

### 完了報告の Resolve と起票結果の記録

single-scenario-writer の完了報告コメントがある場合、MCP `resolve_comments` で Resolve する（単一 UC 影響なしの経路では省略する）。

続けて MCP `comment` を呼ぶ（待機なし）:
- `number`: $number
- `is_pr`: true
- `sender`: `story-conductor`
- `receiver`: ユーザーログイン名
- `format`:
  - `type`: `plain`
  - `body`: 起票結果（先頭グループの subsystem PR リンク一覧 + 依存順の要点）

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `story-conductor`
- `number`: $number

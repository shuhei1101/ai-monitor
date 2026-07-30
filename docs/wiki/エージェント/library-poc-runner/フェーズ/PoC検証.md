# PoC検証

担当候補の最小 PoC コードを実装して検証を実行し、実測値と判定を PoC PR 本文に記録して発注元へ報告する。

## 手順

### 検証指示と本文の確認

検証指示コメントと PoC PR 本文（`## 検証対象` / `## 調査結果` / `## 検証観点と結果`）から、検証するライブラリ・バージョン・使い方の要点・観点ごとの成功条件を把握する。

- `## 検証対象` の `既存 Wiki` 行にページ名がある場合、そのページ（採用済みバージョン・使用中のメソッド）も読んで前提に含める（オンデマンド取得は共通ルール『Wikiページのオンデマンド取得』）

### 最小 PoC コードの実装

PoC ブランチの worktree（`.claude/worktrees/{ブランチ名の / を - に置換}`。ブランチ名は PoC PR の `head_ref`）へ移動し、`git pull --ff-only` でリモートの最新を取り込む。

`## 検証観点と結果` の各観点を実測できる最小のコードを実装し、commit push する。

### 検証実行

実装したコードを実行し、観点ごとに実測値を収集する（ターミナルへの報告は共通ルール『ターミナル出力』）。

### 検証結果の記録

テンプレート「PR本文/ライブラリPoC」の書式に従い、`## 検証観点と結果` の実測値・判定（`✅` / `❌`）・所感を記入し、`## 最小再現コード`（核心部 10〜30 行 + diff の見どころ）を新設する。

- 成功条件を満たさない観点がある場合、判定を `❌` にして実測値と満たせない理由を記録する（採用可否は発注元が判断するため、PoC PR は open のまま残す）

MCP `update_body` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `body`: 更新後本文

### 検証指示の Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: 検証指示コメントの node_id

### 発注元への完了報告

MCP `comment` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `sender`: `library-poc-runner`
- `receiver`: 検証指示コメントの送信者
- `format`:
  - `type`: `commits`
  - `body`: 検証の完了報告（観点ごとの実測値と判定のサマリ + 所感）
  - `entries`: 積んだ commit の `commit` と `summary` の組

続けて MCP `transition_phase` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_LIBRARY_POC_RUNNER` の値
- `add_labels_`:
  - 発注元が architect なら `$AI_MONITOR_LABEL_CONFIRM_ARCHITECT` の値

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `library-poc-runner`
- `number`: $pr_number

---
name: ai-monitor:mock-designer
description: epic 全体の UI 設計（画面一覧・遷移・モック）を確定するエージェント
argument-hint: "[pr-number]"
arguments: "pr_number"
disable-model-invocation: true
---

# mock-designer

epic 全体の画面の方向性 — 画面一覧（新規 / 変更の洗い出し）・画面遷移の全体像・新規 / 変更画面のモック — を確定するエージェント。
方針の合意 → モック作成 → モックの合意 の 2 ゲートで進め、確定内容を epic PR 本文の `## UI 設計` に段階反映する。

## 入力

- PR 番号: $pr_number

## フェーズ

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/mock-designer/README.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/mock-designer/フェーズ/初期処理.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/mock-designer/フェーズ/方針提案（初回）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/mock-designer/フェーズ/方針の応答ループ.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/mock-designer/フェーズ/モック作成.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/mock-designer/フェーズ/モックの応答ループ.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/mock-designer/フェーズ/完了処理.md"`

## 参考資料

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_agent_docs.py" mock-designer`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/build_wiki_index.py"`

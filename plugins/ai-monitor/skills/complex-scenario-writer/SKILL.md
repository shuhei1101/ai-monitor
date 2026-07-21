---
name: ai-monitor:complex-scenario-writer
description: epic の複合ユースケースシナリオを設計するエージェント
argument-hint: "[pr-number]"
arguments: "pr_number"
disable-model-invocation: true
---

# complex-scenario-writer

epic 本文のユースケース一覧をもとに、UC を箱として連鎖させた業務フロー（複合ユースケースシナリオ）を設計し、epic ブランチに commit するエージェント。

## 入力

- PR 番号: $pr_number

## フェーズ

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/complex-scenario-writer/README.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/complex-scenario-writer/フェーズ/初期処理.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/complex-scenario-writer/フェーズ/シナリオ作成（初回）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/complex-scenario-writer/フェーズ/応答ループ.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/complex-scenario-writer/フェーズ/完了処理.md"`

## 参考資料

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_agent_docs.py" complex-scenario-writer`

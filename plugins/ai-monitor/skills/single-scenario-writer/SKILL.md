---
name: ai-monitor:single-scenario-writer
description: story のユースケース要件から単一ユースケースシナリオを設計するエージェント
argument-hint: "[pr-number]"
arguments: "pr_number"
disable-model-invocation: true
---

# single-scenario-writer

story Issue の `## ユースケース要件` をもとに 1 UC 分の単一ユースケースシナリオ（正常系 + 異常系）を設計し、story ブランチに commit するエージェント。

## 入力

- PR 番号: $pr_number

## フェーズ

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/single-scenario-writer/README.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/single-scenario-writer/フェーズ/初期処理.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/single-scenario-writer/フェーズ/シナリオ作成（初回）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/single-scenario-writer/フェーズ/応答ループ.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/single-scenario-writer/フェーズ/完了処理.md"`

## 参考資料

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_agent_docs.py" single-scenario-writer`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/build_wiki_index.py"`

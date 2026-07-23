---
name: ai-monitor:epic-poc-runner
description: epic の実現可能性 PoC 検証エージェント
argument-hint: "[pr-number]"
arguments: "pr_number"
disable-model-invocation: true
---

# epic-poc-runner

epic の成立条件になっている核心機構を最安直構成で検証する独立系エージェント。
方針をユーザーと固めた上で検証コードを実装・実行し、結果を PoC PR 本文と親 epic Issue に記録して epic-conductor に返す。

## 入力

- PR 番号: $pr_number

## フェーズ

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/epic-poc-runner/README.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/epic-poc-runner/フェーズ/初期処理.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/epic-poc-runner/フェーズ/方針固め（初回）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/epic-poc-runner/フェーズ/応答ループ.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/epic-poc-runner/フェーズ/検証実行.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/epic-poc-runner/フェーズ/完了処理.md"`

## 参考資料

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_agent_docs.py" epic-poc-runner`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/build_wiki_index.py"`

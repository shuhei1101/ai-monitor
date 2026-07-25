---
template_version: 1.0.0
name: ai-monitor:subsystem-conductor
description: subsystem レイヤーの指揮役
argument-hint: "[issue-number]"
arguments: "issue_number"
disable-model-invocation: true
---

# subsystem-conductor

subsystem レイヤーの指揮役。
1 対象システム分のシステム要件を確定し、設計〜実装レビューの一式を architect へ委任して、subsystem → story への昇格マージまでを進行させる。

## 入力

- Issue 番号: $issue_number

## フェーズ

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/README.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/初期処理.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/要件確定（初回）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/エスカレーションの中継.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/応答ループ.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/バグ修正着手.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/SA変更確定.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/要件確定（完了処理）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/タスク一覧確定.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/インターフェース確定の中継.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/マージ起動.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/subsystem-conductor/フェーズ/subsystemマージ.md"`

## 参考資料

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_agent_docs.py" subsystem-conductor`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/build_wiki_index.py"`

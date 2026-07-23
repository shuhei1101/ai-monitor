---
name: ai-monitor:intake-issue-triager
description: 起点レイヤーの振り分け役
argument-hint: "[issue-number]"
arguments: "issue_number"
disable-model-invocation: true
---

# intake-issue-triager

起点レイヤーの振り分け役。
ユーザーが起票した Issue を作業単位に分解し、承認を経て epic / story / subsystem / chore のサブ Issue として起票する。

## 入力

- Issue 番号: $issue_number

## フェーズ

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/intake-issue-triager/README.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/intake-issue-triager/フェーズ/初期処理.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/intake-issue-triager/フェーズ/分解判定（応答ループ）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/intake-issue-triager/フェーズ/サブIssue起票（完了処理）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/intake-issue-triager/フェーズ/分解判定（初回）.md"`

## 参考資料

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_agent_docs.py" intake-issue-triager`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/build_wiki_index.py"`

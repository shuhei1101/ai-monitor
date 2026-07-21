---
name: ai-monitor:story-conductor
description: story レイヤーの指揮役
argument-hint: "[issue-number]"
arguments: "issue_number"
disable-model-invocation: true
---

# story-conductor

story レイヤーの指揮役。
1 ユースケースの要件を確定し、実装分担（subsystem）への分解から統合テスト起動、story → epic への昇格マージまでを進行させる。

## 入力

- Issue 番号: $issue_number

## フェーズ

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/README.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/初期処理.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/要件確定（初回）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/応答ループ.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/要件確定（完了処理）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/子subsystem起票（初回）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/子subsystem起票（逐次）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/統合テスト起動.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/バグ差し戻し（方針確認）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/バグ差し戻し（実行）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/バグ差し戻しの中継（下り）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/バグ差し戻しの中継（上り）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${AI_MONITOR_WIKI_BASE}/エージェント/story-conductor/フェーズ/storyマージ.md"`

## 参考資料

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_agent_docs.py" story-conductor`

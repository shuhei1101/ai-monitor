---
name: ai-monitor:epic-conductor
description: epic レイヤーの指揮役
argument-hint: "[issue-number]"
arguments: "issue_number"
disable-model-invocation: true
---

# epic-conductor

epic レイヤーの指揮役。
機能全体の要件を確定し、実現可能性 PoC・UI 全体設計の判断から子 story の起票、複合 UC 統合テストの委任、epic → master マージまでを進行させる。

## 入力

- Issue 番号: $issue_number

## フェーズ

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/README.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/初期処理.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/要件確定（初回）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/応答ループ.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/要件確定（完了処理）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/PoC結果確認.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/モック完了確認.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/子story起票.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/統合テスト起動.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/バグ差し戻し（方針確認）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/バグ差し戻し（実行）.md"`

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_urls.py" "${WIKI_BASE}/エージェント/epic-conductor/フェーズ/epicマージ.md"`

## 参考資料

!`python "${CLAUDE_PLUGIN_ROOT}/inject/read_agent_docs.py" epic-conductor`

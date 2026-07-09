#!/usr/bin/env bash
#
# 使い方
# source constants.sh で定数をロードする

# 定数
export REPO_SLUG=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
export WIKI_BASE="https://raw.githubusercontent.com/${REPO_SLUG}/master/docs/wiki"

# 共通
export AI_MONITOR_LABEL_PHASE_END="フェーズ終了"
export AI_MONITOR_LABEL_PROCESSING_PREFIX="処理中:"

# レイヤー（intake-issue-triager が判定して付与）
export AI_MONITOR_LABEL_LAYER_INTAKE="layer:intake"
export AI_MONITOR_LABEL_LAYER_EPIC="layer:epic"
export AI_MONITOR_LABEL_LAYER_STORY="layer:story"
export AI_MONITOR_LABEL_LAYER_SUBSYSTEM="layer:subsystem"
export AI_MONITOR_LABEL_LAYER_CHORE="layer:chore"

# 再開（2 段階呼び出しの復帰トリガー）
export AI_MONITOR_LABEL_RESUME_CREATE_STORY="再開:子story起票"
export AI_MONITOR_LABEL_RESUME_CREATE_SUBSYSTEM="再開:子subsystem起票"

# --- 起点 ---
# 1. intake-issue-triager
export AI_MONITOR_LABEL_CONFIRM_INTAKE_ISSUE_TRIAGE="確認:intake-issue-triager"
export AI_MONITOR_LABEL_PROCESSING_INTAKE_ISSUE_TRIAGE="処理中:intake-issue-triager"

# --- epic レイヤー ---
# 2. epic-issue-triager
export AI_MONITOR_LABEL_CONFIRM_EPIC_ISSUE_TRIAGE="確認:epic-issue-triager"
export AI_MONITOR_LABEL_PROCESSING_EPIC_ISSUE_TRIAGE="処理中:epic-issue-triager"

# 3. epic-pr-initializer
export AI_MONITOR_LABEL_CONFIRM_EPIC_PR_INITIALIZER="確認:epic-pr-initializer"
export AI_MONITOR_LABEL_PROCESSING_EPIC_PR_INITIALIZER="処理中:epic-pr-initializer"

# 4. complex-scenario-writer
export AI_MONITOR_LABEL_CONFIRM_COMPLEX_SCENARIO_WRITER="確認:complex-scenario-writer"
export AI_MONITOR_LABEL_PROCESSING_COMPLEX_SCENARIO_WRITER="処理中:complex-scenario-writer"

# 5. complex-scenario-tester
export AI_MONITOR_LABEL_CONFIRM_COMPLEX_SCENARIO_TESTER="確認:complex-scenario-tester"
export AI_MONITOR_LABEL_PROCESSING_COMPLEX_SCENARIO_TESTER="処理中:complex-scenario-tester"

# --- story レイヤー ---
# 6. story-issue-triager
export AI_MONITOR_LABEL_CONFIRM_STORY_ISSUE_TRIAGE="確認:story-issue-triager"
export AI_MONITOR_LABEL_PROCESSING_STORY_ISSUE_TRIAGE="処理中:story-issue-triager"

# 7. story-pr-initializer
export AI_MONITOR_LABEL_CONFIRM_STORY_PR_INITIALIZER="確認:story-pr-initializer"
export AI_MONITOR_LABEL_PROCESSING_STORY_PR_INITIALIZER="処理中:story-pr-initializer"

# 8. single-scenario-writer
export AI_MONITOR_LABEL_CONFIRM_SINGLE_SCENARIO_WRITER="確認:single-scenario-writer"
export AI_MONITOR_LABEL_PROCESSING_SINGLE_SCENARIO_WRITER="処理中:single-scenario-writer"

# 9. single-scenario-tester
export AI_MONITOR_LABEL_CONFIRM_SINGLE_SCENARIO_TESTER="確認:single-scenario-tester"
export AI_MONITOR_LABEL_PROCESSING_SINGLE_SCENARIO_TESTER="処理中:single-scenario-tester"

# --- subsystem レイヤー ---
# 10. subsystem-issue-triager
export AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_ISSUE_TRIAGE="確認:subsystem-issue-triager"
export AI_MONITOR_LABEL_PROCESSING_SUBSYSTEM_ISSUE_TRIAGE="処理中:subsystem-issue-triager"

# 11. subsystem-pr-initializer
export AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_PR_INITIALIZER="確認:subsystem-pr-initializer"
export AI_MONITOR_LABEL_PROCESSING_SUBSYSTEM_PR_INITIALIZER="処理中:subsystem-pr-initializer"

# 12. ui-designer
export AI_MONITOR_LABEL_CONFIRM_UI_DESIGNER="確認:ui-designer"
export AI_MONITOR_LABEL_PROCESSING_UI_DESIGNER="処理中:ui-designer"

# 13. architect
export AI_MONITOR_LABEL_CONFIRM_ARCHITECT="確認:architect"
export AI_MONITOR_LABEL_PROCESSING_ARCHITECT="処理中:architect"

# 14. tester
export AI_MONITOR_LABEL_CONFIRM_TESTER="確認:tester"
export AI_MONITOR_LABEL_PROCESSING_TESTER="処理中:tester"

# 15. implementer
export AI_MONITOR_LABEL_CONFIRM_IMPLEMENTER="確認:implementer"
export AI_MONITOR_LABEL_PROCESSING_IMPLEMENTER="処理中:implementer"

# 16. reviewer
export AI_MONITOR_LABEL_CONFIRM_REVIEWER="確認:reviewer"
export AI_MONITOR_LABEL_PROCESSING_REVIEWER="処理中:reviewer"

# --- 共通後段 ---
# 17. merger
export AI_MONITOR_LABEL_CONFIRM_MERGER="確認:merger"
export AI_MONITOR_LABEL_PROCESSING_MERGER="処理中:merger"

# --- 独立系 ---
# 18. resetter
export AI_MONITOR_LABEL_CONFIRM_RESETTER="確認:resetter"
export AI_MONITOR_LABEL_PROCESSING_RESETTER="処理中:resetter"

# 19. quick-implementer
export AI_MONITOR_LABEL_CONFIRM_QUICK_IMPLEMENTER="確認:quick-implementer"
export AI_MONITOR_LABEL_PROCESSING_QUICK_IMPLEMENTER="処理中:quick-implementer"

# 20. questioner
export AI_MONITOR_LABEL_CONFIRM_QUESTIONER="確認:questioner"
export AI_MONITOR_LABEL_PROCESSING_QUESTIONER="処理中:questioner"

# ---------------------------------------------------------------------
# その他のラベル
# ---------------------------------------------------------------------

# 優先度（ユーザーが付与）
export AI_MONITOR_LABEL_PRIORITY_URGENT="優先度:急ぎ"
export AI_MONITOR_LABEL_PRIORITY_LOW="優先度:いつでも"

# タイプ（issue-triager が付与）
export AI_MONITOR_LABEL_TYPE_BUG="type:bug"
export AI_MONITOR_LABEL_TYPE_FEAT="type:feat"
export AI_MONITOR_LABEL_TYPE_REFACTOR="type:refactor"
export AI_MONITOR_LABEL_TYPE_DOCS="type:docs"
export AI_MONITOR_LABEL_TYPE_CHORE="type:chore"
export AI_MONITOR_LABEL_TYPE_TEST="type:test"

# ---------------------------------------------------------------------
# Wiki テンプレートファイルパス（WIKI_BASE からの相対）
# ---------------------------------------------------------------------

# Issue 本文テンプレ
export AI_MONITOR_TEMPLATE_ISSUE_EPIC="テンプレート/イシュー本文/エピック.md"
export AI_MONITOR_TEMPLATE_ISSUE_STORY="テンプレート/イシュー本文/ストーリー.md"
export AI_MONITOR_TEMPLATE_ISSUE_SUBSYSTEM="テンプレート/イシュー本文/サブシステム.md"

# PR 本文テンプレ
export AI_MONITOR_TEMPLATE_PR_EPIC="テンプレート/PR本文/エピック.md"
export AI_MONITOR_TEMPLATE_PR_STORY="テンプレート/PR本文/ストーリー.md"
export AI_MONITOR_TEMPLATE_PR_SUBSYSTEM="テンプレート/PR本文/サブシステム.md"

# 設計テンプレ
export AI_MONITOR_TEMPLATE_SCENARIO="テンプレート/シナリオ.md"
export AI_MONITOR_TEMPLATE_MODULE_COMPOSITION="テンプレート/モジュール構成.md"
export AI_MONITOR_TEMPLATE_TEST_FIXTURE="テンプレート/テストフィクスチャ.md"

# 判定フローチャート
export AI_MONITOR_TEMPLATE_LAYER_DECISION="判定フローチャート/レイヤー.md"

# 補助テンプレ
export AI_MONITOR_TEMPLATE_REVIEW_RESULT="レビュー結果コメント.md"
export AI_MONITOR_TEMPLATE_USER_REVIEW_CRITERIA="ユーザー確認要否判定.md"
export AI_MONITOR_TEMPLATE_SCRIPT_TEST_REPORT="スクリプトテスト結果報告テンプレート.md"
export AI_MONITOR_TEMPLATE_OTHER_TEST_REPORT="その他動作確認報告テンプレート.md"
export AI_MONITOR_TEMPLATE_LIBRARY_SELECTION="テンプレート_ライブラリ選定論点.md"
export AI_MONITOR_TEMPLATE_DESIGN_REVIEW="テンプレート_設計レビュー論点.md"

---
template_version: 1.0.0
---

# エージェント

エージェントごとの実務ドキュメント（フェーズ索引 + フェーズページ）。
モニターが起動プロンプトへ本フォルダの該当ページを全文で載せる（対象は `config/agent_phases.yaml` が持つ）。
各ページの書式は [テンプレート](./テンプレート/) に従う。

## 目次

| ページ | 概要 | 補足 |
| --- | --- | --- |
| [テンプレート](./テンプレート/) | フェーズ索引 + フェーズページの書式定義 | - |
| [intake-issue-triager](./intake-issue-triager/) | intake Issue の分解とサブ Issue 起票 | - |
| [epic-conductor](./epic-conductor/) | epic 要件確定から子 story 起票・統合テスト委任・master マージまでの指揮 | - |
| [epic-poc-runner](./epic-poc-runner/) | epic の実現可能性 PoC 検証 | - |
| [mock-designer](./mock-designer/) | epic 全体の UI 設計（画面一覧・遷移・モック）を確定 | - |
| [complex-scenario-writer](./complex-scenario-writer/) | epic の複合ユースケースシナリオを設計 | - |
| [story-conductor](./story-conductor/) | story 要件確定から子 subsystem 起票・バグ差し戻し中継・story マージまでの指揮 | - |
| [single-scenario-writer](./single-scenario-writer/) | story のユースケース要件から単一ユースケースシナリオを設計 | - |
| [subsystem-conductor](./subsystem-conductor/) | subsystem の要件確定から architect への一式委任・バグ修正着手・subsystem マージまでの指揮 | - |

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
| [RE担当共通](./RE担当共通/) | `*-reverse-engineer` 5 体が共有するフェーズページ | エージェントではない |
| [RE発注共通](./RE発注共通/) | 4 レイヤーの conductor が共有する RE 起動フェーズ | エージェントではない |
| [intake-issue-triager](./intake-issue-triager/) | intake Issue の分解とサブ Issue 起票 | - |
| [system-conductor](./system-conductor/) | 構成要件の確定から土台生成の委任・master マージ・子 epic 一括起票までの指揮 | ユーザーが直接起票（intake を経由しない） |
| [system-architect](./system-architect/) | アーキテクチャ図・`docs/wiki/` 骨格・`docs/rules.yaml`・`README.md` の生成とラベル一括作成 | プロジェクトごとに 1 回 |
| [architecture-reverse-engineer](./architecture-reverse-engineer/) | 実装コードからの現状アーキテクチャ図の起こし | 発注元は system-conductor |
| [mock-reverse-engineer](./mock-reverse-engineer/) | 実装画面からの現状モックの起こし | 発注元は epic-conductor |
| [complex-scenario-reverse-engineer](./complex-scenario-reverse-engineer/) | 実装コードからの現状複合 UC シナリオの起こし | 発注元は epic-conductor |
| [single-scenario-reverse-engineer](./single-scenario-reverse-engineer/) | 実装コードからの現状単一 UC シナリオの起こし | 発注元は story-conductor |
| [ss-design-reverse-engineer](./ss-design-reverse-engineer/) | 実装コードからの現状インターフェース定義 / モジュール構成の起こし | 発注元は subsystem-conductor |
| [epic-conductor](./epic-conductor/) | epic 要件確定から子 story 起票・統合テスト委任・master マージまでの指揮 | - |
| [epic-poc-runner](./epic-poc-runner/) | epic の実現可能性 PoC 検証 | - |
| [mock-designer](./mock-designer/) | epic 全体の UI 設計（画面一覧・遷移・モック）を確定 | - |
| [complex-scenario-writer](./complex-scenario-writer/) | epic の複合ユースケースシナリオを設計・複合 UC 統合テストを指揮 | - |
| [complex-scenario-tester](./complex-scenario-tester/) | 複合 UC の E2E テスト実装と実行 | - |
| [story-conductor](./story-conductor/) | story 要件確定から子 subsystem 起票・バグ差し戻し中継・story マージまでの指揮 | - |
| [single-scenario-writer](./single-scenario-writer/) | story のユースケース要件から単一ユースケースシナリオを設計・単一 UC 統合テストを指揮 | - |
| [single-scenario-tester](./single-scenario-tester/) | 単一 UC の E2E テスト実装と実行 | - |
| [subsystem-conductor](./subsystem-conductor/) | subsystem の要件確定から architect への一式委任・バグ修正着手・subsystem マージまでの指揮 | - |
| [architect](./architect/) | SS 設計とライブラリ選定の確定・tester / implementer への割り当てとレビュー | - |
| [library-poc-runner](./library-poc-runner/) | ライブラリ候補 1 つの PoC 検証と結果記録 | - |
| [tester](./tester/) | 結合 / モジュール構成を元にしたテストコードの作成と指摘対応 | - |
| [implementer](./implementer/) | 結合 / モジュール構成のとおりの実装と指摘対応 | - |
| [resetter](./resetter/) | 不要化した Issue 配下の巻き戻し（子孫 Issue / PR / ブランチの削除） | 唯一のユーザー手動起動 |
| [questioner](./questioner/) | question Issue の調査と回答 | 実装は行わない |

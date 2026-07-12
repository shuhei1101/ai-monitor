# シナリオ

単一ユースケース / 複合ユースケース の 2 種類を扱う。
1 ファイル = 1 テストファイル（pytest による E2E 実行の 1 ケース）に対応する。

**評価方針:** 画面がないため Playwright ではなく **pytest + gh CLI + sandbox リポ** で「gh api で観測可能なアーティファクト状態」を assert する。
テスト対象のシナリオノードは全て「Issue のラベル / assignee / comment」「PR の state / base」「Sub-issue の存在」等の外部観測可能な状態変化として書く。

## 一覧

| No | 種別 | シナリオ / 機能名 | 概要 | リンク | 補足 |
| --- | --- | --- | --- | --- | --- |
| 1 | 単一ユースケース | Issue分解と子起票 | intake Issue の分解 → 承認 → Sub-issue 起票 | [Issue分解と子起票](./単一ユースケース/Issue分解と子起票.md) | intake-issue-triager |
| 2 | 〃 | epic要件確定 | epic 本文 5 セクション確定 + PoC 要否判定 | [epic要件確定](./単一ユースケース/epic要件確定.md) | epic-conductor 初回 |
| 3 | 〃 | 実現可能性PoC検証 | 核心機構の成立検証・PoC PR はマージせず close | [実現可能性PoC検証](./単一ユースケース/実現可能性PoC検証.md) | epic-poc-runner・条件付き |
| 4 | 〃 | PoC結果確認 | PoC 結果の確認 → epic Draft PR 作成 + 引き継ぎ | [PoC結果確認](./単一ユースケース/PoC結果確認.md) | epic-conductor 復帰・条件付き |
| 5 | 〃 | 全体UI設計 | 画面一覧・遷移全体像・モックで画面の方向性を確定 | [全体UI設計](./単一ユースケース/全体UI設計.md) | mock-designer・画面の新規作成 / レイアウト変更を含む epic のみ |
| 6 | 〃 | 複合シナリオ設計 | 複合 UC シナリオを epic ブランチに commit | [複合シナリオ設計](./単一ユースケース/複合シナリオ設計.md) | complex-scenario-writer |
| 7 | 〃 | 子story起票 | UC 一覧から story Issue x N 起票 | [子story起票](./単一ユースケース/子story起票.md) | epic-conductor 復帰 |
| 8 | 〃 | story要件確定 | story 本文 4 セクション確定 | [story要件確定](./単一ユースケース/story要件確定.md) | story-conductor 初回 |
| 9 | 〃 | 単一シナリオ設計 | 単一 UC シナリオを story ブランチに commit | [単一シナリオ設計](./単一ユースケース/単一シナリオ設計.md) | single-scenario-writer |
| 10 | 〃 | 子subsystem起票 | 実装分担単位で subsystem Issue x M 起票 | [子subsystem起票](./単一ユースケース/子subsystem起票.md) | story-conductor 復帰 |
| 11 | 〃 | subsystem要件確定 | 現状調査 + システム要件（SA）確定 | [subsystem要件確定](./単一ユースケース/subsystem要件確定.md) | subsystem-conductor |
| 12 | 〃 | UI設計 | 画面構成 / 遷移 / モック合意 + FE Wiki 更新 | [UI設計](./単一ユースケース/UI設計.md) | ui-designer・画面ありのみ |

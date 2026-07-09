# gh-kit 状態遷移

gh-kit のワークフローを Issue / PR のラベル状態遷移で表現したページ群。

## 目次

| No | ページ | 対象 |
| --- | --- | --- |
| 1 | [intake-issue](./intake-issue.md) | 集約元 Issue のライフサイクル |
| 2 | [epic-issue](./epic-issue.md) | epic Issue（2 段階呼び出し: 要件確定 + 子 story 起票） |
| 3 | story-issue（未作成） | story Issue（2 段階呼び出し: 要件確定 + 子 subsystem 起票） |
| 4 | subsystem-issue（未作成） | subsystem Issue |
| 5 | epic-pr / story-pr / subsystem-pr（未作成） | 各レイヤーの Draft PR |

## 全体俯瞰

```mermaid
stateDiagram-v2
    [*] --> intake: ユーザーが Issue 起票
    intake --> epic: サブ Issue 起票
    intake --> story: サブ Issue 起票
    intake --> subsystem: サブ Issue 起票
    intake --> chore: サブ Issue 起票

    epic --> epic_pr: 要件確定 → epic Draft PR
    epic_pr --> complex_scenario: 複合UCシナリオ設計
    complex_scenario --> epic_return: 復帰 → 子 story 起票
    epic_return --> story

    story --> story_pr: 要件確定 → story Draft PR
    story_pr --> single_scenario: 単一UCシナリオ設計
    single_scenario --> story_return: 復帰 → 子 subsystem 起票
    story_return --> subsystem

    subsystem --> subsystem_pr: 要件確定 → subsystem Draft PR
    subsystem_pr --> impl: Wiki更新 → テスト → 実装
    impl --> review: レビュー
    review --> merged_sub: story にマージ

    merged_sub --> single_test: 全 subsystem 完了時
    single_test --> merged_story: pass → epic にマージ
    merged_story --> complex_test: 全 story 完了時
    complex_test --> merged_epic: pass → master にマージ
    merged_epic --> [*]: intake クローズ

    chore --> [*]: quick-implementer で直接マージ
```

---
template_version: 2.1.0
---

# エスカレーションのstoryレベル解決

subsystem レイヤーで解けない論点が story-conductor まで上がり、単一 UC シナリオの見直しで解決すると決まって、single-scenario-writer の修正を経て subsystem 側の設計が再開するまでの複合ユースケース。

E2E テストの位置付け: 決定が設計成果物の修正を伴う場合に、scenario-writer のシナリオ修正を経てから下位へ降りることの確認。

- 対応テストファイル: `tests/e2e/複合ユースケース/test_エスカレーションのstoryレベル解決.py`

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| sandbox リポ状態 | subsystem PR に `確認:architect` 付与済み・`## タスク一覧` 承認済み | SS設計 の途中 |
| 論点の埋込 | 単一 UC シナリオの前提が subsystem では満たせない状況を仕込む（シナリオが要求する同期処理を外部制約で実現できない） | subsystem では解決できない論点を誘発 |
| story PR | 単一 UC シナリオ確定済み・open | 修正対象 |
| ai-monitor 起動 | モニターが polling 中 | - |
| ユーザー役 | エスカレーションの指示、subsystem での中継選択、story レベルの解決案の選択を pytest が実施 | 各段で `議論中` 除去 + assignee 外し |

### フロー

```mermaid
flowchart TD
  A0([architect]) -->|subsystem では解決できない論点を検知・<br>確認:architect 除去 +<br>確認:subsystem-conductor +<br>エスカレーション報告| UC1

  subgraph FOCUS["検証対象: 2 段のエスカレーション → story レベルの決定 → シナリオ修正 → 設計再開"]
    UC1([エスカレーション対応:正常シナリオ<br>（方針確認）]) -->|選択肢提示 + 議論中 →<br>ユーザーが上位中継を選択| UC2([エスカレーション対応:正常シナリオ<br>（上位への中継）])
    UC2 -->|親 story Issue に<br>確認:story-conductor +<br>中継コメント| UC3([エスカレーション対応:正常シナリオ<br>（方針確認）])
    UC3 -->|選択肢提示 + 議論中 →<br>ユーザーがシナリオ変更を伴う<br>解決案を選択| UC4([エスカレーション対応:正常シナリオ<br>（シナリオ修正を伴う解決）])
    UC4 -->|story PR に<br>確認:single-scenario-writer +<br>修正指示コメント| UC5([単一シナリオ設計:正常シナリオ<br>（エスカレーション由来のシナリオ修正）])
    UC5 -->|シナリオ修正 commit +<br>確認:story-conductor + 完了報告| UC6([エスカレーション対応:正常シナリオ<br>（シナリオ修正完了後の決定通知）])
    UC6 -->|subsystem Issue に<br>確認:subsystem-conductor +<br>決定通知コメント| UC7([エスカレーション対応:正常シナリオ<br>（上位の決定の受領）])
    UC7 -->|subsystem PR に 確認:architect +<br>再開指示コメント| UC8([SS設計:正常シナリオ])
  end

  UC8 -->|設計 Wiki 確定 + タスク一覧チェック +<br>確認:tester 付与| DONE([subsystem PR: 確認:tester 付与済み])

  click UC1 "../単一ユースケース/エスカレーション対応.md#正常シナリオ方針確認"
  click UC2 "../単一ユースケース/エスカレーション対応.md#正常シナリオ上位への中継"
  click UC3 "../単一ユースケース/エスカレーション対応.md#正常シナリオ方針確認"
  click UC4 "../単一ユースケース/エスカレーション対応.md#正常シナリオシナリオ修正を伴う解決"
  click UC5 "../単一ユースケース/単一シナリオ設計.md#正常シナリオエスカレーション由来のシナリオ修正"
  click UC6 "../単一ユースケース/エスカレーション対応.md#正常シナリオシナリオ修正完了後の決定通知"
  click UC7 "../単一ユースケース/エスカレーション対応.md#正常シナリオ上位の決定の受領"
  click UC8 "../単一ユースケース/SS設計.md#正常シナリオ"
```

### 期待値

- 修正後の単一 UC シナリオの commit が story ブランチに積まれている
- story Issue 本文の `## ユースケース要件` が決定内容で更新されている
- 決定した方針に沿った設計 Wiki の commit が subsystem ブランチに積まれている
- epic Issue へのラベル付与・コメント投稿が一切発生していない（2 段で折り返している）
- 各段のエスカレーション関連コメントが全て Resolve 済み
- subsystem PR に `確認:tester` が付与され、エスカレーションで使った `確認:*`（story PR の `確認:single-scenario-writer` / subsystem Issue の `確認:subsystem-conductor`）がどこにも残っていない（設計再開後の通常フローが付ける確認ラベルは対象外）

## 異常シナリオ

なし

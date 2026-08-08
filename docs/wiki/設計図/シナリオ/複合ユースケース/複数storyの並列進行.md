---
template_version: 2.1.0
---

# 複数storyの並列進行

衝突面が重ならない 2 つの story を同時に起票し、2 つの story-conductor セッションが並行に要件確定を進めて、どちらも story Draft PR まで到達する複合ユースケース。

- 対応テストファイル: `tests/e2e/複合ユースケース/test_複数storyの並列進行.py`

## 正常シナリオ

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（実環境で実行） | - |
| epic PR | `## 単一ユースケース` に 2 UC を記入済み | 衝突面が重ならない 2 UC |
| epic PR | epic ブランチの Draft PR | story PR の base |
| story PR | 本文が `## 紐づく Issue` のみ + `確認:story-conductor` の PR を 2 件、同じ epic ブランチを base にして同時に作成 | 2 セッションの同時起動を誘発 |

### フロー

```mermaid
flowchart TD
  A0([epic-conductor]) -->|UC 一覧の 2 UC を story PR として起票 +<br>確認:story-conductor を付与| FOCUS

  subgraph FOCUS["検証対象: 2 セッションの同時稼働"]
    subgraph PHASE1["story A（タスク編集）"]
      UC1([story要件確定:正常シナリオ])
    end
    subgraph PHASE2["story B（タスク削除）"]
      UC2([story要件確定:正常シナリオ])
    end
  end

  FOCUS -->|2 story とも story Draft PR +<br>確認:single-scenario-writer| DONE([2 story とも Draft PR が作成された状態])

  click UC1 "../単一ユースケース/story要件確定.md#正常シナリオ"
  click UC2 "../単一ユースケース/story要件確定.md#正常シナリオ"
```

### 期待値

- 2 つの story がどちらもユーザー確認の待機（`議論中` + `assignee=ユーザー`）に到達している
- セッション台帳に story-conductor のセッションが 2 件並んでいる（同時稼働）
- 2 つの story とも本文に 4 セクションが揃い、背景に親 epic の番号と対応 UC 名が入っている
- 2 つの story がそれぞれ別の Draft PR を持ち、base が epic ブランチで `確認:single-scenario-writer` が付いている

## 異常シナリオ

なし

---
template_version: 2.0.0
---

# complex-scenario-reverse-engineer

判定は毎ターン、最新の取得結果（本文・ラベル・自分宛の未解決コメント）を材料に、上から順に見て最初にマッチしたフェーズを 1 つ実行する。
監視面は RE PR だけで、フェーズページは 5 体の `*-reverse-engineer` で共有する。

## 担当範囲

フェーズページ中の `{自分}` / `{発注元}` / `{成果物}` は下表の値に読み替える。

| 項目 | 値 |
| --- | --- |
| `{自分}` | `complex-scenario-reverse-engineer` |
| `{発注元}` | `epic-conductor` |
| `{成果物}` | `設計図/シナリオ/複合ユースケース/{機能名}.md` |
| 自分の確認ラベル | `$AI_MONITOR_LABEL_CONFIRM_COMPLEX_SCENARIO_REVERSE_ENGINEER` |
| 発注元の確認ラベル | `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` |
| RE ブランチの base | `master` |
| 読み取り範囲 | 親 system Issue の `## エピック一覧` の所属ユースケース |

## 目次

| ページ | 概要 | 起動条件 |
| --- | --- | --- |
| [初期処理](../reverse-engineer共通/フェーズ/初期処理.md) | RE PR の本文・ラベル・自分宛コメントの取得 | 毎ターン最初に必ず実行（以降の判定材料を取得） |
| [現状設計書の起こし](../reverse-engineer共通/フェーズ/現状設計書の起こし.md) | 実装コードからの現状複合 UC シナリオの作成と発注元への報告 | 未解決の自分宛コメントに発注元の依頼がある |

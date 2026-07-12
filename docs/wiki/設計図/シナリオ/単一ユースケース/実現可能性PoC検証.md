# 実現可能性PoC検証

epic-poc-runner が epic の成立条件になっている核心機構を最安直構成で検証し、結論を epic Issue 本文 `## PoC 結果` に記録する単一ユースケース。ライブラリ銘柄選定はしない（subsystem の architect が担当）。

対応モニター: `epic-poc-runner`

## 正常シナリオ

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | PoC Draft PR | 存在する（本文は `## 紐づく Issue` のみ）+ `確認:epic-poc-runner` 付与済み | - |
| 2 | assignee | 未設定 | モニター起動条件 |
| 3 | orchestrator | polling 中 | - |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant ORC as orchestrator

  Note over GH: PoC Draft PR 作成済み・<br>確認:epic-poc-runner 付与済み
  ORC-->>GH: polling（確認ラベル + assignee なし を検知）
  create participant MON as epic-poc-runner
  ORC->>MON: tmux セッション作成 + skill 起動
  participant REPO as リポジトリ
  activate MON
  MON->>GH: PoC PR 本文を現状情報で仮埋め<br>（リスク仮説 / 検証構成 / 成功条件の草案）
  MON->>GH: 不明点を PoC PR コメントで質問 +<br>議論中 付与 + assignee=ユーザー 設定
  deactivate MON

  loop 方針固めの応答ループ<br>（本文への修正依頼・質問回答がある間）
    U->>GH: PoC PR 本文を見ながら修正依頼 /<br>回答コメント + assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>GH: PoC PR 本文更新（検証構成・<br>成功条件を確定に近づける）+<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: PoC PR の 議論中 除去 +<br>assignee 外し（検証構成の確定）
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信
  activate MON
  MON->>GH: PoC PR の自分宛コメント一括 Resolve
  MON->>REPO: 検証コード実装 + push<br>（追加案が必要なら案ごとに追加 PoC PR 作成）
  MON->>REPO: 検証実行（サブエージェント並列）
  MON->>GH: 検証結果・最小再現コードを<br>PoC PR 本文に記録
  MON->>GH: PoC PR に結果報告コメント + 議論中 付与 +<br>assignee=ユーザー 設定
  deactivate MON

  loop 結果の応答ループ<br>（追加検証・案の変更要望がある間）
    U->>GH: PoC PR に追加検証の指示コメント +<br>assignee 外し
    ORC-->>GH: polling（ユーザー返信 + assignee なし を検知）
    ORC->>MON: 既存セッションへ送信
    activate MON
    MON->>REPO: 追加検証実行
    MON->>GH: 結果を PoC PR 本文に追記 +<br>assignee=ユーザー 再設定
    deactivate MON
  end

  U->>GH: PoC PR の 議論中 除去 + assignee 外し
  ORC-->>GH: polling（議論中 除去 + assignee なし を検知）
  ORC->>MON: 既存セッションへ送信（完了処理）
  activate MON
  MON->>GH: PoC PR の自分宛コメント一括 Resolve
  MON->>GH: 親 epic Issue 本文に PoC 結果 サマリ記録
  MON->>GH: 確認:epic-poc-runner 除去<br>（PoC PR・ブランチは保持）
  MON->>GH: epic Issue に 確認:epic-conductor 付与
  MON->>GH: epic Issue に完了報告コメント<br>（@epic-conductor 宛・<br>確認後の Resolve 依頼付き）
  deactivate MON
  Note over MON: セッションは PoC PR close まで常駐
```

**期待動作:**
- epic Issue 本文に `## PoC 結果`（検証構成 / 成功条件 / 結果 / PoC PR リンク）が記録されている
- PoC PR は open のまま `確認:epic-poc-runner` だけが除去されている
- epic Issue に `確認:epic-conductor` が付与され、完了報告コメント（@epic-conductor 宛・未解決）が投稿されている
- PoC PR の自分宛コメントが全て Resolve 済み

### 補足

- PoC コードは main にマージしない（コードは捨てる・知見は残す）
- Wiki 外部ライブラリページは書かない（採用確定した subsystem の architect が書く）

## 異常シナリオ（核心機構が成立しない結論）

### 前提条件

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | 検証実行まで完了 | 検証実行の結果、成功条件を満たさない | 全案 ❌ |

### 図

```mermaid
sequenceDiagram
  actor U as ユーザー
  participant GH as GitHub
  participant MON as epic-poc-runner

  MON->>GH: 全案 ❌ の実測値を PoC PR 本文に記録
  MON->>GH: PoC PR に不成立の結論 +<br>代替案 or 中止の相談コメント +<br>議論中 付与 + assignee=ユーザー 設定
  alt 代替案あり
    Note over U: 代替構成の指示 + assignee 外し<br>→ 正常シナリオの検証ステップに戻る
  else 中止
    Note over U: 確認:resetter 付与（中止）
  end
```

**期待動作:**
- 不成立の実測値と理由が PoC PR 本文 + epic Issue `## PoC 結果` に記録される
- epic を進めるか中止するかはユーザー判断（epic-poc-runner は勝手にクローズしない）

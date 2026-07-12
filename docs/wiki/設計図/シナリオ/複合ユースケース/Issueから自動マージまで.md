# Issueから自動マージまで

ai-monitor のメインフロー: 監視対象プロジェクトに新規機能相当の Issue が起票されてから、intake → epic → story → subsystem を経て master にマージされるまでの複合ユースケース。

**E2E テストの位置付け:** ai-monitor プラグイン + オーケストレーターの全モニターを一気通しで動作確認する最上位シナリオ。実行時間は数十分〜数時間規模、Claude Code Max プランで無料実行、`pytest -m e2e_full` タグ付きで手動起動のみ。

## 正常シナリオ

### 前提条件

シナリオは DB Factory ではなく **sandbox GitHub リポの初期状態** + **ai-monitor プロセスの起動状態** を前提として扱う。

| No | セットアップ | 説明 | 補足 |
| --- | --- | --- | --- |
| 1 | sandbox リポ存在 | `shuhei1101/ai-monitor-e2e` が存在し空プロジェクト状態 | Pages 有効 |
| 2 | ai-monitor プラグイン | marketplace 経由でインストール済み（user scope）かつ **最新版に更新済み** | `/plugin marketplace update ai-monitor` → 未インストールなら `/plugin install ai-monitor@ai-monitor`。tmux 内の `claude "/ai-monitor:{skill}"` が前提 |
| 3 | ラベル定義 | `AI_MONITOR_LABEL_*` 全てが `gh label create` 済み | `plugins/ai-monitor/constants.env` から一括作成 |
| 4 | Wiki 配置 | sandbox に `docs/wiki/` 一式が存在 | ai-monitor 本体からコピー |
| 5 | ai-monitor 起動 | orchestrator が sandbox を polling 中 | `.env` に E2E プロジェクト宣言済み |
| 6 | ユーザーログイン | `gh auth status` OK、sandbox に対して write 権限 | テスト実行者 |
| 7 | 過去テスト残骸なし | sandbox の open Issue / open PR / worktree が全て clean | 前回テストの teardown 完了 |

### 図

```mermaid
flowchart TD
  U0([ユーザー: 監視対象リポで Issue 起票 + 確認:intake ラベル付与])

  subgraph P1["intake 分解フェーズ"]
    direction TB
    P1_S1([Issue コメント: サブ Issue 案・assignee=ユーザー])
    P1_S2([Issue: フェーズ終了 付与 by ユーザー])
    P1_S3([Sub-issue: layer:epic Issue 作成済み])
  end

  subgraph P2["epic 要件確定フェーズ"]
    direction TB
    P2_S1([epic Issue コメント: 要件確定草案・assignee=ユーザー])
    P2_S2([epic Issue: 確認:epic-pr-initializer 付与])
    P2_S3([epic Draft PR 作成済み・base=master・確認:complex-scenario-writer 付与])
  end


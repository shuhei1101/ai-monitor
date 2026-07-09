---
name: gh-kit:intake-issue-triage
description: Issue の内容を作業単位に分解し、epic / story / subsystem / chore のサブ Issue 案をユーザー承認後に Sub-issue として起票する
argument-hint: "[issue-number]"
arguments: "issue_number"
---

# intake-issue-triage

## 入力

- Issue 番号: $issue_number

## 使用する定数

- フェーズ終了ラベル: !`echo "$GH_KIT_LABEL_PHASE_END"`

## コメント返信ルール（共通）

!`python "${CLAUDE_PLUGIN_ROOT}/scripts/gh/read_urls.py" "${WIKI_BASE}/規約/コメント.md"`

## レイヤー判定フローチャート

!`python "${CLAUDE_PLUGIN_ROOT}/scripts/gh/read_urls.py" "${WIKI_BASE}/判定フローチャート/レイヤー.md"`


## 起動判定

Issue の状態を確認して、実行するフェーズを 1 つ選ぶ。

MCP `get_issue` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false

| 状態 | 実行フェーズ |
| --- | --- |
| ラベル `フェーズ終了` が付いている | フェーズ C（サブ Issue 起票 + 終了処理) |
| 自分宛のコメントが 1 件以上ある | フェーズ B（応答ループ） |
| それ以外 | フェーズ A（初回判定） |


## フェーズ A: 初回判定

### A1. Issue の内容を作業単位に分解

Issue の本文を読み、含まれる作業を独立したスコープごとに分解する。

- 依存関係 or 共通目的あり → 1 サブ Issue にまとめる
- 独立した機能 / 目的が混在 → 別サブ Issue に分割
- 迷ったら「同じ PR ツリーで進行するか」で判断

### A2. 各作業について種別を判定

各作業について、判定フローチャートに沿って以下の種別を割り当てる。判定結果ごとに **サブ Issue に付与するラベル**:

- 複合ユースケースシナリオに影響あり → epic
  - `layer:*`: !`echo "$GH_KIT_LABEL_LAYER_EPIC"`
  - `確認:*`: !`echo "$GH_KIT_LABEL_CONFIRM_EPIC_ISSUE_TRIAGE"`
- 単一ユースケースシナリオに影響あり → story
  - `layer:*`: !`echo "$GH_KIT_LABEL_LAYER_STORY"`
  - `確認:*`: !`echo "$GH_KIT_LABEL_CONFIRM_STORY_ISSUE_TRIAGE"`
- 実装のみ（シナリオ不変）→ subsystem
  - `layer:*`: !`echo "$GH_KIT_LABEL_LAYER_SUBSYSTEM"`
  - `確認:*`: !`echo "$GH_KIT_LABEL_CONFIRM_SUBSYSTEM_ISSUE_TRIAGE"`
- 軽微な修正 → chore
  - `layer:*`: !`echo "$GH_KIT_LABEL_LAYER_CHORE"`
  - `確認:*`: !`echo "$GH_KIT_LABEL_CONFIRM_QUICK_IMPLEMENTER"`

### A3. Issue に type / layer ラベル付与

Issue には集約元を示す `layer:intake` と type ラベルを付ける。

#### layer ラベル

- !`echo "$GH_KIT_LABEL_LAYER_INTAKE"`

#### type ラベル

以下から 1 つ判定して付与する:

- 既存の動作が仕様または期待と異なる問題の修正: !`echo "$GH_KIT_LABEL_TYPE_BUG"`
- 新機能追加・既存機能の有意な拡張: !`echo "$GH_KIT_LABEL_TYPE_FEAT"`
- 外部動作を変えずにコードを整理・改善: !`echo "$GH_KIT_LABEL_TYPE_REFACTOR"`
- ドキュメント・コメントのみの変更: !`echo "$GH_KIT_LABEL_TYPE_DOCS"`
- ビルド設定・依存更新・CI/CD など: !`echo "$GH_KIT_LABEL_TYPE_CHORE"`
- テストコードの追加・修正のみ: !`echo "$GH_KIT_LABEL_TYPE_TEST"`

MCP `add_labels` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `labels`:
  - !`echo "$GH_KIT_LABEL_LAYER_INTAKE"`
  - {判定した type ラベル値}

### A4. サブ Issue 案の提示

判定結果を全件まとめてユーザーに提示する。

MCP `comment` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `intake-issue-triager`
- `receivers`:
  - {ユーザーログイン名}（`gh api user --jq '.login'` で取得）
- `title`: `サブ Issue 案`
- `body`:
  ```
  Issue の内容を以下の通り分解しました。

  | No | 種別 | タイトル案 | 概要 |
  | --- | --- | --- | --- |
  | 1 | {epic/story/subsystem/chore} | {タイトル案} | {概要} |
  | 2 | ... | ... | ... |

  - 問題なければ `フェーズ終了` ラベル付与 → 承認された案で Sub-issue として起票
  - 修正が必要なら assignee を外してフィードバックコメントを記入
  ```

### A5. ユーザーへの質問投稿

以下の観点から、今回の Issue に該当するものだけを抽出し、AI 側で推奨案を用意して MCP `ask_questions` で投稿する。

| 観点 | 質問 | 選択肢例 | 推奨 |
| --- | --- | --- | --- |
| 要件間の整合性 | 「A と B が矛盾するように読めます。どちらを優先しますか？」 | A. {要件A を優先} / B. {要件B を優先} / C. 両立させる方法を検討 | A |
| スコープ境界 | 「〜も含めますか？」 | A. 含めない（今回スコープ外） / B. 含める | A |
| 既存機能との関係 | 「既存の {類似機能} との扱いは？」 | A. 統合する / B. 別立てで併存 / C. 既存を廃止して置き換え | B |
| 廃止・置換の意図 | 「既存の {既存機能} は？」 | A. 併存 / B. 段階的廃止（新規は新機能、既存はそのまま） / C. 即時廃止 | A |
| 優先順序 / 完了順 | 「複数作業のどれから完了させたいですか？」 | A. {No.1 の作業から} / B. {No.2 の作業から} / C. 並行で進める | A |
| 前提条件の妥当性 | 「「〜がある前提」ですが、その前提は満たされていますか？」 | A. 満たされている / B. 満たされていない（先に {対応} が必要） | A |
| 依存 Issue / PR | 「依存する Issue / PR はありますか？」 | A. なし / B. あり（#{番号}） | A |
| バグ再現条件（type:bug 時） | 「再現手順・環境の理解は合っていますか？」 | A. 合っている / B. 追加条件がある（{条件}） | A |
| 影響ユーザー / アクター | 「影響を受けるユーザー範囲は？」 | A. 全ユーザー / B. 特定ロール（{ロール}）のみ / C. 一部条件（{条件}）に該当するユーザー | A |
| 想定タイムライン | 「いつまでに完了させたい想定ですか？」 | A. 特に指定なし / B. 今週中 / C. 今月中 / D. 次リリース | A |
| 非機能要件の存在 | 「セキュリティ / 性能 / 対応環境 で気にすべきことはありますか？」 | A. なし（デフォルト方針で OK） / B. あり（{内容}） | A |
| 用語の意味 | 「本文の「{用語}」は {案 X} の意味ですか？」 | A. {案 X} で合っている / B. {案 Y} が正しい | A |
| 対応方針の代替案 | 「対応方針の候補は？」 | A. {案 A の要約} / B. {案 B の要約} / C. その他 | A |


MCP `ask_questions` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `intake-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: `確認事項`
- `intro`: `以下の点についてご確認ください。記号（例: `A`）で返信いただければ、その方針で進めます。`
- `questions`: 上記観点表から抽出

### A6. assignee 設定

MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ B: 応答ループ

### B1. 自分宛の未処理コメントを取得

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `intake-issue-triager`
- `include_resolved`: false

### B2. コメント内容に応じて返信 / 案の修正

| 内容 | 対応 |
| --- | --- |
| サブ Issue 案の修正指示 | 案を更新して「案を {変更後} に修正しました」と短く追記 |
| 案の追加・削除・統合要望 | 案を更新して短く追記 |
| 不明確な指示・複数解釈可能 | 「この理解で合っていますか？」と確認の追記 |
| 妥当性に疑問がある指示 | 「ご指摘の方法だと {懸念点}。代替案として {案} はいかがでしょうか？」と返す |
| 質問 | 質問に回答するのみ、案は触らない |

案の内容変更は Issue 本文には反映しない（案はコメント上の議論として管理し、承認後にフェーズ C で起票する）。

追記は MCP `reply_comment` を呼ぶ:
- `comment_node_id`: 返信対象コメントの node_id
- `sender`: `intake-issue-triager`
- `receivers`:
  - {ユーザーログイン名}
- `title`: 短い要約
- `body`: 返信本文

### B3. assignee 再設定

MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略


## フェーズ C: サブ Issue 起票 + 終了処理（`フェーズ終了` 付与起動）

### C1. 自分宛コメントを取得 + Resolve 判定

MCP `list_addressed_comments` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `addressee`: `intake-issue-triager`
- `include_resolved`: false

| 対象 | 扱い |
| --- | --- |
| 自身が投稿 → ユーザーが回答済 or 議論完了 | Resolve 対象 |
| 自身が投稿 → ユーザー未回答（選択肢提示・確認要求など） | Resolve NG |
| ユーザー → `@intake-issue-triager` 宛（AI 側が対応済） | Resolve 対象 |

Resolve NG が残る場合はフェーズ B に戻ってユーザーに確認質問を投げる。

### C2. 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: C1 で Resolve 対象に選別したコメントの `node_id` 配列

### C3. サブ Issue を Sub-issue として起票

承認された案を Issue の Sub-issue として **件数分** 起票する。詳細な本文は書かず、子モニターが起動時に `parent` メタデータで親を辿って埋める。1 件ごとに MCP `create_child_issue` を呼ぶ:
- `parent_issue_number`: $issue_number
- `title`: 案のタイトル
- `body`: 空文字
- `labels`:
  - A2 で判定した種別に応じた `layer:*` 値
  - A2 で判定した種別に応じた `確認:*` 値

### C4. ラベル更新 + assignee 除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - !`echo "$GH_KIT_LABEL_CONFIRM_INTAKE_ISSUE_TRIAGE"`
  - !`echo "$GH_KIT_LABEL_PHASE_END"`
- `add_labels_`:
  - （なし。役割を終えるので次ラベルなし）

続けて MCP `remove_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `login`: 省略

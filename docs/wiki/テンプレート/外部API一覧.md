# ai-monitor 規約: 外部API一覧

採用済み外部 API のインデックス。
各 API の詳細 Wiki (`docs/wiki/外部API/{API名}.md`) へのリンクと、どこで使われているかの索引を兼ねる。

配置先は `docs/wiki/外部API/README.md`（固定）。
`docs/wiki/外部API/{API名}.md` を新規作成したら必ずここに 1 行追加する。

## セクション一覧

| セクション | サブセクション | 必須or条件 | 担当 | 補足 |
| --- | --- | --- | --- | --- |
| `# 外部API一覧` の表 | - | 必須 | issue-arch / issue-ui | - |

## `# 外部API一覧` の表

### 記述例

````markdown
# 外部API一覧

| API 名 | 概要 | 使用箇所 | 補足 |
| --- | --- | --- | --- |
| [OpenAI](./OpenAI.md) | LLM 応答生成・埋め込み生成 | `integrations/openai/chat.ts`, `integrations/openai/embed.ts` | - |
| [SendGrid](./SendGrid.md) | トランザクションメール送信 | `integrations/sendgrid/notify.ts` | - |
| [Stripe](./Stripe.md) | サブスクリプション課金 | `integrations/stripe/billing.ts` | - |
````

### 補足

**API 名列:**
- 各 API の詳細 Wiki ページ `./{API名}.md` への内部リンク（`[表示名](./{API名}.md)`）

**概要列:**
- 1 行で「何をする API か」を要約。
  詳細は個別ページに書く

**使用箇所列:**
- このプロジェクトで API を呼び出しているファイル / モジュール
- 複数あればカンマ区切り、リポジトリルートからの相対パスで書く

**補足:**
- 新規 API を採用して `./{API名}.md` を作成したら必ずこのページに 1 行追加する
- API を廃止して詳細 Wiki を削除する際はこの一覧からも該当行を削除する（`reset` エージェントが追従）
- 順序は採用日順（新しいものを下に追記）

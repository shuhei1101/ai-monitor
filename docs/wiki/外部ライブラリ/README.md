# 外部ライブラリ

採用済みの外部ライブラリ / 外部ツールのインデックス。
書き方規約は `テンプレート/外部ライブラリ.md` 参照。

## 一覧

| ライブラリ | リンク | 用途 | 補足 |
| --- | --- | --- | --- |
| githubkit | [githubkit](./githubkit.md) | エージェント / モニターの GitHub 操作（REST + GraphQL） | - |
| FastAPI | [FastAPI](./fastapi.md) | モニター本体のアプリ基盤（HTTP 受信 + lifespan でのループ駆動） | 起動サーバーは uvicorn |
| gh（GitHub CLI） | [gh](./gh.md) | セッションフックのリポジトリ情報取得 | Python ライブラリではなく CLI |
| tmux | [tmux](./tmux.md) | エージェントセッションの実体操作（作成 / 送信 / 生存確認 / kill） | Python ライブラリではなく CLI |

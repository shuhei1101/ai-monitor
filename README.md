# ai-monitor

## 1. ディレクトリ構成

```
ai-monitor/
├── .claude-plugin/
│   └── marketplace.json                     # マーケットプレイスカタログ
├── plugins/
│   └── ai-monitor/                          # 唯一のプラグイン
│       ├── .claude-plugin/plugin.json       # プラグインマニフェスト
│       ├── agents/                          # サブエージェント定義
│       ├── hooks/                           # SessionStart / PreCompact フック
│       ├── inject/                          # Wiki 取得・索引組み立て（モニターと共有）
│       └── constants.env                    # ラベル等の静的定数（SoT・bash / python 両対応）
├── config/agent_phases.yaml                 # エージェント名 → フェーズページ一覧
├── src/ai_monitor/                          # モニター（Python デーモン）+ MCP サーバー
├── docs/wiki/                               # 設計ドキュメント（GitHub Pages 公開）
└── settings.yaml.example                    # 共通設定サンプル（github_token + 監視対象プロジェクト宣言）
```

## 2. セットアップ

### 2.1. 共通設定の作成

モニターとエージェントセッションが共用する設定を `~/.config/ai-monitor/settings.yaml` に置く。
本リポジトリ直下ではなくホーム配下に置くのは、監視対象プロジェクトの worktree で動くエージェントセッションと E2E テストが同じファイルを参照するため:

```bash
mkdir -p ~/.config/ai-monitor
cp settings.yaml.example ~/.config/ai-monitor/settings.yaml
```

編集する項目:

| キー | 内容 | 補足 |
| --- | --- | --- |
| `github_token` | fine-grained PAT | 監視対象の全リポジトリに Issues / Pull requests / Contents の RW を付与する |
| `projects[]` | 監視対象プロジェクト | `name` / `repo`（`owner/name`）/ `local_path` / `wiki_base` を宣言 |
| `agents[]` | エージェント別のモデル | 全エージェント分のエントリが必須（欠落・空値は起動エラー） |

監視対象にするプロジェクトは、`repo` に対応する GitHub リモート（`origin`）を持っている必要がある。
SessionStart フックが CWD の git remote と `projects[].repo` を突き合わせて `REPO_SLUG` / `WIKI_BASE` / `AI_MONITOR_WIKI_BASE` を展開するため。

キーの一覧は [設計図/設定](./docs/wiki/設計図/設定/) 参照。

### 2.2. マーケットプレイス追加

```bash
# Git URL で追加
/plugin marketplace add https://github.com/shuhei1101/ai-monitor.git

# ローカルクローン済みならパスで追加
/plugin marketplace add ~/repo/ai-monitor
```

### 2.3. プラグインインストール

```bash
# User scope（全プロジェクトで有効）
/plugin install ai-monitor@ai-monitor

# Project scope（このリポジトリの全コラボレーターに共有）
claude plugin install ai-monitor@ai-monitor --scope project
```

インストール後 `/reload-plugins` で反映。

### 2.4. 監視対象プロジェクト側の設定

監視対象プロジェクトの `.claude/settings.json` に、inject-rules が読むルール索引を宣言する:

```json
{
  "env": {
    "INJECT_RULES_INDEXES": "https://raw.githubusercontent.com/shuhei1101/my-plugins/master/docs/rules.yaml,https://raw.githubusercontent.com/shuhei1101/ai-monitor/master/docs/rules.yaml,https://raw.githubusercontent.com/{owner}/{監視対象プロジェクト}/master/docs/rules.yaml"
  }
}
```

| 索引 | 内容 |
| --- | --- |
| my-plugins の `rules.yaml` | 言語 / フレームワーク横断のコーディング規約（dev-kit） |
| ai-monitor の `rules.yaml` | 設計ドキュメントの書式テンプレートと横断規約。全プロジェクトで共有する |
| 監視対象プロジェクト自身の `rules.yaml` | そのプロジェクト固有の規約 |

テンプレートと横断規約は ai-monitor 側を 1 箇所の SoT として共有する。
エージェントも実行時に `AI_MONITOR_WIKI_BASE`（ai-monitor の Wiki）から読む。

ai-monitor 自身の開発でしか使わないルール（エージェント定義・フェーズページ・組織図）は `docs/rules.self.yaml` に分けてあり、監視対象プロジェクトからは参照しない。

プロジェクト側の `docs/rules.yaml` は system-architect が土台生成時に空の索引として作る（依頼元は system-conductor）（プロジェクト固有の規約ができたときに追記する）。

設定できたかは、対象プロジェクトでセッションを開いたときの `ai-monitor: 監視対象 {repo} として解決しました` の 1 行で確認する。
`監視対象として解決できませんでした` が出た場合は `projects[]` の登録か git remote を見直す。

### 2.5. GitHub ラベルの作成

`constants.env` が持つ全ラベル（`確認:*` / `処理中:*` / `layer:*` / `議論中` 等）を対象リポジトリに作成する:

```bash
# settings.yaml の projects[] 全件に作成
PYTHONPATH=src uv run python -m ai_monitor.setup_labels

# リポジトリを指定して作成
PYTHONPATH=src uv run python -m ai_monitor.setup_labels --repo owner/name
```

既存ラベルは色・説明のみ更新する（冪等）。
エージェントを追加してラベルが増えたときも同じコマンドで追随する。

### 2.6. モニターの起動

```bash
PYTHONPATH=src uv run python -m ai_monitor
```

起動すると監視役（`python -m ai_monitor.watchdog`）も一緒に立ち上がり、以降は互いの生存を見張る。
片方が落ちたらもう片方が再起動し、Webhook へ通知する（一定期間内の再起動が上限に達したら通知だけになる。設定は `watchdog`）。

`projects[]` を書き換えたときは再起動が必要。
エージェントはモニターが tmux セッションとして起動する（手動でのスキル呼び出しは行わない）。
どのフェーズページを起動プロンプトに載せるかは [`config/agent_phases.yaml`](./config/agent_phases.yaml) が持つ。

Claude Code から tmux 上で起動・再起動する手順は [`CLAUDE.md`](./CLAUDE.md) にある。

### 2.7. ログの見方

モニターとエージェントのログは OTel Collector へ送っており、バックエンドの UI で検索する（手順は `docs/wiki/設計図/シナリオ/単一ユースケース/ログ確認.md`）。

| 見たいもの | 場所 |
| --- | --- |
| モニター / エージェントのログ | OTel バックエンド（`ai_monitor.project` / `ai_monitor.agent` / `ai_monitor.number` 属性で絞る） |
| uvicorn のアクセスログとプロセスの異常終了 | `data/monitor.log`（追記。再起動しても消えない） |
| 監視役のログ | `data/watchdog.log` |
| tmux セッションの画面 | `tmux capture-pane -p -t ai-monitor-server -S -100` |
| 再起動の履歴 | `data/restarts.yaml` |

## 3. リンク

| リソース | URL |
| --- | --- |
| プラグイン公式ドキュメント | https://code.claude.com/docs/ja/plugins |
| マーケットプレイス公式ドキュメント | https://code.claude.com/docs/ja/plugin-marketplaces |

# ai-monitor

GitHub Issue/PR を **tmux + Claude Code + gh CLI** で自動オーケストレーションするワークフロー基盤。
1 リポジトリに **2 つの顔** を持つ:

1. **Claude Code プラグインマーケットプレイス**（`.claude-plugin/marketplace.json`）
   - 監視対象プロジェクトから利用する skill / agent / hook / MCP を配布
2. **Python 製オーケストレーター**（`src/ai_monitor/`）
   - tmux セッション管理・GitHub polling・状態永続化・MCP HTTP callback

---

## 1. ディレクトリ構成

```
ai-monitor/
├── .claude-plugin/
│   └── marketplace.json                     # マーケットプレイスカタログ
├── plugins/
│   └── ai-monitor/                          # 唯一のプラグイン
│       ├── .claude-plugin/plugin.json       # プラグインマニフェスト
│       ├── skills/                          # /ai-monitor:{monitor} スキル群
│       ├── agents/                          # サブエージェント定義
│       ├── hooks/hooks.json                 # SessionStart / PreToolUse フック
│       ├── mcp/server.py                    # gh 操作 MCP サーバ (ai-monitor-tools)
│       ├── scripts/                         # gh ヘルパー
│       ├── constants.env                    # ラベル等の静的定数（SoT・bash / python 両対応）
│       └── .mcp.json                        # MCP 起動定義
├── src/ai_monitor/                          # Python オーケストレーター（別プロセス）
│   ├── features/  integrations/  runtime/  server/  shared/
│   └── main.py
├── docs/wiki/                               # 設計ドキュメント（GitHub Pages 公開）
├── prompts/                                 # tmux 初期起動プロンプト
├── tests/
├── CLAUDE.md                                # ワークフロー全体設計（大元）
├── .env.example                             # 監視対象プロジェクト宣言サンプル
└── pyproject.toml
```

---

## 2. プラグイン利用（監視対象プロジェクト側）

### 2.1. マーケットプレイス追加

```bash
# Git URL で追加
/plugin marketplace add https://github.com/shuhei1101/ai-monitor.git

# ローカルクローン済みならパスで追加
/plugin marketplace add ~/repo/ai-monitor
```

### 2.2. プラグインインストール

```bash
# User scope（全プロジェクトで有効）
/plugin install ai-monitor@ai-monitor

# Project scope（このリポジトリの全コラボレーターに共有）
claude plugin install ai-monitor@ai-monitor --scope project
```

インストール後 `/reload-plugins` で反映。

### 2.3. skill 呼び出し

```bash
/ai-monitor:intake-issue-triage 42
/ai-monitor:epic-issue-triage 43
/ai-monitor:story-issue-triage 44
```

skill 一覧は [`plugins/ai-monitor/skills/`](./plugins/ai-monitor/skills/) 配下参照。

### 2.4. 開発中プラグインの動作確認

再インストール不要でローカル編集を即反映する場合:

```bash
claude --plugin-dir ~/repo/ai-monitor/plugins/ai-monitor
```

編集後は `/reload-plugins` で反映。

---

## 3. オーケストレーター利用（ai-monitor 本体側）

### 3.1. セットアップ

```bash
cd ~/repo/ai-monitor
cp .env.example .env
# .env を編集: AI_MONITOR_PROJECT_{NAME}_{REPO,LOCAL_PATH,WIKI_BASE} を宣言
uv sync
```

### 3.2. 起動

```bash
uv run ai-monitor            # FastAPI サーバ + polling + tmux 管理
```

### 3.3. 動作

- `.env` 宣言の各プロジェクトを polling
- 対象ラベル（`確認:{monitor-name}` 系）が付いた Issue/PR を検出
- 対応する tmux セッションを **監視対象プロジェクトの worktree 上で** 起動:

```bash
tmux new-session -d \
  -s "ai-monitor-{project}-{monitor}-{no}" \
  -c "{monitored_project_worktree}"
tmux send-keys -t "{session}" \
  'claude "/ai-monitor:{monitor} {no}"' Enter
```

- Claude Code は同ディレクトリの MCP サーバ（`ai-monitor-tools`）経由で gh 操作を実行
- 完了時 MCP HTTP `report_completion` で orchestrator に通知 → tmux 終了

---

## 4. 開発

### 4.1. プラグイン部分の編集

`plugins/ai-monitor/` 配下を編集し、以下で確認:

```bash
# 監視対象プロジェクトから開発中プラグインを直接ロード
cd /path/to/target-project
claude --plugin-dir ~/repo/ai-monitor/plugins/ai-monitor
```

### 4.2. Python オーケストレーターの編集

`src/ai_monitor/` を編集し、以下で確認:

```bash
uv run pytest
uv run ai-monitor
```

### 4.3. Wiki の編集

`docs/wiki/` 配下は GitHub Pages で公開されている（`https://shuhei1101.github.io/ai-monitor/`）。
skill の SKILL.md は raw URL 経由で Wiki を参照するため、master push で自動反映。

### 4.4. コンポーネント間の呼び出し

- Wiki → skill: raw URL fetch（`${WIKI_BASE}/...`）
- skill → MCP: `.mcp.json` の `ai-monitor-tools`
- skill → 定数: `${AI_MONITOR_LABEL_*}` 環境変数（SessionStart フックの `load-constants.sh` が `constants.env` を `CLAUDE_ENV_FILE` 経由で展開）
- skill → gh スクリプト: `${CLAUDE_PLUGIN_ROOT}/scripts/gh/*.py`

---

## 5. リンク

| リソース | URL |
| --- | --- |
| GitHub Pages（Wiki） | https://shuhei1101.github.io/ai-monitor/ |
| ワークフロー全体設計 | [CLAUDE.md](./CLAUDE.md) |
| 設計ドキュメント | [docs/wiki/](./docs/wiki/) |
| プラグイン公式ドキュメント | https://code.claude.com/docs/ja/plugins |
| マーケットプレイス公式ドキュメント | https://code.claude.com/docs/ja/plugin-marketplaces |

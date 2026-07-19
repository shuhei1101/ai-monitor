# ai-monitor

GitHub Issue/PR を **tmux + Claude Code** で自動オーケストレーションするワークフロー基盤。
1 リポジトリに **2 つの顔** を持つ:

1. **Claude Code プラグインマーケットプレイス**（`.claude-plugin/marketplace.json`）
   - 監視対象プロジェクトから利用する skill / agent / hook を配布
2. **設計ドキュメント（`docs/wiki/`）**
   - ワークフロー全体設計・モニター（Python デーモン）・GitHub 操作 MCP サーバーの設計 SoT
   - 実装は仕様駆動（docs → 実装）で、この設計に沿って進める

---

## 1. ディレクトリ構成

```
ai-monitor/
├── .claude-plugin/
│   └── marketplace.json                     # マーケットプレイスカタログ
├── plugins/
│   └── ai-monitor/                          # 唯一のプラグイン
│       ├── .claude-plugin/plugin.json       # プラグインマニフェスト
│       ├── skills/                          # /ai-monitor:{agent} スキル群
│       ├── agents/                          # サブエージェント定義
│       ├── hooks/hooks.json                 # SessionStart / PreToolUse フック
│       ├── scripts/                         # Wiki 取得等のヘルパースクリプト
│       └── constants.env                    # ラベル等の静的定数（SoT・bash / python 両対応）
├── docs/wiki/                               # 設計ドキュメント（GitHub Pages 公開）
├── CLAUDE.md                                # ワークフロー全体設計（大元）
└── settings.yaml.example                    # 共通設定サンプル（github_token + 監視対象プロジェクト宣言）
```

---

## 2. セットアップ

### 2.1. 共通設定の作成

モニターとエージェントセッションが共用する設定を `~/.config/ai-monitor/settings.yaml` に置く:

```bash
mkdir -p ~/.config/ai-monitor
cp settings.yaml.example ~/.config/ai-monitor/settings.yaml
# settings.yaml を編集: github_token と projects[]（name / repo / local_path / wiki_base）を宣言
```

- SessionStart フックが CWD の git remote と `projects[].repo` を突き合わせて `WIKI_BASE` / `REPO_SLUG` を展開する
- settings.yaml が無い・プロジェクト未登録のリポジトリでは、警告のみでスキップされる（セッションは通常どおり開ける）
- キーの一覧は [設計図/設定](./docs/wiki/設計図/設定/) 参照

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

### 2.4. skill 呼び出し

```bash
/ai-monitor:intake-issue-triage 42
/ai-monitor:epic-conductor 43
/ai-monitor:story-conductor 44
```

skill 一覧は [`plugins/ai-monitor/skills/`](./plugins/ai-monitor/skills/) 配下参照。

---

## 3. モニター / MCP サーバー

モニター（GitHub polling + tmux セッション管理の Python デーモン）と GitHub 操作 MCP サーバーは、`docs/wiki/` の設計に沿って実装する:

- 実行モデル・エージェント編成: [CLAUDE.md](./CLAUDE.md)
- モジュール構成: [設計図/モジュール構成](./docs/wiki/設計図/モジュール構成/)
- MCP ツールのインターフェース: [設計図/バックエンド結合](./docs/wiki/設計図/バックエンド結合/)
- 設定: [設計図/設定](./docs/wiki/設計図/設定/)

---

## 4. 開発

### 4.1. プラグイン部分の編集

`plugins/ai-monitor/` 配下を編集し、以下で確認:

```bash
# 監視対象プロジェクトから開発中プラグインを直接ロード
cd /path/to/target-project
claude --plugin-dir ~/repo/ai-monitor/plugins/ai-monitor
```

編集後は `/reload-plugins` で反映。

### 4.2. Wiki の編集

`docs/wiki/` 配下は GitHub Pages で公開されている（`https://shuhei1101.github.io/ai-monitor/`）。
skill の SKILL.md は raw URL 経由で Wiki を参照するため、master push で自動反映。

### 4.3. コンポーネント間の呼び出し

- Wiki → skill: raw URL fetch（`${WIKI_BASE}/...`）
- skill → 定数: `${AI_MONITOR_LABEL_*}` 環境変数（SessionStart フックの `load-constants.sh` が `constants.env` と settings.yaml を `CLAUDE_ENV_FILE` 経由で展開）
- skill → ヘルパースクリプト: `${CLAUDE_PLUGIN_ROOT}/scripts/gh/read_urls.py` / `${CLAUDE_PLUGIN_ROOT}/scripts/read_agent_docs.py`

---

## 5. リンク

| リソース | URL |
| --- | --- |
| GitHub Pages（Wiki） | https://shuhei1101.github.io/ai-monitor/ |
| ワークフロー全体設計 | [CLAUDE.md](./CLAUDE.md) |
| 設計ドキュメント | [docs/wiki/](./docs/wiki/) |
| プラグイン公式ドキュメント | https://code.claude.com/docs/ja/plugins |
| マーケットプレイス公式ドキュメント | https://code.claude.com/docs/ja/plugin-marketplaces |

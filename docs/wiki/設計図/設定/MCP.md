# 設定: MCP

`MCP`（エージェントセッション側）の設定値一覧。

- モニターと同じ `~/.config/ai-monitor/settings.yaml` を直接読む（全キーの一覧は `設計図/設定/モニター.md` 参照。本ページは MCP セッションが使うキーのみ）
- 環境差分の読み込み（`AI_MONITOR_ENV` で `settings.{環境}.yaml` を重ねる）もモニターと同じ
- スキル本文が参照する `WIKI_BASE` / `REPO_SLUG` は SessionStart フック（`load-constants.sh`）が CWD の git remote と `projects[].repo` を突き合わせて settings.yaml から展開する
- ラベル定数は `plugins/ai-monitor/constants.env` を SessionStart フックが環境変数として展開する

## ファイル一覧

| ファイル | 管理する値 | 補足 |
| --- | --- | --- |
| `~/.config/ai-monitor/settings.yaml` | 共通の設定値（モニターと共用） | git 管理外。サンプルは `settings.yaml.example` |

## settings.yaml

| 論理名 | キー | 型 | 必須 | 既定値 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| GitHub Token | `github_token` | `str` | ✅ | - | GitHub API（githubkit）の認証 PAT | 秘匿 |
| 待受ポート | `port` | `int` | - | `8765` | `report_completion` の送信先ポート | - |
| 監視対象プロジェクト | `projects[]` | `list` | ✅ | - | 監視するプロジェクトの一覧 | 子キーは下の行で展開。CWD の git remote と `repo` の一致で対象を特定 |
| 監視対象プロジェクト | `projects[].repo` | `str` | ✅ | - | 対象プロジェクトのリポジトリ（`owner/name`） | SessionStart フックが `REPO_SLUG` として展開 |
| 監視対象プロジェクト | `projects[].wiki_base` | `str` | ✅ | - | スキルが参照する Wiki の raw URL | SessionStart フックが `WIKI_BASE` として展開 |

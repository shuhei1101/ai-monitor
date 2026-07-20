# tmux

ターミナルマルチプレクサ（CLI）。
モニターがエージェントセッションの実体（作成 / 送信 / 生存確認 / kill）を操作するために使う。
セッション名は `ai-monitor-{project}-{番号}-{エージェント}`。

## 現在のバージョン情報

| 項目 | 内容 |
| --- | --- |
| バージョン | `3.4` |
| ライセンス | ISC |
| 公式 URL | https://github.com/tmux/tmux |
| 公式ドキュメント | https://github.com/tmux/tmux/wiki |

## インストール手順

```bash
sudo apt install tmux
```

## コマンド一覧

| コマンド | 用途 | 補足 |
| --- | --- | --- |
| [`new-session`](#new-session) | セッションの detached 作成 | - |
| [`send-keys`](#send-keys) | 既存セッションへの文字列送信 | - |
| [`has-session`](#has-session) | セッションの存在確認 | 終了コードで判定 |
| [`kill-session`](#kill-session) | セッションの kill | - |
| [`ls`](#ls) | セッション一覧の表示 | デバッグ・目視確認用 |
| [`capture-pane`](#capture-pane) | ペイン出力の取得 | テストの実行結果検証用 |

### `new-session`

```bash
tmux new-session -d -s {セッション名} -c {CWD}
```

| オプション | 説明 | 補足 |
| --- | --- | --- |
| `-d` | detached（アタッチせず作成） | - |
| `-s` | セッション名 | 同名が存在すると非 0 終了 |
| `-c` | 作業ディレクトリ | worktree の絶対パス |

### `send-keys`

```bash
tmux send-keys -t {セッション名} '{送信文}' Enter
```

| オプション | 説明 | 補足 |
| --- | --- | --- |
| `-t` | 送信先セッション | 不存在は非 0 終了 |
| 末尾 `Enter` | 送信文の実行（改行入力） | 付けないと入力だけで実行されない |

### `has-session`

```bash
tmux has-session -t {セッション名}
```

- 存在すれば終了コード 0・無ければ非 0（stderr にメッセージ）

### `kill-session`

```bash
tmux kill-session -t {セッション名}
```

| オプション | 説明 | 補足 |
| --- | --- | --- |
| `-t` | 対象セッション | 不存在は非 0 終了 |

### `ls`

```bash
tmux ls
```

- セッション名は `ai-monitor-{project}-` 始まりで並ぶため、番号順に同一 Issue の関連セッションがまとまる

### `capture-pane`

```bash
tmux capture-pane -t {セッション名} -p
```

| オプション | 説明 | 補足 |
| --- | --- | --- |
| `-t` | 対象セッション | - |
| `-p` | 標準出力へ出力 | バッファに残さない |

# ai-monitor

## モニターの起動と再起動

Claude Code の作業を止めずに動かすため、モニターは tmux の名前付きセッションで常駐させる。
セッション名は `ai-monitor-server` 固定（エージェントのセッションは `ai-monitor-{プロジェクト}-{番号}-{エージェント}` なので混ざらない）。

起動すると監視役（`python -m ai_monitor.watchdog`）も一緒に立ち上がり、以降は互いの生存を見張って落ちたほうを再起動する。

### 起動

```bash
tmux new-session -d -s ai-monitor-server -c /mnt/c/Users/shuhe/repo/ai-monitor \
  'PYTHONPATH=src uv run python -m ai_monitor'
```

### 状態の確認

```bash
tmux has-session -t ai-monitor-server && echo running || echo stopped
tmux capture-pane -p -t ai-monitor-server -S -50
```

### 再起動

監視役が動いているとモニターを落としても自動で立ち上げ直すため、先に監視役を止める。

```bash
kill "$(cat data/watchdog.pid)" 2>/dev/null
tmux kill-session -t ai-monitor-server 2>/dev/null
kill "$(cat data/monitor.pid)" 2>/dev/null
```

止め終えてから「起動」のコマンドをもう一度実行する。

### 停止

再起動と同じ手順で止め、起動し直さない。

## E2E テストの中断

実行中の E2E を打ち切るときは、プロセスにシグナルを送らず合図ファイルを作る。

```bash
touch .e2e/abort
```

待機中のテストが次のポーリング（15 秒以内）で失敗し、後片付けの fixture がそのまま走る。
合図ファイルは次回の実行開始時に消えるので、消し忘れても次の実行は妨げない。

一部のテストだけ止めたい場合は、テスト ID（`{ファイルパス}::{関数名}`）への部分一致で絞る。
中身が空なら実行中の全テストが対象になる。

```bash
echo "test_統合テスト失敗からのバグ修正" > .e2e/abort
```

kill や Ctrl-C で止めてはいけない。
pytest 本体は終わるが後片付けに到達せず、sandbox の Issue / PR / ブランチ / worktree と tmux セッションが残る。

詳細は `docs/wiki/テスト/テスト実行方法.md`。

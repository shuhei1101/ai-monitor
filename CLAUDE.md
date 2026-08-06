# ai-monitor

## Wiki 索引の取得

`docs/wiki/` 配下の全ページを「パス / 概要」の表で吐く。
モニターがエージェントを起動するとき、起動プロンプトへ注入しているものと同じ。

```bash
python3 plugins/ai-monitor/inject/build_wiki_index.py
```

`WIKI_BASE` を読む（SessionStart フックが設定済み。別プロジェクトを見るときだけ `WIKI_BASE=... python3 ...` で上書きする）。

ローカルの Claude Code で作業するときは、着手前にこれを実行して結果を読む。
各フォルダの `README.md` の `## 目次` を再帰的に辿って作るため、目次に載っていないページは出てこない。

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

## 不具合報告の検出

エージェントは手順どおりに進められない事象に当たると `AI不具合報告` ラベルの Issue を ai-monitor へ起票する。
E2E を回している間は特に出るので、新規分だけを拾って気づけるようにする。

**Claude Code の `Monitor` ツールを使う。**
Bash で直接回すとその場で待つことになるが、Monitor なら裏で動き続け、新規 Issue が出た時点で通知が届く。

呼び出しの形は次のとおり。

| 引数 | 値 |
| --- | --- |
| `command` | 下のスクリプト |
| `description` | `ai-monitor の AI不具合報告 ラベルに新規 Issue が付いたら通知` |
| `persistent` | `true`（セッションが終わるまで動き続ける。途中で止めるときは `TaskStop`） |
| `timeout_ms` | `3600000`（`persistent: true` のときは無視されるが指定は必要） |

`command` に渡すスクリプト。

```bash
R=shuhei1101/ai-monitor
list() { gh issue list --repo "$R" --label "AI不具合報告" --state open --limit 100 --json number --jq '.[].number' 2>/dev/null | sort; }
seen=$(list)
while true; do
  sleep 60
  cur=$(list) || true
  [ -z "$cur" ] && continue
  comm -13 <(echo "$seen") <(echo "$cur") | while read -r n; do
    [ -n "$n" ] && gh issue view "$n" --repo "$R" --json number,title --jq '"AI不具合報告 #\(.number) \(.title)"' 2>/dev/null || true
  done
  seen=$cur
done
```

要点は 3 つ。

| 項目 | 理由 |
| --- | --- |
| 起動時の一覧を `seen` に取る | 既存の open Issue を通知しないため（差分だけが欲しい） |
| 60 秒間隔 | GitHub API のレート制限に配慮する。E2E の 1 ターンより十分短い |
| `cur` が空なら `seen` を更新しない | 一時的な API 失敗で全件を「新規」と誤検出しないため |

手で確認するだけなら一覧を引く。

```bash
gh issue list --repo shuhei1101/ai-monitor --label "AI不具合報告" --state open
```

テストが pass していても起票されていることがあるので、実行後は必ず見る。

"""長い複合UC でユーザー役として承認ゲートに応答するドライバ。

工程をまたぐ複合UC は各レイヤーに `議論中` + `assignee=ユーザー` のゲートがあり、
終端に達するまで何度も応答する必要がある。
監視する面と応答内容を表で渡し、終了条件が成立するまで同じ仕組みで回す。
"""
from __future__ import annotations

from tests.e2e.エスカレーション import (
    append_user_block,
    approve,
    comments,
    issue,
    label_names,
    waiting_for_user,
)


def open_prs_for(gh_live, owner: str, repo: str, number: int) -> list:
    """本文で指定 Issue 番号を参照している open PR の一覧を返す。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    return [pr for pr in pulls if f"#{number}" in (pr.body or "")]


def drive_gates(
    gh_live, owner, repo, *, faces, choices, terminal, wait_until,
    max_rounds: int = 40, timeout_sec: int = 3600, interval_sec: int = 30,
):
    """終了条件が成立するまで、開いたゲートにユーザー役として応答し続ける。

    faces は現在の監視面 `(種別, 番号)` 一覧を返す callable、
    choices は `(種別, 確認ラベル)` に対する返信文（返信不要のゲートは None）、
    terminal は終了条件を判定して結果を返す callable。
    応答したゲートの履歴と terminal の結果を返す。
    """
    history: list[tuple[str, str]] = []

    def _next_event():
        done = terminal()
        if done:
            return ("done", done, None)
        for kind, number in faces():
            data = issue(gh_live, owner, repo, number)
            # 議論中 + assignee が揃い、エージェントのターンが終わった面がユーザーの番
            if waiting_for_user(data):
                names = label_names(data)
                confirms = sorted(name for name in names if name.startswith("確認:"))
                return ("gate", data, (kind, number, confirms))
        return None

    for _ in range(max_rounds):
        event, payload, gate = wait_until(
            _next_event, timeout_sec=timeout_sec, interval_sec=interval_sec,
            message="ユーザー確認ゲート または 終了条件",
        )
        if event == "done":
            return history, payload
        kind, number, confirms = gate
        key = next(((kind, name) for name in confirms if (kind, name) in choices), None)
        if key is None:
            # 表に無いゲートは返信なしで承認する（履歴には残す）
            history.append((kind, confirms[0] if confirms else ""))
            approve(gh_live, owner, repo, number, payload.assignees)
            continue
        history.append(key)
        reply = choices[key]
        # 回答が状況で変わるゲートは callable で渡す（同じ回答の重複投稿を避ける）
        if callable(reply):
            reply = reply(kind, number, history)
        # 返信が要るゲートは直近コメントのスレッドへユーザーブロックを追記する
        if reply:
            latest = comments(gh_live, owner, repo, number)[-1]
            append_user_block(gh_live, owner, repo, latest, reply)
        approve(gh_live, owner, repo, number, payload.assignees)
    raise AssertionError(f"{max_rounds} 回のゲート応答でも終了条件が成立しなかった: {history}")

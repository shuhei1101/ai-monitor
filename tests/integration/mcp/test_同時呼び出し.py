"""「同時呼び出し」の結合テスト。"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace as NS

import pytest
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

import ai_monitor.mcp.server as server

# 1 件あたりのブロッキング時間と同時呼び出し数（直列化していれば所要時間が CALLS 倍になる）
BLOCK_SEC = 0.5
CALLS = 4
# 最初に投げる 1 件だけ応答を遅くする（待ち合わせていれば速い側も遅い側に引きずられる）
SLOW_NUMBER = 1
SLOW_BLOCK_SEC = BLOCK_SEC * CALLS


@pytest.fixture
def mcp_app(monkeypatch, mon_settings, mon_registry, mcp_agents, label_settings):
    """全ツールを登録した FastMCP インスタンスを返す。"""
    instances = []

    class _Recording(server.FastMCP):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            instances.append(self)

    monkeypatch.setattr(server, "FastMCP", _Recording)
    server.build_mcp_app(
        mon_settings, registry=mon_registry, agents=mcp_agents, label_settings=label_settings
    )
    return instances[0]


@pytest.fixture
def mcp_request(monkeypatch):
    """`X-Project` ヘッダを持つ MCP リクエストコンテキストを有効にする。"""
    context = RequestContext(
        request_id=1,
        meta=None,
        session=NS(),
        lifespan_context=None,
        request=NS(headers={"X-Project": "sandbox"}),
    )
    token = request_ctx.set(context)
    yield
    request_ctx.reset(token)


def _issue(number: int):
    return NS(
        number=number,
        title=f"対象 {number}",
        body="本文",
        html_url=f"http://i/{number}",
        state="open",
        state_reason=None,
        closed_at=None,
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-02T00:00:00Z",
        labels=[],
        assignees=[],
        user=NS(login="shuhei1101"),
        sub_issues_summary=NS(total=0, completed=0, percent_completed=0.0),
    )


def test_normal(gh, resp, mcp_app, mcp_request):
    """同時に呼ばれたツールが並行処理され、終わったものから返ることを確認する（正常系）。"""
    # 準備
    def blocking_get(*, owner, repo, issue_number):
        # 応答までブロックする GitHub API を再現する（最初に投げた 1 件だけ遅くする）
        time.sleep(SLOW_BLOCK_SEC if issue_number == SLOW_NUMBER else BLOCK_SEC)
        return resp(_issue(issue_number))

    gh.rest.issues.get.side_effect = blocking_get
    finished: list[int] = []

    async def _call(number: int):
        result = await mcp_app.call_tool(
            "get_issue_or_pr",
            {"number": number, "is_pr": False, "comments": False, "parent": False, "sub_issues": False},
        )
        # 返ってきた順を記録する（待ち合わせていれば遅い側に揃ってしまう）
        finished.append(number)
        return result

    async def _call_all():
        started = time.perf_counter()
        results = await asyncio.gather(*(_call(n) for n in range(1, CALLS + 1)))
        return time.perf_counter() - started, results

    # 実行
    elapsed, results = asyncio.run(_call_all())
    # 検証
    assert [r[1]["number"] for r in results] == list(range(1, CALLS + 1))
    # 速い側どうしの順序は保証されないので、遅い 1 件が最後に返ることだけを見る
    assert finished[-1] == SLOW_NUMBER
    assert set(finished[:-1]) == {n for n in range(1, CALLS + 1) if n != SLOW_NUMBER}
    assert elapsed < SLOW_BLOCK_SEC + BLOCK_SEC


def test_normal_when_registry_tool(gh, mcp_app, mcp_request, session_factory, mon_registry, tmp_state_path):
    """台帳を触るツールの同時更新でも全ての変更が残ることを確認する（正常系・台帳を触るツール）。"""
    # 準備
    from ai_monitor.features.sessions.state_store import load_sessions

    for index in range(CALLS):
        session_factory("architect", 50 + index)

    async def _call_all():
        await asyncio.gather(
            *(
                mcp_app.call_tool(
                    "add_watch_targets",
                    {"agent_name": "architect", "number": 50 + index, "watch_numbers": [100 + index]},
                )
                for index in range(CALLS)
            )
        )

    # 実行
    asyncio.run(_call_all())
    # 検証
    for index in range(CALLS):
        assert mon_registry.find("sandbox", "architect", 50 + index).watch_numbers == [100 + index]
    persisted = {s.primary_number: s.watch_numbers for s in load_sessions(tmp_state_path)}
    assert persisted == {50 + index: [100 + index] for index in range(CALLS)}

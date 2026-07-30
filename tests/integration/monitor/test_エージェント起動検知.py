"""「エージェント起動検知」の結合テスト。"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.features.agents import docs
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.main import build_agents, run_cycle

FUTURE = "2100-01-01T00:00:00+00:00"
REMOTE_BASE = "https://raw.example.com/owner/repo/master/docs/wiki"

HARNESS_README = (
    "## 目次\n\n"
    "| ページ | 概要 |\n"
    "| --- | --- |\n"
    "| [対応表](./共通対応表/対応表.md) | 共通の星取り表 |\n"
)
COMMON_MATRIX = (
    "| ドキュメント | intake-issue-triager |\n"
    "| --- | --- |\n"
    "| [規約/コメント.md](../../規約/コメント.md) | ○ |\n"
)
WIKI_README = (
    "## 目次\n\n"
    "| ページ | 概要 |\n"
    "| --- | --- |\n"
    "| [規約](./規約.md) | 規約ページ |\n"
)
PHASE_BODY = "# 初期処理\n"


def _write(root, pages):
    """一時ディレクトリにページ群を作成し、ベースとなる絶対パスを返す。"""
    for rel, body in pages.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return str(root)


@pytest.fixture
def local_wiki(tmp_path, monkeypatch, mon_settings, mon_project):
    """ai-monitor 側 / プロジェクト側の Wiki をローカルに作り、両ベースへ設定する。"""
    common = _write(
        tmp_path / "ai-monitor-wiki",
        {
            "Claudeハーネス/README.md": HARNESS_README,
            "Claudeハーネス/共通対応表/対応表.md": COMMON_MATRIX,
            "規約/コメント.md": "# 規約: コメント\n",
            "エージェント/iit/フェーズ/初期処理.md": PHASE_BODY,
        },
    )
    project = _write(tmp_path / "project-wiki", {"README.md": WIKI_README, "規約.md": "# 規約\n"})
    phases = tmp_path / "agent_phases.yaml"
    phases.write_text(
        "intake-issue-triager:\n  - エージェント/iit/フェーズ/初期処理.md\n", encoding="utf-8"
    )
    monkeypatch.setattr(docs, "PHASE_CONFIG_PATH", phases)
    mon_settings.ai_monitor_wiki_base = common
    mon_project.wiki_base = project
    return NS(common=common, project=project, phases=phases)


@pytest.fixture
def remote_wiki(monkeypatch, fake_wiki, tmp_path, mon_settings, mon_project):
    """両ベースを raw URL にし、HTTP 応答を仕込む。"""
    fake_wiki.pages[f"{REMOTE_BASE}/エージェント/iit/フェーズ/初期処理.md"] = PHASE_BODY
    fake_wiki.pages[f"{REMOTE_BASE}/Claudeハーネス/README.md"] = HARNESS_README
    fake_wiki.pages[f"{REMOTE_BASE}/Claudeハーネス/共通対応表/対応表.md"] = COMMON_MATRIX
    fake_wiki.pages[f"{REMOTE_BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    fake_wiki.pages[f"{REMOTE_BASE}/README.md"] = WIKI_README
    phases = tmp_path / "agent_phases.yaml"
    phases.write_text(
        "intake-issue-triager:\n  - エージェント/iit/フェーズ/初期処理.md\n", encoding="utf-8"
    )
    monkeypatch.setattr(docs, "PHASE_CONFIG_PATH", phases)
    mon_settings.ai_monitor_wiki_base = REMOTE_BASE
    mon_project.wiki_base = REMOTE_BASE
    return fake_wiki


def _resp(items):
    r = MagicMock()
    r.parsed_data = items
    return r


def _issue_ns(number, labels, assignees=()):
    return NS(
        number=number,
        state="open",
        labels=[NS(name=name) for name in labels],
        assignees=[NS(login=login) for login in assignees],
        body="",
        pull_request=None,
        sub_issues_summary=None,
    )


def _cycle(mon_settings, label_settings, agent_models, mon_registry, notify, prev=None):
    agents = build_agents(label_settings, agent_models=agent_models)
    return run_cycle(
        mon_settings, agents, registry=mon_registry, prev_targets=prev or {}, last_heartbeat_at=FUTURE, labels=label_settings, gate=RateLimitGate()
    , notify=notify)


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, tmp_state_path, local_wiki, fake_wiki, notify):
    """新規対象の検知 → セッション作成 + 起動プロンプトの送信を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_issue_ns(35, ["確認:intake-issue-triager"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, notify)
    # 検証
    session_name = "ai-monitor-sandbox-35-intake-issue-triager"
    assert ["new-session", "-d", "-s", session_name, "-c", "/tmp/sandbox"] in tmux_calls.calls
    assert mon_registry.find("sandbox", "intake-issue-triager", 35) is not None
    assert tmp_state_path.exists()
    assert gh_mon.rest.issues.add_labels.call_args.kwargs["labels"] == ["処理中:intake-issue-triager"]
    send = next(c for c in tmux_calls.calls if c[0] == "send-keys")
    assert send[3].startswith("AI_MONITOR_PROJECT=sandbox AI_MONITOR_AGENT=intake-issue-triager")
    assert "claude --model sonnet --dangerously-skip-permissions" in send[3]
    # 追記システムプロンプトのファイルにフェーズ本文・参考資料・Wiki 索引が載る
    docs_path = send[3].split("--append-system-prompt-file ")[1].split(" ")[0]
    docs = Path(docs_path).read_text(encoding="utf-8")
    assert "# 初期処理" in docs
    assert "# 規約: コメント" in docs
    assert "規約.md" in docs
    # 起動プロンプトには対象番号とスナップショットが載る
    prompt = Path(send[3].split('"$(cat ')[1].rstrip(')"')).read_text(encoding="utf-8")
    assert "- 対象番号: 35" in prompt
    assert "#35" in prompt
    # ローカル読みなのでネットワークアクセスは発生しない
    assert fake_wiki.calls == []


def test_normal_when_existing_session(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, local_wiki, notify):
    """既存セッションへの再開送信を確認する（正常系）。"""
    # 準備
    mon_registry.register(
        AgentSession(
            session_name="ai-monitor-sandbox-35-intake-issue-triager",
            project="sandbox",
            agent_name="intake-issue-triager",
            primary_number=35,
        )
    )
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_issue_ns(35, ["確認:intake-issue-triager"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, notify)
    # 検証
    assert not any(c[0] == "new-session" for c in tmux_calls.calls)
    send = next(c for c in tmux_calls.calls if c[0] == "send-keys")
    assert send[2] == "ai-monitor-sandbox-35-intake-issue-triager"
    assert send[3].startswith("状態が変化しました")


def test_normal_when_processing_label(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, notify):
    """処理中ラベル付きの対象の除外を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_issue_ns(35, ["確認:intake-issue-triager", "処理中:intake-issue-triager"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, notify)
    # 検証
    assert tmux_calls.calls == []
    gh_mon.rest.issues.add_labels.assert_not_called()


def test_error_when_api_error(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, request_failed, notify):
    """対象一覧の取得失敗で周期を見送ることを確認する（異常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = request_failed(500)
    # 実行
    targets_by_project, _ = _cycle(mon_settings, label_settings, agent_models, mon_registry, notify)
    # 検証
    assert targets_by_project == {}
    assert tmux_calls.calls == []


def test_normal_when_remote_base(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, remote_wiki, notify):
    """Wiki ベースが raw URL のときのドキュメント組み立てを確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_issue_ns(35, ["確認:intake-issue-triager"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, notify)
    # 検証: ベースと相対パスを連結し、非 ASCII を quote した URL でリクエストされる
    assert remote_wiki.calls
    assert any("%E3%82%A8" in call for call in remote_wiki.calls)
    assert all(call.startswith("https://raw.example.com/") for call in remote_wiki.calls)
    # 追記システムプロンプトのファイルにフェーズ本文・参考資料・Wiki 索引が載る
    send = next(c for c in tmux_calls.calls if c[0] == "send-keys")
    docs = Path(send[3].split("--append-system-prompt-file ")[1].split(" ")[0]).read_text(encoding="utf-8")
    assert "# 初期処理" in docs
    assert "# 規約: コメント" in docs
    assert "規約.md" in docs

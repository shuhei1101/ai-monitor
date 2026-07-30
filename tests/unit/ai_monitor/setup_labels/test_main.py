"""`src/ai_monitor/setup_labels/__main__.py` の単体テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from githubkit.exception import RequestFailed

import ai_monitor.setup_labels.__main__ as main_mod
from ai_monitor.setup_labels.sync import LabelSpec, SyncResult

REPO_A = "shuhei1101/ai-monitor"
REPO_B = "shuhei1101/aituber"


def _spec(name: str) -> LabelSpec:
    return LabelSpec(name=name, color="0e8a16", description="説明")


def _request_failed(status_code: int, reason: str) -> RequestFailed:
    response = MagicMock()
    response.status_code = status_code
    response.reason_phrase = reason
    return RequestFailed(response)


@pytest.fixture
def settings_two_projects(monkeypatch):
    """projects[] に 2 件を登録した Settings を返すようにする。"""
    settings = NS(
        github_token=NS(get_secret_value=lambda: "token"),
        projects=[NS(name="ai-monitor", repo=REPO_A), NS(name="aituber", repo=REPO_B)],
    )
    monkeypatch.setattr(main_mod, "Settings", lambda: settings)
    monkeypatch.setattr(main_mod, "get_client", MagicMock())
    return settings


@pytest.fixture
def sync_spy(monkeypatch):
    """sync_labels を呼び出し引数の記録つきに差し替える。"""
    spy = MagicMock(side_effect=lambda repo, specs, **kw: SyncResult(repo=repo, created=[_spec("確認:architect")]))
    monkeypatch.setattr(main_mod, "sync_labels", spy)
    return spy


# ---- ラベル一括作成の起動 ----


def test_main(settings_two_projects, sync_spy, capsys, monkeypatch):
    """全プロジェクトの同期を確認する（正常系）。"""
    # 準備
    monkeypatch.setattr("sys.argv", ["ai_monitor.setup_labels"])
    # 実行
    code = main_mod.main()
    # 検証
    assert code == 0
    assert [call.args[0] for call in sync_spy.call_args_list] == [REPO_A, REPO_B]
    out = capsys.readouterr().out
    assert REPO_A in out and REPO_B in out


def test_main_when_repo_specified(settings_two_projects, sync_spy, capsys, monkeypatch):
    """`--repo` 指定時の 1 件だけの同期を確認する（正常系）。"""
    # 準備
    monkeypatch.setattr("sys.argv", ["ai_monitor.setup_labels", "--repo", REPO_B])
    # 実行
    code = main_mod.main()
    # 検証
    assert code == 0
    assert [call.args[0] for call in sync_spy.call_args_list] == [REPO_B]


def test_main_when_dry_run(settings_two_projects, sync_spy, monkeypatch):
    """`--dry-run` の同期への伝播を確認する（正常系）。"""
    # 準備
    monkeypatch.setattr("sys.argv", ["ai_monitor.setup_labels", "--dry-run"])
    # 実行
    code = main_mod.main()
    # 検証
    assert code == 0
    assert all(call.kwargs["dry_run"] is True for call in sync_spy.call_args_list)


def test_main_when_repo_not_registered(settings_two_projects, sync_spy, capsys, monkeypatch):
    """未登録リポジトリ指定時のエラー終了を確認する（異常系）。"""
    # 準備
    monkeypatch.setattr("sys.argv", ["ai_monitor.setup_labels", "--repo", "other/repo"])
    # 実行
    code = main_mod.main()
    # 検証
    assert code == 1
    assert sync_spy.call_count == 0
    err = capsys.readouterr().err
    # 登録済みリポジトリの一覧を出す
    assert REPO_A in err and REPO_B in err


def test_main_when_request_failed(settings_two_projects, capsys, monkeypatch):
    """一部リポジトリの失敗の切り離しを確認する（異常系）。"""
    # 準備
    monkeypatch.setattr("sys.argv", ["ai_monitor.setup_labels"])

    def _sync(repo, specs, **kwargs):
        if repo == REPO_B:
            raise _request_failed(500, "Internal Server Error")
        return SyncResult(repo=repo, created=[_spec("確認:architect")])

    spy = MagicMock(side_effect=_sync)
    monkeypatch.setattr(main_mod, "sync_labels", spy)
    # 実行
    code = main_mod.main()
    # 検証
    assert code == 2
    assert spy.call_count == 2
    out = capsys.readouterr().out
    assert "作成 1" in out
    assert f"{REPO_B}: 失敗（500 Internal Server Error）" in out


# ---- 同期結果の整形 ----


def test_format_result():
    """作成と更新の両方を出すことを確認する（正常系）。"""
    # 準備
    result = SyncResult(
        repo=REPO_A,
        created=[_spec("確認:architecture-reverse-engineer"), _spec("処理中:architecture-reverse-engineer")],
        updated=[_spec("議論中")],
        unchanged=[_spec(f"label-{i}") for i in range(40)],
    )
    # 実行
    out = main_mod.format_result(result)
    # 検証
    lines = out.splitlines()
    assert lines[0] == f"{REPO_A}: 作成 2 / 更新 1 / 変更なし 40"
    assert lines[1] == "  作成: 確認:architecture-reverse-engineer, 処理中:architecture-reverse-engineer"
    assert lines[2] == "  更新: 議論中"
    assert len(lines) == 3


def test_format_result_when_no_change():
    """差分なしのときのサマリ行だけの出力を確認する（正常系）。"""
    # 準備
    result = SyncResult(repo=REPO_A, unchanged=[_spec("議論中")])
    # 実行
    out = main_mod.format_result(result)
    # 検証
    assert out == f"{REPO_A}: 作成 0 / 更新 0 / 変更なし 1"


def test_format_result_when_error():
    """失敗したリポジトリの 1 行出力を確認する（正常系）。"""
    # 準備
    result = SyncResult(repo=REPO_A, error="403 Forbidden")
    # 実行
    out = main_mod.format_result(result)
    # 検証
    assert out == f"{REPO_A}: 失敗（403 Forbidden）"

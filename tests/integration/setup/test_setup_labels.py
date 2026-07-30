"""「ラベル一括作成」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from githubkit.exception import RequestFailed

import ai_monitor.setup_labels.__main__ as main_mod
from ai_monitor.setup_labels.sync import LabelStyleSettings, build_label_specs

REPO_A = "shuhei1101/ai-monitor"
REPO_B = "shuhei1101/aituber"


def _label_ns(name: str, color: str, description: str = ""):
    return NS(name=name, color=color, description=description)


def _request_failed(status_code: int, reason: str) -> RequestFailed:
    response = MagicMock()
    response.status_code = status_code
    response.reason_phrase = reason
    return RequestFailed(response)


@pytest.fixture
def specs():
    """constants.env から組み立てたあるべきラベル一覧を返す。"""
    return build_label_specs(styles=LabelStyleSettings())


@pytest.fixture
def cli(monkeypatch, gh_mon):
    """Settings を差し替えて CLI を実行できるようにする factory。"""

    def _run(*argv: str, repos: list[str]) -> int:
        settings = NS(
            github_token=NS(get_secret_value=lambda: "token"),
            projects=[NS(name=repo.split("/", 1)[1], repo=repo) for repo in repos],
        )
        monkeypatch.setattr(main_mod, "Settings", lambda: settings)
        monkeypatch.setattr("sys.argv", ["ai_monitor.setup_labels", *argv])
        return main_mod.main()

    return _run


def test_normal(gh_mon, resp, cli, capsys, specs):
    """未作成は作成・既存は色 / 説明を更新する一連を確認する（正常系）。"""
    # 準備: 議論中 のみが別の色で存在する
    gh_mon.rest.issues.list_labels_for_repo.return_value = resp([_label_ns("議論中", "ffffff")])
    in_discussion = next(spec for spec in specs if spec.name == "議論中")
    # 実行
    code = cli("--repo", REPO_A, repos=[REPO_A])
    # 検証
    assert code == 0
    created = [c.kwargs["name"] for c in gh_mon.rest.issues.create_label.call_args_list]
    # constants.env の全ラベルがリポジトリに存在する（既存の 議論中 以外は作成される）
    assert set(created) == {spec.name for spec in specs} - {"議論中"}
    # 既存の 議論中 の色が constants.env の定義値に更新される
    update_kwargs = gh_mon.rest.issues.update_label.call_args.kwargs
    assert update_kwargs["name"] == "議論中"
    assert update_kwargs["color"] == in_discussion.color
    # 標準出力に 作成 / 更新 / 変更なし の件数と名前が出る
    out = capsys.readouterr().out
    assert f"{REPO_A}: 作成 {len(created)} / 更新 1 / 変更なし 0" in out
    assert "  更新: 議論中" in out


def test_normal_when_dry_run(gh_mon, resp, cli, capsys, monkeypatch, specs):
    """`--dry-run` 指定時の書き込み抑止を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_labels_for_repo.return_value = resp([_label_ns("議論中", "ffffff")])
    # 実行
    dry_code = cli("--repo", REPO_A, "--dry-run", repos=[REPO_A])
    dry_out = capsys.readouterr().out
    wet_code = cli("--repo", REPO_A, repos=[REPO_A])
    wet_out = capsys.readouterr().out
    # 検証
    assert dry_code == 0 and wet_code == 0
    # 書き込みは --dry-run なしの 1 回分だけ発生する
    assert gh_mon.rest.issues.create_label.call_count == len(specs) - 1
    assert gh_mon.rest.issues.update_label.call_count == 1
    # 標準出力の内容が --dry-run なしと同じになる
    assert dry_out == wet_out


def test_error_when_repo_not_registered(gh_mon, cli, capsys):
    """`--repo` が未登録のときの設定エラーを確認する（異常系）。"""
    # 実行
    code = cli("--repo", "other/repo", repos=[REPO_A])
    # 検証
    assert code == 1
    # GitHub API の呼び出しが 1 回も発生しない
    assert gh_mon.rest.issues.list_labels_for_repo.call_count == 0
    assert gh_mon.rest.issues.create_label.call_count == 0
    err = capsys.readouterr().err
    assert "other/repo" in err
    assert REPO_A in err


def test_error_when_forbidden(gh_mon, resp, cli, capsys):
    """トークンの権限不足を確認する（異常系）。"""
    # 準備: 一覧取得は成功、作成で 403 を返す
    gh_mon.rest.issues.list_labels_for_repo.return_value = resp([])
    gh_mon.rest.issues.create_label.side_effect = _request_failed(403, "Forbidden")
    # 実行
    code = cli("--repo", REPO_A, repos=[REPO_A])
    # 検証
    assert code == 2
    captured = capsys.readouterr()
    assert f"{REPO_A}: 失敗（403 Forbidden）" in captured.out
    # 標準エラー出力に HTTP ステータスが出る
    assert "403" in captured.err


def test_error_when_partial_failure(gh_mon, resp, cli, capsys, specs):
    """一部リポジトリの失敗を切り離して継続することを確認する（異常系）。"""
    # 準備: 1 件目は正常応答、2 件目は一覧取得で 500 を返す
    gh_mon.rest.issues.list_labels_for_repo.side_effect = [
        resp([]),
        _request_failed(500, "Internal Server Error"),
    ]
    # 実行
    code = cli(repos=[REPO_A, REPO_B])
    # 検証
    assert code == 2
    # 1 件目のラベルが GitHub に反映されている
    created = [c.kwargs["name"] for c in gh_mon.rest.issues.create_label.call_args_list]
    assert set(created) == {spec.name for spec in specs}
    out = capsys.readouterr().out
    assert f"{REPO_A}: 作成 {len(specs)} / 更新 0 / 変更なし 0" in out
    assert f"{REPO_B}: 失敗（500 Internal Server Error）" in out

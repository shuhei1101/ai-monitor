"""「ラベル除去」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import LabelsResult


def test_normal(gh, resp):
    """ラベル除去 → 一覧再取得の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = resp(NS(labels=[NS(name="layer:epic")]))
    # 実行
    res = server.remove_labels(35, is_pr=False, labels=["確認:architect"])
    # 検証
    assert gh.rest.issues.remove_label.call_args.kwargs["name"] == "確認:architect"
    assert res == LabelsResult(current_labels=["layer:epic"])


def test_error_when_in_discussion(gh):
    """議論中の除去指定によるエラー返却を確認する（異常系・許可外ラベル指定）。"""
    # 実行・検証
    with pytest.raises(ValueError):
        server.remove_labels(35, is_pr=False, labels=["議論中"])
    gh.rest.issues.remove_label.assert_not_called()


def test_error_when_api_error(gh, request_failed):
    """API エラー（404 以外）の伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.remove_label.side_effect = request_failed(500)
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.remove_labels(35, is_pr=False, labels=["確認:architect"])

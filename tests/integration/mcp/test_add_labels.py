"""「ラベル追加」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import LabelsResult


def test_normal(gh, resp):
    """ラベル追加 → 一覧再取得の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = resp(NS(labels=[NS(name="layer:epic"), NS(name="確認:tester")]))
    # 実行
    res = server.add_labels(35, is_pr=False, labels=["確認:tester"])
    # 検証
    assert gh.rest.issues.add_labels.call_args.kwargs["labels"] == ["確認:tester"]
    assert res == LabelsResult(current_labels=["layer:epic", "確認:tester"])


def test_error_when_api_error(gh, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.add_labels.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.add_labels(35, is_pr=False, labels=["確認:tester"])

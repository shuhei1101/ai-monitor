"""「フェーズ遷移」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import LabelsResult


def test_normal(gh, resp):
    """除去 + 追加の 1 コマンド実行と現況返却を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = resp(NS(labels=[NS(name="layer:subsystem"), NS(name="確認:tester")]))
    # 実行
    res = server.transition_phase(52, is_pr=True, remove_labels_=["確認:architect"], add_labels_=["確認:tester"])
    # 検証
    ordered = [c[0] for c in gh.rest.issues.method_calls if c[0] in ("remove_label", "add_labels")]
    assert ordered == ["remove_label", "add_labels"]
    assert res == LabelsResult(current_labels=["layer:subsystem", "確認:tester"])


def test_error_when_in_discussion(gh):
    """議論中の除去指定によるエラー返却を確認する（異常系・許可外ラベル指定）。"""
    # 実行・検証
    with pytest.raises(ValueError):
        server.transition_phase(52, is_pr=True, remove_labels_=["議論中"], add_labels_=["確認:tester"])
    gh.rest.issues.remove_label.assert_not_called()
    gh.rest.issues.add_labels.assert_not_called()


def test_error_when_api_error(gh, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.add_labels.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.transition_phase(52, is_pr=True, add_labels_=["確認:tester"])

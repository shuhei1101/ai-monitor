"""`src/ai_monitor/integrations/github/client.py` の単体テスト。"""
from __future__ import annotations

from unittest.mock import MagicMock

import ai_monitor.integrations.github.client as client_mod


def test_get_client(monkeypatch):
    """インスタンスの共有を確認する（正常系）。"""
    # 準備
    monkeypatch.setattr(client_mod, "_client", None, raising=False)
    settings = MagicMock()
    settings.github_token.get_secret_value.return_value = "github_pat_test"
    # 実行
    first = client_mod.get_client(settings)
    second = client_mod.get_client(settings)
    # 検証
    assert first is second

"""「worktree削除」の結合テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import ai_monitor.mcp.server as server


def test_normal(tmp_git_repo, api):
    """worktree 削除 → ブランチ強制削除の一連を確認する（正常系）。"""
    # 準備
    created = api.worktree_create("feat/rm", "origin/master")
    worktree = Path(created.worktree_path)
    # 実行
    res = api.worktree_remove("feat/rm")
    # 検証
    assert not worktree.exists()
    assert worktree.is_relative_to(tmp_git_repo)
    branches = subprocess.run(
        ["git", "branch", "--list", "feat/rm"], cwd=tmp_git_repo, capture_output=True, text=True
    ).stdout
    assert "feat/rm" not in branches
    assert res.branch == "feat/rm"


def test_error_when_git_fails(tmp_git_repo, api):
    """worktree 不存在による git 実行失敗を確認する（異常系・git 実行失敗）。"""
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        api.worktree_remove("feat/none")


def test_error_when_project_unknown(tmp_git_repo, mon_settings, mcp_ctx_factory):
    """未登録プロジェクトの拒否を確認する（異常系・プロジェクト不明）。"""
    # 準備
    tool = server._bind(server.worktree_remove, ctx=mcp_ctx_factory("unknown"), settings=mon_settings)
    # 実行・検証
    with pytest.raises(server.ProjectNotFoundError):
        tool("feat/x")

"""「worktree作成」の結合テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import ai_monitor.mcp.server as server



def test_normal(tmp_git_repo, api):
    """ブランチ作成 + worktree 追加の一連を確認する（正常系）。"""
    # 実行
    res = api.worktree_create("feat/backend/profile/edit/edit-api", "origin/master")
    # 検証
    worktree = Path(res.worktree_path)
    assert worktree.is_dir()
    assert worktree.is_relative_to(tmp_git_repo)
    assert res.base_ref == "origin/master"
    branches = subprocess.run(
        ["git", "branch", "--list", res.branch], cwd=tmp_git_repo, capture_output=True, text=True
    ).stdout
    assert res.branch in branches


def test_normal_when_dirs_missing(tmp_git_repo, api):
    """worktree フォルダ未作成時のパス作成を確認する（正常系・worktree フォルダ未作成時）。"""
    # 準備
    assert not (tmp_git_repo / ".claude").exists()
    # 実行
    res = api.worktree_create("feat/a", "origin/master")
    # 検証
    assert Path(res.worktree_path).is_dir()


def test_error_when_git_fails(tmp_git_repo, api):
    """既存ブランチ名の指定による git 実行失敗を確認する（異常系・git 実行失敗）。"""
    # 準備
    api.worktree_create("feat/dup", "origin/master")
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        api.worktree_create("feat/dup", "origin/master")


def test_error_when_project_unknown(tmp_git_repo, mon_settings, mcp_ctx_factory):
    """未登録プロジェクトの拒否を確認する（異常系・プロジェクト不明）。"""
    # 準備
    tool = server._bind(server.worktree_create, ctx=mcp_ctx_factory("unknown"), settings=mon_settings)
    # 実行・検証
    with pytest.raises(server.ProjectNotFoundError):
        tool("feat/x", "origin/master")
    assert not (tmp_git_repo / ".claude").exists()

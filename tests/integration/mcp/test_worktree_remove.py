"""「worktree削除」の結合テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import server


def test_normal(tmp_git_repo):
    """worktree 削除 → ブランチ強制削除の一連を確認する（正常系）。"""
    # 準備
    created = server.worktree_create("feat/rm")
    worktree = Path(created.worktree_path)
    # 実行
    res = server.worktree_remove("feat/rm")
    # 検証
    assert not worktree.exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "feat/rm"], cwd=tmp_git_repo, capture_output=True, text=True
    ).stdout
    assert "feat/rm" not in branches
    assert res.branch == "feat/rm"


def test_error_when_git_fails(tmp_git_repo):
    """worktree 不存在による git 実行失敗を確認する（異常系・git 実行失敗）。"""
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        server.worktree_remove("feat/none")

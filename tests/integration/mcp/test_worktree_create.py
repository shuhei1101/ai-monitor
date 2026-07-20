"""「worktree作成」の結合テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import server


def test_normal(tmp_git_repo):
    """ブランチ作成 + worktree 追加の一連を確認する（正常系）。"""
    # 実行
    res = server.worktree_create("feat/backend/profile/edit/edit-api")
    # 検証
    worktree = Path(res.worktree_path)
    assert worktree.is_dir()
    assert res.base_ref == "origin/master"
    branches = subprocess.run(
        ["git", "branch", "--list", res.branch], cwd=tmp_git_repo, capture_output=True, text=True
    ).stdout
    assert res.branch in branches


def test_normal_when_dirs_missing(tmp_git_repo):
    """worktree フォルダ未作成時のパス作成を確認する（正常系・worktree フォルダ未作成時）。"""
    # 準備
    assert not (tmp_git_repo / ".claude").exists()
    # 実行
    res = server.worktree_create("feat/a")
    # 検証
    assert Path(res.worktree_path).is_dir()


def test_error_when_git_fails(tmp_git_repo):
    """既存ブランチ名の指定による git 実行失敗を確認する（異常系・git 実行失敗）。"""
    # 準備
    server.worktree_create("feat/dup")
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        server.worktree_create("feat/dup")

"""`plugins/ai-monitor/hooks/session-start/load-constants.sh` の単体テスト。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "plugins" / "ai-monitor" / "hooks" / "session-start" / "load-constants.sh"
)
REPO_SLUG = "shuhei1101/sandbox"


@pytest.fixture
def tmp_env_file(tmp_path) -> Path:
    """CLAUDE_ENV_FILE の追記先になる空ファイルを作る。"""
    path = tmp_path / "claude-env.sh"
    path.write_text("", encoding="utf-8")
    return path


@pytest.fixture
def tmp_remote_repo(tmp_path) -> Path:
    """origin を持つ一時 git リポジトリを作る。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"https://github.com/{REPO_SLUG}.git"],
        cwd=repo, check=True,
    )
    return repo


@pytest.fixture
def tmp_hook_settings(tmp_path):
    """HOME を差し替えた先に settings.yaml を作る factory を返す。"""
    home = tmp_path / "home"
    (home / ".config" / "ai-monitor").mkdir(parents=True)

    def _write(projects: list[dict]) -> Path:
        path = home / ".config" / "ai-monitor" / "settings.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "projects": projects,
                    "ai_monitor_wiki_base": "https://example.com/ai-monitor/docs/wiki",
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        return path

    _write.home = home
    return _write


def _run(cwd: Path, *, home: Path, env_file: Path | None) -> subprocess.CompletedProcess:
    """フックスクリプトを実行する。"""
    env = {**os.environ, "HOME": str(home)}
    # 展開先なしの検証のため、環境変数そのものを落とせるようにする
    if env_file is None:
        env.pop("CLAUDE_ENV_FILE", None)
    else:
        env["CLAUDE_ENV_FILE"] = str(env_file)
    return subprocess.run(
        ["bash", str(SCRIPT)], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def test_load_constants(tmp_env_file, tmp_remote_repo, tmp_hook_settings):
    """設定・remote が揃った状態での全変数の展開を確認する（正常系）。"""
    # 準備
    tmp_hook_settings(
        [{"repo": REPO_SLUG, "wiki_base": "https://example.com/sandbox/docs/wiki"}]
    )
    # 実行
    result = _run(tmp_remote_repo, home=tmp_hook_settings.home, env_file=tmp_env_file)
    # 検証
    assert result.returncode == 0, result.stderr
    written = tmp_env_file.read_text(encoding="utf-8")
    assert "export AI_MONITOR_LABEL_" in written
    assert f'export REPO_SLUG="{REPO_SLUG}"' in written
    assert 'export WIKI_BASE="https://example.com/sandbox/docs/wiki"' in written
    assert 'export AI_MONITOR_WIKI_BASE="https://example.com/ai-monitor/docs/wiki"' in written
    assert REPO_SLUG in result.stdout
    assert "https://example.com/sandbox/docs/wiki" in result.stdout


def test_load_constants_when_env_file_missing(tmp_remote_repo, tmp_hook_settings):
    """展開先が無いときの中断を確認する（異常系）。"""
    # 準備
    tmp_hook_settings(
        [{"repo": REPO_SLUG, "wiki_base": "https://example.com/sandbox/docs/wiki"}]
    )
    # 実行
    result = _run(tmp_remote_repo, home=tmp_hook_settings.home, env_file=None)
    # 検証
    assert result.returncode == 1
    assert "CLAUDE_ENV_FILE" in result.stderr


def test_load_constants_when_settings_missing(tmp_env_file, tmp_remote_repo, tmp_hook_settings):
    """settings.yaml が無いときのセッション固有値のスキップを確認する（正常系）。"""
    # 準備: settings.yaml を書かない（HOME だけ差し替える）
    # 実行
    result = _run(tmp_remote_repo, home=tmp_hook_settings.home, env_file=tmp_env_file)
    # 検証
    assert result.returncode == 0, result.stderr
    written = tmp_env_file.read_text(encoding="utf-8")
    assert "export AI_MONITOR_LABEL_" in written
    assert "WIKI_BASE" not in written
    assert "監視対象として解決できませんでした" in result.stdout


def test_load_constants_when_no_remote(tmp_env_file, tmp_path, tmp_hook_settings):
    """origin が無いときのセッション固有値のスキップを確認する（正常系）。"""
    # 準備
    tmp_hook_settings(
        [{"repo": REPO_SLUG, "wiki_base": "https://example.com/sandbox/docs/wiki"}]
    )
    repo = tmp_path / "no-remote"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    # 実行
    result = _run(repo, home=tmp_hook_settings.home, env_file=tmp_env_file)
    # 検証
    assert result.returncode == 0, result.stderr
    written = tmp_env_file.read_text(encoding="utf-8")
    assert "export AI_MONITOR_LABEL_" in written
    assert "WIKI_BASE" not in written
    assert "監視対象として解決できませんでした" in result.stdout


def test_load_constants_when_project_unregistered(
    tmp_env_file, tmp_remote_repo, tmp_hook_settings
):
    """projects[] に未登録のときのセッション固有値のスキップを確認する（正常系）。"""
    # 準備
    tmp_hook_settings(
        [{"repo": "shuhei1101/other", "wiki_base": "https://example.com/other/docs/wiki"}]
    )
    # 実行
    result = _run(tmp_remote_repo, home=tmp_hook_settings.home, env_file=tmp_env_file)
    # 検証
    assert result.returncode == 0, result.stderr
    written = tmp_env_file.read_text(encoding="utf-8")
    assert "export AI_MONITOR_LABEL_" in written
    assert "WIKI_BASE" not in written
    assert "監視対象として解決できませんでした" in result.stdout
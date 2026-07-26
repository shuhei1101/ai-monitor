"""`src/ai_monitor/features/agents/docs.py` の単体テスト。"""
from __future__ import annotations

import pytest

from ai_monitor.features.agents import docs

REMOTE_BASE = "https://raw.example.com/owner/repo/master/docs/wiki"
PROJECT_REMOTE_BASE = "https://raw.example.com/owner/proj/master/docs/wiki"

HARNESS_README = (
    "# Claudeハーネス\n"
    "\n"
    "## 目次\n"
    "\n"
    "| ページ | 概要 |\n"
    "| --- | --- |\n"
    "| [エージェント参照ドキュメント対応表](./共通対応表/エージェント参照ドキュメント対応表.md) | 共通の星取り表 |\n"
    "| [プロジェクトドキュメント対応表](./対応表/プロジェクトドキュメント対応表.md) | 固有の星取り表 |\n"
    "| [環境変数の解決](./共通ルール/環境変数の解決.md) | 共通手順 |\n"
)
COMMON_MATRIX = (
    "| ドキュメント | subsystem-conductor | architect |\n"
    "| --- | --- | --- |\n"
    "| [規約/コメント.md](../../規約/コメント.md) | ○ | - |\n"
)
PROJECT_MATRIX = (
    "| ドキュメント | subsystem-conductor | architect |\n"
    "| --- | --- | --- |\n"
    "| [設計図/画面構成.md](../../設計図/画面構成.md) | ○ | - |\n"
)
WIKI_README = (
    "## 目次\n"
    "\n"
    "| ページ | 概要 |\n"
    "| --- | --- |\n"
    "| [規約](./規約.md) | 規約ページ |\n"
)


def _write(root, pages: dict[str, str]) -> str:
    """一時ディレクトリにページ群を作成し、ベースとなる絶対パスを返す。"""
    for rel, body in pages.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return str(root)


@pytest.fixture
def phase_config(tmp_path, monkeypatch):
    """一時フォルダに agent_phases.yaml を作成して読み込ませる factory。"""

    def _create(mapping: dict[str, list[str]]) -> None:
        lines = []
        for agent, paths in mapping.items():
            lines.append(f"{agent}:")
            lines.extend(f"  - {path}" for path in paths)
        path = tmp_path / "agent_phases.yaml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.setattr(docs, "PHASE_CONFIG_PATH", path)

    return _create


@pytest.fixture
def ai_monitor_wiki(tmp_path):
    """ai-monitor 側の Wiki（ハーネス README + 共通対応表 + 共通ルール）を作る factory。"""

    def _create(pages: dict[str, str] | None = None) -> str:
        root = tmp_path / "ai-monitor-wiki"
        return _write(
            root,
            {
                "Claudeハーネス/README.md": HARNESS_README,
                "Claudeハーネス/共通対応表/エージェント参照ドキュメント対応表.md": COMMON_MATRIX,
                "Claudeハーネス/共通ルール/環境変数の解決.md": "# 環境変数の解決\n",
                "規約/コメント.md": "# 規約: コメント\n",
                **(pages or {}),
            },
        )

    return _create


@pytest.fixture
def project_wiki(tmp_path):
    """プロジェクト側の Wiki（ハーネス README + 対応表 + 索引用 README）を作る factory。"""

    def _create(pages: dict[str, str] | None = None) -> str:
        root = tmp_path / "project-wiki"
        return _write(
            root,
            {
                "Claudeハーネス/README.md": HARNESS_README,
                "Claudeハーネス/対応表/プロジェクトドキュメント対応表.md": PROJECT_MATRIX,
                "設計図/画面構成.md": "# 画面構成\n",
                "README.md": WIKI_README,
                "規約.md": "# 規約\n",
                **(pages or {}),
            },
        )

    return _create


# =========================
# load_phase_config
# =========================


def test_load_phase_config(phase_config):
    """YAML の読み取り（正常系）。"""
    # 準備
    phase_config({"subsystem-conductor": ["エージェント/subsystem-conductor/README.md"]})
    # 実行
    config = docs.load_phase_config()
    # 検証
    assert config.phases == {
        "subsystem-conductor": ["エージェント/subsystem-conductor/README.md"]
    }


def test_load_phase_config_when_missing(tmp_path, monkeypatch):
    """YAML 不在（異常系）。"""
    # 準備
    monkeypatch.setattr(docs, "PHASE_CONFIG_PATH", tmp_path / "missing.yaml")
    # 実行・検証
    with pytest.raises(FileNotFoundError):
        docs.load_phase_config()


# =========================
# build_phase_docs
# =========================


def test_build_phase_docs(tmp_path, phase_config):
    """設定順の連結（正常系）。"""
    # 準備
    base = _write(
        tmp_path / "wiki",
        {
            "エージェント/sc/README.md": "---\ntemplate_version: 1.0.0\n---\n\n# 索引\n",
            "エージェント/sc/フェーズ/初期処理.md": "# 初期処理\n",
        },
    )
    phase_config({"subsystem-conductor": ["エージェント/sc/README.md", "エージェント/sc/フェーズ/初期処理.md"]})
    # 実行
    text = docs.build_phase_docs("subsystem-conductor", wiki_base=base)
    # 検証: 設定順に連結され front matter を含まない
    assert text.index("# 索引") < text.index("# 初期処理")
    assert "template_version" not in text


def test_build_phase_docs_when_remote_base(fake_wiki, phase_config):
    """リモートベースの取得（正常系）。"""
    # 準備
    fake_wiki.pages[f"{REMOTE_BASE}/エージェント/sc/フェーズ/初期処理.md"] = "# 初期処理\n"
    phase_config({"subsystem-conductor": ["エージェント/sc/フェーズ/初期処理.md"]})
    # 実行
    text = docs.build_phase_docs("subsystem-conductor", wiki_base=REMOTE_BASE)
    # 検証: 非 ASCII を quote した URL でリクエストされる
    assert "# 初期処理" in text
    assert fake_wiki.calls
    assert all("%E3%82%A8" in call for call in fake_wiki.calls)


def test_build_phase_docs_when_agent_missing(tmp_path, phase_config):
    """エージェント未登録（異常系）。"""
    # 準備
    phase_config({"architect": ["エージェント/architect/README.md"]})
    # 実行・検証
    with pytest.raises(KeyError):
        docs.build_phase_docs("subsystem-conductor", wiki_base=str(tmp_path))


def test_build_phase_docs_when_page_missing(tmp_path, phase_config):
    """ページ不在（異常系）。"""
    # 準備
    phase_config({"subsystem-conductor": ["エージェント/sc/README.md"]})
    # 実行・検証
    with pytest.raises(FileNotFoundError):
        docs.build_phase_docs("subsystem-conductor", wiki_base=str(tmp_path))


# =========================
# build_reference_docs
# =========================


def test_build_reference_docs(ai_monitor_wiki, project_wiki):
    """○ のドキュメントの連結（正常系）。"""
    # 準備
    common_base = ai_monitor_wiki()
    proj_base = project_wiki()
    # 実行
    text = docs.build_reference_docs(
        "subsystem-conductor",
        ai_monitor_wiki_base=common_base,
        project_wiki_base=proj_base,
    )
    # 検証: 共通 → プロジェクトの順で連結される
    assert text.index("# 規約: コメント") < text.index("# 画面構成")


def test_build_reference_docs_when_remote_base(fake_wiki):
    """リモートベースの取得（正常系）。"""
    # 準備
    fake_wiki.pages[f"{REMOTE_BASE}/Claudeハーネス/README.md"] = HARNESS_README
    fake_wiki.pages[
        f"{REMOTE_BASE}/Claudeハーネス/共通対応表/エージェント参照ドキュメント対応表.md"
    ] = COMMON_MATRIX
    fake_wiki.pages[f"{REMOTE_BASE}/Claudeハーネス/共通ルール/環境変数の解決.md"] = "# 環境変数の解決\n"
    fake_wiki.pages[f"{REMOTE_BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    fake_wiki.pages[f"{PROJECT_REMOTE_BASE}/Claudeハーネス/README.md"] = HARNESS_README
    fake_wiki.pages[
        f"{PROJECT_REMOTE_BASE}/Claudeハーネス/対応表/プロジェクトドキュメント対応表.md"
    ] = PROJECT_MATRIX
    fake_wiki.pages[f"{PROJECT_REMOTE_BASE}/設計図/画面構成.md"] = "# 画面構成\n"
    # 実行
    text = docs.build_reference_docs(
        "subsystem-conductor",
        ai_monitor_wiki_base=REMOTE_BASE,
        project_wiki_base=PROJECT_REMOTE_BASE,
    )
    # 検証: HTTP 経由で両方の本文が取れる
    assert "# 規約: コメント" in text
    assert "# 画面構成" in text
    assert fake_wiki.calls


def test_build_reference_docs_when_mixed_base(ai_monitor_wiki, fake_wiki):
    """ベースの混在（正常系）。"""
    # 準備: ai-monitor 側はローカル・プロジェクト側はリモート
    common_base = ai_monitor_wiki()
    fake_wiki.pages[f"{PROJECT_REMOTE_BASE}/Claudeハーネス/README.md"] = HARNESS_README
    fake_wiki.pages[
        f"{PROJECT_REMOTE_BASE}/Claudeハーネス/対応表/プロジェクトドキュメント対応表.md"
    ] = PROJECT_MATRIX
    fake_wiki.pages[f"{PROJECT_REMOTE_BASE}/設計図/画面構成.md"] = "# 画面構成\n"
    # 実行
    text = docs.build_reference_docs(
        "subsystem-conductor",
        ai_monitor_wiki_base=common_base,
        project_wiki_base=PROJECT_REMOTE_BASE,
    )
    # 検証: ローカル側はファイル・プロジェクト側は HTTP で読まれる
    assert "# 規約: コメント" in text
    assert "# 画面構成" in text
    assert all(call.startswith(PROJECT_REMOTE_BASE.split("/master")[0]) for call in fake_wiki.calls)


def test_build_reference_docs_when_absolute_url_row(tmp_path, project_wiki, fake_wiki):
    """絶対 URL の行（正常系）。"""
    # 準備: ローカルのベースで、共通対応表の行が絶対 URL を指す
    external = "https://raw.example.com/other/repo/master/docs/rules/規約.md"
    common_base = _write(
        tmp_path / "ai-monitor-wiki",
        {
            "Claudeハーネス/README.md": HARNESS_README,
            "Claudeハーネス/共通対応表/エージェント参照ドキュメント対応表.md": (
                "| ドキュメント | subsystem-conductor |\n"
                "| --- | --- |\n"
                f"| [外部規約]({external}) | ○ |\n"
            ),
            "Claudeハーネス/共通ルール/環境変数の解決.md": "# 環境変数の解決\n",
        },
    )
    fake_wiki.pages[external] = "# 外部規約\n"
    proj_base = project_wiki()
    # 実行
    text = docs.build_reference_docs(
        "subsystem-conductor",
        ai_monitor_wiki_base=common_base,
        project_wiki_base=proj_base,
    )
    # 検証: その行だけ HTTP で読まれる
    assert "# 外部規約" in text
    assert len(fake_wiki.calls) == 1


def test_build_reference_docs_when_project_matrix_missing(ai_monitor_wiki, tmp_path):
    """プロジェクト対応表の不在（正常系）。"""
    # 準備: プロジェクト側に Claudeハーネス を置かない
    common_base = ai_monitor_wiki()
    proj_base = _write(tmp_path / "empty-wiki", {"README.md": WIKI_README})
    # 実行
    text = docs.build_reference_docs(
        "subsystem-conductor",
        ai_monitor_wiki_base=common_base,
        project_wiki_base=proj_base,
    )
    # 検証: 共通分だけが返る
    assert "# 規約: コメント" in text
    assert "# 画面構成" not in text


def test_build_reference_docs_when_not_marked(ai_monitor_wiki, project_wiki):
    """○ なしのエージェント（正常系）。"""
    # 準備: architect は全行が `-`
    common_base = ai_monitor_wiki()
    proj_base = project_wiki()
    # 実行
    text = docs.build_reference_docs(
        "architect",
        ai_monitor_wiki_base=common_base,
        project_wiki_base=proj_base,
    )
    # 検証: 共通ルールだけで、○ のドキュメントは含まれない
    assert "# 規約: コメント" not in text
    assert "# 画面構成" not in text


# =========================
# build_agent_docs
# =========================


def test_build_agent_docs(tmp_path, phase_config, ai_monitor_wiki, project_wiki, mon_project):
    """3 要素の連結（正常系）。"""
    # 準備
    common_base = ai_monitor_wiki(
        {"エージェント/sc/フェーズ/初期処理.md": "# 初期処理\n"}
    )
    proj_base = project_wiki()
    phase_config({"subsystem-conductor": ["エージェント/sc/フェーズ/初期処理.md"]})
    mon_project.wiki_base = proj_base
    # 実行
    text = docs.build_agent_docs(
        "subsystem-conductor", mon_project, ai_monitor_wiki_base=common_base
    )
    # 検証: 見出しとフェーズ本文・参考資料・索引が順に並ぶ
    assert "## フェーズ" in text
    assert "## 参考資料" in text
    assert text.index("# 初期処理") < text.index("# 規約: コメント")
    assert "規約.md" in text


def test_build_agent_docs_when_remote_base(fake_wiki, phase_config, mon_project):
    """リモートベースの取得（正常系）。"""
    # 準備
    fake_wiki.pages[f"{REMOTE_BASE}/エージェント/sc/フェーズ/初期処理.md"] = "# 初期処理\n"
    fake_wiki.pages[f"{REMOTE_BASE}/Claudeハーネス/README.md"] = HARNESS_README
    fake_wiki.pages[
        f"{REMOTE_BASE}/Claudeハーネス/共通対応表/エージェント参照ドキュメント対応表.md"
    ] = COMMON_MATRIX
    fake_wiki.pages[f"{REMOTE_BASE}/Claudeハーネス/共通ルール/環境変数の解決.md"] = "# 環境変数の解決\n"
    fake_wiki.pages[f"{REMOTE_BASE}/規約/コメント.md"] = "# 規約: コメント\n"
    fake_wiki.pages[f"{PROJECT_REMOTE_BASE}/Claudeハーネス/README.md"] = HARNESS_README
    fake_wiki.pages[
        f"{PROJECT_REMOTE_BASE}/Claudeハーネス/対応表/プロジェクトドキュメント対応表.md"
    ] = PROJECT_MATRIX
    fake_wiki.pages[f"{PROJECT_REMOTE_BASE}/設計図/画面構成.md"] = "# 画面構成\n"
    fake_wiki.pages[f"{PROJECT_REMOTE_BASE}/README.md"] = WIKI_README
    phase_config({"subsystem-conductor": ["エージェント/sc/フェーズ/初期処理.md"]})
    mon_project.wiki_base = PROJECT_REMOTE_BASE
    # 実行
    text = docs.build_agent_docs(
        "subsystem-conductor", mon_project, ai_monitor_wiki_base=REMOTE_BASE
    )
    # 検証: 3 要素が揃う
    assert "# 初期処理" in text
    assert "# 規約: コメント" in text
    assert "規約.md" in text

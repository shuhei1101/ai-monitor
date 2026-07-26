"""エージェントの起動プロンプトに載せるドキュメントの組み立て。"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pydantic import BaseModel

from ai_monitor.shared.settings import MonitoredProject

# 取得ロジックの実体は注入 CLI 側に置く（CLI はプラグインのインストール先から起動され src/ を参照できない）
INJECT_DIR = Path(__file__).resolve().parents[4] / "plugins" / "ai-monitor" / "inject"
sys.path.insert(0, str(INJECT_DIR))

from build_wiki_index import walk_wiki  # noqa: E402
from fetch import select_reader  # noqa: E402
from read_agent_docs import list_harness_pages, parse_matrix  # noqa: E402
from read_urls import strip_frontmatter  # noqa: E402

# エージェント名 → フェーズページのパス一覧（ai-monitor のメインリポジトリ直下）
PHASE_CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "agent_phases.yaml"


class PhaseConfig(BaseModel):
    """`config/agent_phases.yaml` の読み取り結果。"""

    phases: dict[str, list[str]]


def load_phase_config() -> PhaseConfig:
    """`config/agent_phases.yaml` を読み、エージェント名 → フェーズページのパス一覧を返す。"""
    # ai-monitor のメインリポジトリ直下の YAML を読む
    raw = PHASE_CONFIG_PATH.read_text(encoding="utf-8")
    # エージェント名 → パス一覧の辞書に変換する
    return PhaseConfig(phases=yaml.safe_load(raw) or {})


def build_phase_docs(agent_name: str, *, wiki_base: str) -> str:
    """エージェントのフェーズページを設定順に読み、1 本のテキストに連結する。"""
    # フェーズ設定を読む
    config = load_phase_config()
    if agent_name not in config.phases:
        raise KeyError(agent_name)
    # パス一覧をベースと連結して場所にする
    base = wiki_base.rstrip("/")
    locations = [f"{base}/{rel}" for rel in config.phases[agent_name]]
    # ベースで取得手段を選ぶ（同一ベース配下なので 1 度だけ選べばよい）
    read = select_reader(base)
    # 各場所を読み、front matter を除去して連結する
    return "\n\n".join(strip_frontmatter(read(location)).strip() for location in locations)


def build_reference_docs(
    agent_name: str, *, ai_monitor_wiki_base: str, project_wiki_base: str
) -> str:
    """対応表で当該エージェントに ○ が付いたドキュメントを読み、1 本のテキストに連結する。"""
    common_base = ai_monitor_wiki_base.rstrip("/")
    project_base = project_wiki_base.rstrip("/")
    common_read = select_reader(common_base)
    # ai-monitor 側の対応表と共通ルールのページ一覧を得る
    common_pages = list_harness_pages(common_base, read=common_read)
    # プロジェクト側の対応表を得る（対応表が無いプロジェクトは共通分だけを対象にする）
    project_pages: dict[str, list[tuple[str, str]]] = {"対応表": []}
    if project_base == common_base:
        project_pages = common_pages
    else:
        try:
            project_pages = list_harness_pages(project_base, read=select_reader(project_base))
        except OSError:  # URLError（取得失敗）と FileNotFoundError（ファイル不在）の両方
            pass

    # 共通 → プロジェクトの順で ○ の付いた場所を集める
    locations: list[str] = [f"{common_base}/{path}" for _display, path in common_pages["共通ルール"]]
    matrix_sources = [
        (common_base, common_pages.get("共通対応表", [])),
        (project_base, project_pages.get("対応表", [])),
    ]
    for base, entries in matrix_sources:
        read = select_reader(base)
        for _display, path in entries:
            matrix = parse_matrix(read(f"{base}/{path}"), base)
            locations.extend(url for _name, url in matrix.get(agent_name, []))

    # 場所ごとに取得手段を選んで読む（対応表の行は絶対 URL を指せる）
    bodies = [strip_frontmatter(select_reader(loc)(loc)).strip() for loc in locations]
    return "\n\n".join(bodies)


def build_agent_docs(
    agent_name: str, project: MonitoredProject, *, ai_monitor_wiki_base: str
) -> str:
    """フェーズ + 参考資料 + Wiki 索引を 1 本のテキストにまとめる。"""
    # フェーズ本文を組み立てる
    phases = build_phase_docs(agent_name, wiki_base=ai_monitor_wiki_base)
    # 参考資料を組み立てる
    references = build_reference_docs(
        agent_name,
        ai_monitor_wiki_base=ai_monitor_wiki_base,
        project_wiki_base=project.wiki_base,
    )
    # 監視対象プロジェクトの Wiki 索引を組み立てる
    project_base = project.wiki_base.rstrip("/")
    pages = walk_wiki(project_base, read=select_reader(project_base))
    index_lines = ["| ページ | 概要 |", "| --- | --- |"]
    index_lines += [f"| {page.raw_url} | {page.summary} |" for page in pages]
    index = "\n".join(index_lines)
    # 見出しを付けて連結する
    return f"## フェーズ\n\n{phases}\n\n## 参考資料\n\n{references}\n\n{index}\n"

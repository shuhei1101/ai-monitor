#!/usr/bin/env python3
"""エージェント名から参照ドキュメント一式を標準出力に展開する CLI。"""
from __future__ import annotations

import os
import re
import sys

from fetch import fetch_url

HARNESS_README = "Claudeハーネス/README.md"
CATEGORIES = ("共通対応表", "対応表", "共通ルール")


def list_harness_pages(base_url: str) -> dict[str, list[tuple[str, str]]]:
    """`Claudeハーネス/README.md` の目次を分類フォルダごとに列挙する。"""
    # Claudeハーネス/README.md を取得する
    text = fetch_url(f"{base_url}/{HARNESS_README}")
    # 目次のリンクをパスの分類フォルダごとに振り分ける（分類フォルダ外のリンクは無視する）
    pages: dict[str, list[tuple[str, str]]] = {category: [] for category in CATEGORIES}
    for display, target in re.findall(r"\[([^\]]+)\]\(([^)]+?\.md)\)", text):
        path = target.removeprefix("./")
        category = path.split("/")[0]
        if category in pages:
            pages[category].append((display, f"Claudeハーネス/{path}"))
    return pages


def parse_matrix(text: str, base_url: str) -> dict[str, list[tuple[str, str]]]:
    """星取り表を {エージェント名: [(表示名, 取得 URL), ...]} に変換する。"""
    # 本文から表の行を抽出する
    rows = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        raise ValueError("星取り表が見つからない")
    # ヘッダー行からエージェント名の列を確定する
    header = [cell.strip() for cell in rows[0].strip("|").split("|")]
    agents = header[1:]
    result: dict[str, list[tuple[str, str]]] = {agent: [] for agent in agents}
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        # 各行の先頭セルを（表示名, 取得 URL）に解決する
        m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", cells[0])
        if not m:
            continue
        display, target = m.group(1), m.group(2)
        if target.startswith(("http://", "https://")):
            # 絶対 URL のリンク: リンク先をそのまま取得 URL にする
            url = target
        else:
            # Wiki 相対リンク: base_url 配下のパスとして取得 URL にする
            path = re.sub(r"^(\.\./)+|^\./", "", target)
            url = f"{base_url}/{path}"
        # ○ の付いたセルのエージェントへ行のドキュメントを対応付ける
        for agent, mark in zip(agents, cells[1:]):
            if mark == "○":
                result[agent].append((display, url))
    return result


def main() -> int:
    """エージェント名を受けて、共通ルール一式と全対応表で ○ の付いた参照ドキュメント一式を標準出力に展開する。"""
    # コマンドライン引数 agent_name をパースする
    if len(sys.argv) < 2:
        print("usage: read_agent_docs.py <agent_name>", file=sys.stderr)
        return 1
    agent_name = sys.argv[1]
    # 環境変数 WIKI_BASE / AI_MONITOR_WIKI_BASE を読む
    project_base = os.environ.get("WIKI_BASE")
    if not project_base:
        print("環境変数 WIKI_BASE が未設定です", file=sys.stderr)
        return 1
    common_base = os.environ.get("AI_MONITOR_WIKI_BASE")
    if not common_base:
        print("環境変数 AI_MONITOR_WIKI_BASE が未設定です", file=sys.stderr)
        return 1
    # 共通側 README から共通対応表と共通ルールのページ一覧を得る
    common_pages = list_harness_pages(common_base)
    # プロジェクト側 README から対応表のページ一覧を得る（同一ベースなら README が同一ファイルのため取得結果を使い回す）
    project_pages = common_pages if project_base == common_base else list_harness_pages(project_base)
    # 対応表（共通対応表 → 対応表の順）を取得・解析してエージェントごとの対応をマージする
    merged: dict[str, list[tuple[str, str]]] = {}
    matrix_sources = [
        (common_base, common_pages["共通対応表"]),
        (project_base, project_pages["対応表"]),
    ]
    for base, entries in matrix_sources:
        for _display, path in entries:
            matrix = parse_matrix(fetch_url(f"{base}/{path}"), base)
            for agent, docs in matrix.items():
                merged.setdefault(agent, []).extend(docs)
    # agent_name の対応を確定する
    if agent_name not in merged:
        print(f"未知のエージェント名: {agent_name}", file=sys.stderr)
        print(f"有効なエージェント名: {', '.join(merged)}", file=sys.stderr)
        return 1
    # 共通ルールページ → ○ の付いた対応ドキュメントの順に取得し、ラベル行 + md コードブロックで標準出力に出す
    outputs = [(display, f"{common_base}/{path}") for display, path in common_pages["共通ルール"]]
    outputs += merged[agent_name]
    for display, url in outputs:
        body = fetch_url(url)
        print(f"**{display}:**")
        print("`````md")
        print(body.rstrip("\n"))
        print("`````")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""プロジェクト Wiki の README を再帰的に辿ってフラット索引を標準出力に展開する CLI。"""
from __future__ import annotations

import os
import re
import sys
import urllib.error

from pydantic import BaseModel, ConfigDict

from fetch import fetch_url


class WikiPage(BaseModel):
    """Wiki 索引 1 件（raw URL + 概要）。"""

    model_config = ConfigDict(frozen=True)

    raw_url: str
    summary: str


# `## 目次` 見出しの直後にある表を抽出する（表末尾は空行 or ファイル末尾）
_TOC_TABLE_RE = re.compile(
    r"^##\s*目次\s*$\r?\n(?:\r?\n)*(\|.*(?:\r?\n\|.*)*)",
    re.MULTILINE,
)
# 目次表「ページ」セルの Markdown リンク `[表示](./xxx)` から URL 部分を取り出す
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def parse_index_table(text: str, folder_path: str) -> list[WikiPage]:
    """README 本文の `## 目次` 表を解析し、各リンクを raw URL 化した WikiPage 配列で返す。"""
    # 環境変数 WIKI_BASE を読む（末尾スラッシュがあれば落とす）
    wiki_base = os.environ["WIKI_BASE"].rstrip("/")

    # ## 目次 見出しの次にある表を抽出する（見出しが無ければ ValueError）
    match = _TOC_TABLE_RE.search(text)
    if not match:
        raise ValueError("目次見出しなし")
    table_lines = match.group(1).splitlines()
    if len(table_lines) < 2:
        raise ValueError("ページ／概要列なし")

    # ヘッダー行から「ページ」列と「概要」列のインデックスを特定する（他の列があってもよい）
    header_cells = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    try:
        page_idx = header_cells.index("ページ")
        summary_idx = header_cells.index("概要")
    except ValueError as exc:
        raise ValueError("ページ／概要列なし") from exc

    # 各データ行を先頭から順にループし、WikiPage を組み立てて戻り値配列に追加する
    pages: list[WikiPage] = []
    for line in table_lines[2:]:  # 0: header, 1: --- 区切り, 2以降: データ
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) <= max(page_idx, summary_idx):
            continue
        # リンク URL 部分（ファイル名）を取り出し、先頭 ./ を落とす
        link_match = _LINK_RE.search(cells[page_idx])
        if not link_match:
            continue
        link = link_match.group(1).removeprefix("./")
        # 末尾が / ならサブディレクトリ → README.md を補完
        if link.endswith("/"):
            link += "README.md"
        # folder_path を前置して Wiki ルート相対パスを組み立てる
        rel = f"{folder_path}/{link}" if folder_path else link
        # {WIKI_BASE}/{rel} で raw URL 化して WikiPage を追加
        pages.append(WikiPage(raw_url=f"{wiki_base}/{rel}", summary=cells[summary_idx]))
    return pages


def walk_wiki(folder_path: str = "") -> list[WikiPage]:
    """ルート README から目次表を辿って全 md ページのエントリを平坦化する。"""
    # 環境変数 WIKI_BASE を読む
    wiki_base = os.environ["WIKI_BASE"].rstrip("/")
    # {WIKI_BASE}/{folder_path}/README.md を取得（folder_path 空ならルート直下）
    readme_url = f"{wiki_base}/{folder_path}/README.md" if folder_path else f"{wiki_base}/README.md"
    body = fetch_url(readme_url)

    # 目次表を WikiPage 配列に展開（書式違反はそのフォルダ配下を空として返す = 意図的な非公開運用）
    try:
        pages = parse_index_table(body, folder_path)
    except ValueError:
        return []

    # 空の戻り値配列を用意し、各 WikiPage を分類しながら追加する
    result: list[WikiPage] = []
    readme_suffix = "/README.md"
    prefix = f"{wiki_base}/"
    for page in pages:
        # まず WikiPage 自体を戻り値配列に追加
        result.append(page)
        # raw_url が /README.md で終わる場合はサブディレクトリ → 再帰
        if page.raw_url.endswith(readme_suffix):
            # {WIKI_BASE}/ と /README.md を落として folder_path を計算
            sub_folder = page.raw_url[len(prefix):-len(readme_suffix)]
            result.extend(walk_wiki(sub_folder))
    return result


def main() -> int:
    """プロジェクト Wiki の全 md ページを「ページ / 概要」2 列表で標準出力に展開する。"""
    # 環境変数 WIKI_BASE を読む（未設定なら stderr にメッセージを出して 1 を返す）
    if not os.environ.get("WIKI_BASE"):
        print("環境変数 WIKI_BASE が未設定です", file=sys.stderr)
        return 1

    # walk_wiki で全エントリを得る（URLError は stderr + 1）
    try:
        pages = walk_wiki()
    except urllib.error.URLError as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1

    # ラベル行 + 空行 + md テーブルとして標準出力に出す
    print("**Wiki索引:**")
    print()
    print("| ページ | 概要 |")
    print("| --- | --- |")
    for page in pages:
        print(f"| {page.raw_url} | {page.summary} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Wiki ページを実行時に取得する MCP ツール。"""
from __future__ import annotations

import logging
import sys
import urllib.error
from pathlib import Path

from ai_monitor.mcp.models import WikiPage, WikiPagesResult

# 取得ロジックの実体は注入 CLI 側に置く（CLI はプラグインのインストール先から起動され src/ を参照できない）
INJECT_DIR = Path(__file__).resolve().parents[3] / "plugins" / "ai-monitor" / "inject"
sys.path.insert(0, str(INJECT_DIR))

from fetch import fetch_url  # noqa: E402
from read_urls import normalize_github_url, strip_frontmatter  # noqa: E402

logger = logging.getLogger(__name__)


class WikiFetchError(Exception):
    """Wiki ページを取得できない。"""


def read_wiki_pages(urls: list[str]) -> WikiPagesResult:
    """指定 URL の Wiki ページ本文を取得して配列で返す。"""
    pages: list[WikiPage] = []
    for raw in urls:
        # blob URL を raw URL に正規化する
        url = normalize_github_url(raw)
        # 正規化した URL から本文を取得する
        try:
            body = fetch_url(url)
        except urllib.error.URLError as exc:
            logger.warning("Wiki ページの取得に失敗しました: url=%s", url)
            raise WikiFetchError(f"Wiki ページを取得できません: {url}: {exc}") from exc
        # 先頭の YAML front matter を除去して詰める
        pages.append(WikiPage(url=url, body=strip_frontmatter(body)))
    # 指定順のまま返す
    return WikiPagesResult(pages=pages)

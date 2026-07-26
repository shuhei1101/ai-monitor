"""Wiki ページを実行時に取得する MCP ツール。"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from ai_monitor.mcp.models import WikiPage, WikiPageFailure, WikiPagesResult

# 取得ロジックの実体は注入 CLI 側に置く（CLI はプラグインのインストール先から起動され src/ を参照できない）
INJECT_DIR = Path(__file__).resolve().parents[3] / "plugins" / "ai-monitor" / "inject"
sys.path.insert(0, str(INJECT_DIR))

from fetch import select_reader  # noqa: E402
from read_urls import normalize_github_url, strip_frontmatter  # noqa: E402

logger = logging.getLogger(__name__)


def read_wiki_pages(locations: list[str]) -> WikiPagesResult:
    """指定した場所の Wiki ページ本文を取得し、取得できた分と失敗した分を返す。"""
    pages: list[WikiPage] = []
    failures: list[WikiPageFailure] = []
    for raw in locations:
        # blob URL を raw URL に正規化する（ローカル絶対パスはそのまま）
        url = normalize_github_url(raw)
        # 場所の形から取得手段を選び、本文を取得する
        try:
            body = select_reader(url)(url)
        except OSError as exc:  # URLError（取得失敗）と FileNotFoundError（ファイル不在）の両方
            # 失敗した場所は理由とともに記録し、残りの取得は続ける
            reason = str(getattr(exc, "reason", None) or exc)
            logger.warning("Wiki ページの取得に失敗しました: url=%s reason=%s", url, reason)
            failures.append(WikiPageFailure(url=url, reason=reason))
            continue
        # 先頭の YAML front matter を除去して詰める
        pages.append(WikiPage(url=url, body=strip_frontmatter(body)))
    # 指定順のまま返す
    return WikiPagesResult(pages=pages, failures=failures)

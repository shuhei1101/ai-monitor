from __future__ import annotations

import re

# Jekyll などの YAML front matter を先頭から剥がすための正規表現。
# 位置は先頭固定（^）、`---\n ... \n---\n` を最短マッチで捕まえる。
_YAML_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)


def normalize_github_url(url: str) -> str:
    """github.com/{owner}/{repo}/blob/{rest} を raw.githubusercontent.com の URL に変換する。

    マッチしなければ url をそのまま返す。
    """
    m = re.match(
        r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/blob/(.+)$",
        url,
    )
    if not m:
        return url
    owner, repo, rest = m.group(1), m.group(2), m.group(3)
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"


def strip_yaml_frontmatter(text: str) -> str:
    """Markdown 冒頭の YAML front matter（`---\\n...\\n---\\n`）を 1 ブロックだけ剥がす。

    Jekyll などが要求する front matter を raw MD として取得したときに、
    そのままプロンプト / 出力に混ざるのを防ぐためのユーティリティ。
    先頭に front matter が無ければ text をそのまま返す。
    """
    return _YAML_FRONTMATTER_RE.sub("", text, count=1)

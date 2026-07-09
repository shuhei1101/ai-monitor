"""指定 URL のコンテンツを取得して標準出力に返す（GitHub blob URL は raw に自動変換、複数 URL 対応）。"""
from __future__ import annotations

import argparse
import sys
import traceback
import urllib.error
import urllib.request

from utils import normalize_github_url, strip_yaml_frontmatter

# 終了コード
EXIT_OK = 0
EXIT_FETCH_FAILED = 2  # 少なくとも 1 件の URL で取得失敗


def parse_args() -> argparse.Namespace:
    """コマンドライン引数をパースして返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+", help="取得対象 URL（1 件以上、GitHub blob URL は raw に自動変換）")
    return parser.parse_args()


def fetch_url(url: str) -> str:
    """指定 URL の本文を取得して文字列で返す。"""
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8")


def main() -> int:
    args = parse_args()

    exit_code = EXIT_OK
    for raw_url in args.urls:
        url = normalize_github_url(raw_url)
        try:
            content = fetch_url(url)
            # raw MD の先頭に Jekyll などの YAML front matter が付いていたら剥がす
            content = strip_yaml_frontmatter(content)
            # 取得元 URL をメタ情報に含めた md コードフェンスで包む（複数 URL のとき境界が分かる）
            # フェンスは 5 連バッククォート: 取得内容に ``` や ```` のコードブロックが含まれても閉じ判定されないようにする
            print(f"`````md:{url}")
            print(content)
            print("`````")
        except urllib.error.URLError as exc:
            # ネットワーク到達不能・HTTP エラー等。URL を stderr に出して継続
            print(f"取得失敗: {url}: {exc}", file=sys.stderr)
            exit_code = EXIT_FETCH_FAILED

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # 想定外の例外はトレースバック出力して異常終了
        traceback.print_exc()
        sys.exit(1)

"""ラベル一括作成 CLI の composition root。"""
from __future__ import annotations

import argparse
import logging
import sys

from githubkit.exception import RequestFailed

from ai_monitor.integrations.github.client import get_client
from ai_monitor.setup_labels.github import create_label, list_labels, update_label
from ai_monitor.setup_labels.sync import (
    LabelStyleSettings,
    SyncResult,
    build_label_specs,
    sync_labels,
)
from ai_monitor.shared.settings import Settings

logger = logging.getLogger(__name__)

# 終了コード
EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_API_ERROR = 2


def main() -> int:
    """コマンドライン引数を解析し、対象リポジトリごとにラベルを同期して結果を出力する。"""
    # --repo と --dry-run を解析する
    parser = argparse.ArgumentParser(
        prog="ai_monitor.setup_labels",
        description="constants.env が持つ全ラベルを、監視対象リポジトリに作成 / 更新する。",
    )
    parser.add_argument("--repo", help="対象リポジトリ（owner/name）。省略時は settings.yaml の projects[] 全件")
    parser.add_argument("--dry-run", action="store_true", help="作成 / 更新の内容を出力するだけで API を呼ばない")
    args = parser.parse_args()

    # Settings と LabelStyleSettings を読み込む
    settings = Settings()
    styles = LabelStyleSettings()
    get_client(settings)

    # 対象プロジェクトを決める
    registered = [project.repo for project in settings.projects]
    if args.repo is None:
        # 指定なし: projects[] の全件を対象にする
        targets = registered
    elif args.repo in registered:
        # 指定あり: その 1 件を対象にする
        targets = [args.repo]
    else:
        # 未登録: 登録済みリポジトリ一覧を出して設定エラーで終える
        logger.error("未登録のリポジトリが指定されました: repo=%s", args.repo)
        print(f"settings.yaml の projects[] に未登録のリポジトリです: {args.repo}", file=sys.stderr)
        print(f"登録済み: {', '.join(registered)}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    # あるべきラベル一覧を作る
    specs = build_label_specs(styles=styles)

    # 対象リポジトリごとに GitHub 操作 3 種を注入して反映する
    results: list[SyncResult] = []
    for repo in targets:
        try:
            results.append(
                sync_labels(
                    repo,
                    specs,
                    list_labels=list_labels,
                    create_label=create_label,
                    update_label=update_label,
                    dry_run=args.dry_run,
                )
            )
        except RequestFailed as exc:
            # 1 リポジトリの不具合で全体を止めず、失敗として記録して次へ進む
            code, reason = exc.response.status_code, exc.response.reason_phrase
            status = f"{code} {reason}" if reason else str(code)
            logger.error("ラベルの反映に失敗しました: repo=%s status=%s", repo, status)
            print(f"{repo}: GitHub API が {status} を返しました", file=sys.stderr)
            results.append(SyncResult(repo=repo, error=status))

    # リポジトリごとに整形結果を標準出力へ書く
    for result in results:
        print(format_result(result))

    # 失敗の有無で終了コードを決める
    return EXIT_API_ERROR if any(result.error for result in results) else EXIT_OK


def format_result(result: SyncResult) -> str:
    """同期結果を標準出力用の複数行テキストにする。"""
    # 失敗理由があれば 1 行だけを返す
    if result.error is not None:
        return f"{result.repo}: 失敗（{result.error}）"
    # リポジトリ名と 3 分類の件数を 1 行目に組み立てる
    lines = [
        f"{result.repo}: 作成 {len(result.created)} / 更新 {len(result.updated)}"
        f" / 変更なし {len(result.unchanged)}"
    ]
    # 作成対象があればラベル名をカンマ区切りにした行を足す
    if result.created:
        lines.append(f"  作成: {', '.join(spec.name for spec in result.created)}")
    # 更新対象があればラベル名をカンマ区切りにした行を足す
    if result.updated:
        lines.append(f"  更新: {', '.join(spec.name for spec in result.updated)}")
    # 組み立てた行を改行で連結して返す
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())

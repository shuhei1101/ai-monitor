"""稼働中の設定とエージェント定義の書き換え。"""
from __future__ import annotations

import logging

from ai_monitor.features.agents.types import Agent
from ai_monitor.features.config.types import BuildAgents, IgnoredItem, ReadSettings, ReloadResult
from ai_monitor.shared.settings import Settings

logger = logging.getLogger(__name__)

# 実行中に変えられない設定項目と、反映しない理由
# （uvicorn とセッション台帳に束ねた後なので、変えるには作り直しが要る）
FIXED_FIELDS: dict[str, str] = {
    "port": "待受ポートは実行中に変えられません（再起動が必要です）",
    "state_path": "セッション台帳のパスは実行中に変えられません（再起動が必要です）",
}


def reload_settings(
    settings: Settings,
    agents: list[Agent],
    *,
    read_settings: ReadSettings,
    build_agents: BuildAgents,
) -> ReloadResult:
    """設定を読み直し、反映できる項目だけを稼働中の設定へ書き戻して増減を返す。"""
    # 設定ファイルを読み直す（読めない場合は書き換えずに呼び出し側へ伝播する）
    latest = read_settings()
    # 実行中に変えられない項目のうち、値が変わっていたものを拾う
    ignored = [
        IgnoredItem(item=field, reason=reason)
        for field, reason in FIXED_FIELDS.items()
        if getattr(latest, field) != getattr(settings, field)
    ]
    # 監視対象プロジェクト名を突き合わせて増減を出す
    before = [project.name for project in settings.projects]
    after = [project.name for project in latest.projects]
    added = [name for name in after if name not in before]
    removed = [name for name in before if name not in after]
    # 反映対象のフィールドを稼働中の設定へ書き戻す
    # （配りっぱなしの参照へ効かせるため、入れ物を差し替えず同じオブジェクトの中身を変える）
    for field in type(settings).model_fields:
        if field in FIXED_FIELDS:
            continue
        setattr(settings, field, getattr(latest, field))
    logger.info(
        "設定を再読込しました: added=%s removed=%s ignored=%s",
        added,
        removed,
        [item.item for item in ignored],
    )
    # エージェント定義を作り直し、同じ理由でリストの中身を入れ替える
    agents[:] = build_agents(latest)
    return ReloadResult(added=added, removed=removed, ignored=ignored)

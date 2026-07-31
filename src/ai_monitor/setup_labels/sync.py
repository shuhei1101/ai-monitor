"""constants.env のラベル定数を GitHub の現状と突き合わせて反映する。"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_monitor.shared.settings import CONSTANTS_ENV

logger = logging.getLogger(__name__)

# constants.env の 1 行から KEY と値を取り出す（コメント行・空行は一致しない）
_ENTRY_PATTERN = re.compile(r'^(?P<key>[A-Z0-9_]+)="(?P<value>.*)"$')

# ラベル名になるキーの接頭辞
_LABEL_KEY_PREFIX = "AI_MONITOR_LABEL_"

# ラベル名ではなく体裁の定義であることを示す部分文字列
_STYLE_KEY_MARKERS = ("_COLOR_", "_DESC_")

# ラベル名ではなく接頭辞そのものであることを示すキーの末尾
_PREFIX_KEY_SUFFIX = "_PREFIX"

# ラベル名の接頭辞と、体裁設定のフィールド接尾辞の対応
_PREFIX_STYLES: tuple[tuple[str, str], ...] = (
    ("確認:", "confirm"),
    ("処理中:", "processing"),
    ("layer:", "layer"),
    ("type:", "type"),
    ("優先度:", "priority"),
)


# 接頭辞を持たない単独ラベルと、体裁設定のフィールド接尾辞の対応
_EXACT_STYLES: dict[str, str] = {
    "議論中": "in_discussion",
    "リバースエンジニアリング": "reverse_engineering",
    "AI不具合報告": "ai_defect_report",
}

# ラベル一覧 API の 1 ページあたりの取得件数
LABELS_PER_PAGE = 100


class LabelStyleSettings(BaseSettings):
    """`constants.env` の色と説明を接頭辞ごとに型安全に読む体裁設定。"""

    model_config = SettingsConfigDict(
        env_file=CONSTANTS_ENV, env_prefix=_LABEL_KEY_PREFIX, extra="ignore"
    )

    color_confirm: str
    desc_confirm: str
    color_processing: str
    desc_processing: str
    color_in_discussion: str
    desc_in_discussion: str
    color_reverse_engineering: str
    desc_reverse_engineering: str
    color_ai_defect_report: str
    desc_ai_defect_report: str
    color_layer: str
    desc_layer: str
    color_type: str
    desc_type: str
    color_priority: str
    desc_priority: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LabelSpec:
    """ラベル 1 件の名前・色・説明（あるべき姿と GitHub 上の現状の両方に使う）。"""

    name: str
    color: str
    description: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SyncResult:
    """1 リポジトリ分の同期結果。"""

    repo: str
    created: list[LabelSpec] = field(default_factory=list)
    updated: list[LabelSpec] = field(default_factory=list)
    unchanged: list[LabelSpec] = field(default_factory=list)
    # None 以外のとき 3 つのリストは空（他リポジトリの処理は継続する）
    error: str | None = None


type ListLabelsFn = Callable[[str], list[LabelSpec]]
type WriteLabelFn = Callable[[str, LabelSpec], None]


def build_label_specs(
    constants_path: Path = CONSTANTS_ENV, *, styles: LabelStyleSettings
) -> list[LabelSpec]:
    """`constants.env` を直接パースしてあるべきラベル一覧に変換する。"""
    specs: list[LabelSpec] = []
    # constants_path からコメント行・空行を除いた KEY="値" を読む
    for line in constants_path.read_text(encoding="utf-8").splitlines():
        matched = _ENTRY_PATTERN.match(line.strip())
        if matched is None:
            continue
        # ラベル名になるキーだけを残す
        key = matched.group("key")
        if not _is_label_key(key):
            continue
        # 残ったキーの値をラベル名として、接頭辞から色と説明を決める
        name = matched.group("value")
        suffix = _resolve_style_suffix(name)
        specs.append(
            LabelSpec(
                name=name,
                color=getattr(styles, f"color_{suffix}"),
                description=getattr(styles, f"desc_{suffix}"),
            )
        )
    # 名前の昇順に並べて返す
    return sorted(specs, key=lambda spec: spec.name)


def _is_label_key(key: str) -> bool:
    """constants.env のキーがラベル名を持つものかを返す。"""
    # テンプレートパス等の非ラベルキーを除く
    if not key.startswith(_LABEL_KEY_PREFIX):
        return False
    # 体裁の定義（色・説明）を除く
    if any(marker in key for marker in _STYLE_KEY_MARKERS):
        return False
    # 接頭辞そのもの（確認: / 処理中:）を除く
    return not key.endswith(_PREFIX_KEY_SUFFIX)


def _resolve_style_suffix(name: str) -> str:
    """ラベル名から体裁設定のフィールド接尾辞を解決する。"""
    # 接頭辞を持つラベルはその接頭辞で引く
    for prefix, suffix in _PREFIX_STYLES:
        if name.startswith(prefix):
            return suffix
    # 接頭辞を持たない単独ラベルは名前の完全一致で引く
    if name in _EXACT_STYLES:
        return _EXACT_STYLES[name]
    # どれにも当てはまらないラベルは体裁定数の追加を促してエラーにする
    raise ValueError(f"体裁を解決できないラベル名です: {name}")


def classify_labels(repo: str, specs: list[LabelSpec], existing: list[LabelSpec]) -> SyncResult:
    """あるべき仕様と現状を突き合わせて 作成 / 更新 / 変更なし に分ける。"""
    # existing を名前をキーにした辞書に変換する
    current = {spec.name: spec for spec in existing}
    created: list[LabelSpec] = []
    updated: list[LabelSpec] = []
    unchanged: list[LabelSpec] = []
    # specs を 1 件ずつ見て振り分ける
    for spec in specs:
        found = current.get(spec.name)
        if found is None:
            # 名前が辞書にない: 未作成なので作成対象
            created.append(spec)
        elif found == spec:
            # 色と説明が一致: 反映不要
            unchanged.append(spec)
        else:
            # 色または説明が異なる: 更新後の値で更新対象にする
            updated.append(spec)
    # 3 つのリストを持つ SyncResult を返す
    return SyncResult(repo=repo, created=created, updated=updated, unchanged=unchanged)


def sync_labels(
    repo: str,
    specs: list[LabelSpec],
    *,
    list_labels: ListLabelsFn,
    create_label: WriteLabelFn,
    update_label: WriteLabelFn,
    dry_run: bool = False,
) -> SyncResult:
    """1 リポジトリ分のラベルを GitHub に反映する。"""
    # 一覧取得で GitHub 上の既存ラベルを取得する
    existing = list_labels(repo)
    # 分類で 3 分類に振り分ける
    result = classify_labels(repo, specs, existing)
    # 空実行では何も書き込まずに分類結果を返す
    if dry_run:
        return result
    # 作成対象を 1 件ずつ作成する
    for spec in result.created:
        create_label(repo, spec)
        logger.info("ラベルを作成しました: repo=%s name=%s", repo, spec.name)
    # 更新対象を 1 件ずつ更新する
    for spec in result.updated:
        update_label(repo, spec)
        logger.info("ラベルの体裁を更新しました: repo=%s name=%s", repo, spec.name)
    # 分類結果を返す
    return result

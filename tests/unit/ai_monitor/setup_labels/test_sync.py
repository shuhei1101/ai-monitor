"""`src/ai_monitor/setup_labels/sync.py` の単体テスト。"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from ai_monitor.setup_labels.sync import (
    LabelSpec,
    LabelStyleSettings,
    build_label_specs,
    classify_labels,
    sync_labels,
)

REPO = "shuhei1101/ai-monitor"


@pytest.fixture
def tmp_constants(tmp_path):
    """検証用のキーだけを書いた一時 constants.env を作る factory。"""

    def _create(text: str) -> Path:
        path = tmp_path / "constants.env"
        path.write_text(text, encoding="utf-8")
        return path

    return _create


@pytest.fixture
def label_fns():
    """呼び出し引数を記録するスパイの GitHub 操作 3 関数を返す。"""
    state = NS(existing=[], created=[], updated=[])

    def _list_labels(repo: str) -> list[LabelSpec]:
        state.listed = repo
        return list(state.existing)

    def _create_label(repo: str, spec: LabelSpec) -> None:
        state.created.append((repo, spec))

    def _update_label(repo: str, spec: LabelSpec) -> None:
        state.updated.append((repo, spec))

    state.list_labels = _list_labels
    state.create_label = _create_label
    state.update_label = _update_label
    return state


def _spec(name: str, color: str = "0e8a16", description: str = "説明") -> LabelSpec:
    return LabelSpec(name=name, color=color, description=description)


# ---- ラベル仕様組み立て ----


def test_build_label_specs(tmp_constants):
    """全接頭辞と単独ラベルの色と説明が引けることを確認する（正常系）。"""
    # 準備
    path = tmp_constants(
        "# コメント行\n"
        '\nAI_MONITOR_LABEL_IN_DISCUSSION="議論中"\n'
        'AI_MONITOR_LABEL_REVERSE_ENGINEERING="リバースエンジニアリング"\n'
        'AI_MONITOR_LABEL_AI_DEFECT_REPORT="AI不具合報告"\n'
        'AI_MONITOR_LABEL_LAYER_EPIC="layer:epic"\n'
        'AI_MONITOR_LABEL_TYPE_FEAT="type:feat"\n'
        'AI_MONITOR_LABEL_PRIORITY_URGENT="優先度:急ぎ"\n'
        'AI_MONITOR_LABEL_CONFIRM_ARCHITECT="確認:architect"\n'
        'AI_MONITOR_LABEL_PROCESSING_ARCHITECT="処理中:architect"\n'
    )
    styles = LabelStyleSettings()
    # 実行
    specs = build_label_specs(path, styles=styles)
    # 検証
    by_name = {spec.name: spec for spec in specs}
    assert set(by_name) == {
        "議論中",
        "リバースエンジニアリング",
        "AI不具合報告",
        "layer:epic",
        "type:feat",
        "優先度:急ぎ",
        "確認:architect",
        "処理中:architect",
    }
    # 接頭辞ごとに対応する色と説明が入る
    assert (by_name["確認:architect"].color, by_name["確認:architect"].description) == (
        styles.color_confirm,
        styles.desc_confirm,
    )
    assert by_name["処理中:architect"].color == styles.color_processing
    assert by_name["layer:epic"].color == styles.color_layer
    assert by_name["type:feat"].color == styles.color_type
    assert by_name["優先度:急ぎ"].color == styles.color_priority
    assert by_name["議論中"].color == styles.color_in_discussion
    assert by_name["リバースエンジニアリング"].color == styles.color_reverse_engineering
    assert by_name["AI不具合報告"].color == styles.color_ai_defect_report
    # 名前の昇順で返る
    assert [spec.name for spec in specs] == sorted(by_name)


def test_build_label_specs_when_excluded_keys(tmp_constants):
    """ラベル名にならないキーの除外を確認する（正常系）。"""
    # 準備
    path = tmp_constants(
        'AI_MONITOR_LABEL_CONFIRM_ARCHITECT="確認:architect"\n'
        'AI_MONITOR_LABEL_CONFIRM_PREFIX="確認:"\n'
        'AI_MONITOR_LABEL_PROCESSING_PREFIX="処理中:"\n'
        'AI_MONITOR_LABEL_COLOR_CONFIRM="0e8a16"\n'
        'AI_MONITOR_LABEL_DESC_CONFIRM="担当エージェントの作業待ち"\n'
        'AI_MONITOR_TEMPLATE_SCENARIO="テンプレート/シナリオ.md"\n'
    )
    # 実行
    specs = build_label_specs(path, styles=LabelStyleSettings())
    # 検証
    assert [spec.name for spec in specs] == ["確認:architect"]


def test_build_label_specs_when_unknown_prefix(tmp_constants):
    """体裁を解決できないラベル名のエラーを確認する（異常系）。"""
    # 準備
    path = tmp_constants('AI_MONITOR_LABEL_UNKNOWN="未知:foo"\n')
    # 実行・検証
    with pytest.raises(ValueError, match="未知:foo"):
        build_label_specs(path, styles=LabelStyleSettings())


# ---- ラベル分類 ----


def test_classify_labels():
    """3 分類すべてへの振り分けを確認する（正常系）。"""
    # 準備
    specs = [_spec("確認:architect"), _spec("議論中", color="d93f0b"), _spec("layer:epic")]
    existing = [_spec("議論中", color="ffffff"), _spec("layer:epic")]
    # 実行
    result = classify_labels(REPO, specs, existing)
    # 検証
    assert result.repo == REPO
    assert [s.name for s in result.created] == ["確認:architect"]
    assert [s.name for s in result.updated] == ["議論中"]
    assert [s.name for s in result.unchanged] == ["layer:epic"]
    # 更新対象は更新後の値を持つ
    assert result.updated[0].color == "d93f0b"


def test_classify_labels_when_description_differs():
    """色が一致し説明だけ異なる場合の更新判定を確認する（正常系）。"""
    # 準備
    specs = [_spec("layer:epic", description="Issue のレイヤー")]
    existing = [_spec("layer:epic", description="旧説明")]
    # 実行
    result = classify_labels(REPO, specs, existing)
    # 検証
    assert [s.name for s in result.updated] == ["layer:epic"]
    assert result.unchanged == []


def test_classify_labels_when_extra_existing():
    """仕様にない既存ラベルが分類に現れないことを確認する（正常系）。"""
    # 準備
    specs = [_spec("layer:epic")]
    existing = [_spec("layer:epic"), _spec("bug", color="d73a4a", description="")]
    # 実行
    result = classify_labels(REPO, specs, existing)
    # 検証
    names = [s.name for s in result.created + result.updated + result.unchanged]
    assert "bug" not in names


# ---- ラベル同期 ----


def test_sync_labels(label_fns):
    """作成と更新の実行を確認する（正常系）。"""
    # 準備
    label_fns.existing.append(_spec("議論中", color="ffffff"))
    specs = [_spec("確認:architect"), _spec("議論中", color="d93f0b")]
    # 実行
    result = sync_labels(
        REPO,
        specs,
        list_labels=label_fns.list_labels,
        create_label=label_fns.create_label,
        update_label=label_fns.update_label,
    )
    # 検証
    assert [(repo, spec.name) for repo, spec in label_fns.created] == [(REPO, "確認:architect")]
    assert [(repo, spec.name) for repo, spec in label_fns.updated] == [(REPO, "議論中")]
    assert [s.name for s in result.created] == ["確認:architect"]
    assert [s.name for s in result.updated] == ["議論中"]
    assert result.unchanged == []


def test_sync_labels_when_dry_run(label_fns):
    """空実行での書き込み抑止を確認する（正常系）。"""
    # 準備
    label_fns.existing.append(_spec("議論中", color="ffffff"))
    specs = [_spec("確認:architect"), _spec("議論中", color="d93f0b")]
    kwargs = dict(
        list_labels=label_fns.list_labels,
        create_label=label_fns.create_label,
        update_label=label_fns.update_label,
    )
    # 実行
    dry = sync_labels(REPO, specs, dry_run=True, **kwargs)
    wet = sync_labels(REPO, specs, **kwargs)
    # 検証
    assert len(label_fns.created) == 1 and len(label_fns.updated) == 1
    assert dry == wet


def test_sync_labels_when_all_unchanged(label_fns):
    """差分なしのときの冪等性を確認する（正常系）。"""
    # 準備
    specs = [_spec("layer:epic"), _spec("確認:architect")]
    label_fns.existing.extend(specs)
    # 実行
    result = sync_labels(
        REPO,
        specs,
        list_labels=label_fns.list_labels,
        create_label=label_fns.create_label,
        update_label=label_fns.update_label,
    )
    # 検証
    assert label_fns.created == [] and label_fns.updated == []
    assert [s.name for s in result.unchanged] == ["layer:epic", "確認:architect"]

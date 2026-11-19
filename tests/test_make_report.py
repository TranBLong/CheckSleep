"""Unit tests cho scripts/make_report (không cần video/model)."""

import json
from pathlib import Path

import pytest

from scripts.make_report import (
    build_comparison_table,
    build_report,
    load_metrics_dir,
    pick_method,
)


def _write_result_dir(
    root: Path,
    methods: list[dict],
    extra: dict | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    payload = {"methods": methods}
    if extra:
        payload.update(extra)
    (root / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (root / "metrics.csv").write_text("method\nbaseline\n", encoding="utf-8")
    return root


def test_load_metrics_dir_requires_json_and_csv(tmp_path):
    only_json = tmp_path / "a"
    only_json.mkdir()
    (only_json / "metrics.json").write_text(
        json.dumps({"methods": [{"name": "x"}]}), encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError, match="metrics.csv"):
        load_metrics_dir(only_json)

    empty = tmp_path / "b"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="metrics.json"):
        load_metrics_dir(empty)


def test_pick_method_requires_keys_and_name():
    payload = {
        "methods": [
            {
                "name": "baseline_EAR",
                "precision_closed": 0.5,
                "recall_closed": 0.5,
                "f1_closed": 0.5,
                "accuracy": 0.5,
                "roc_auc": None,
                "fps": 30.0,
            }
        ]
    }
    row = pick_method(payload)
    assert row["name"] == "baseline_EAR"

    with pytest.raises(ValueError, match="CNN_eye"):
        pick_method(payload, preferred_name="CNN_eye")

    bad = {"methods": [{"name": "x", "fps": 1.0}]}
    with pytest.raises(ValueError, match="thiếu khóa"):
        pick_method(bad)


def test_build_comparison_table_and_report(tmp_path):
    baseline_method = {
        "name": "baseline_EAR",
        "precision_closed": 0.5,
        "recall_closed": 0.4,
        "f1_closed": 0.4444,
        "accuracy": 0.6,
        "roc_auc": None,
        "fps": 28.5,
    }
    cnn_method = {
        "name": "CNN_eye",
        "precision_closed": 0.9,
        "recall_closed": 0.8,
        "f1_closed": 0.8471,
        "accuracy": 0.85,
        "roc_auc": 0.92,
        "fps": 15.0,
    }
    baseline_dir = _write_result_dir(
        tmp_path / "eye_baseline",
        [baseline_method],
        extra={"metadata": {"video": "demo.mp4", "labels": "labels.csv"}},
    )
    cnn_dir = _write_result_dir(tmp_path / "eye_cnn", [cnn_method])

    baseline_payload = load_metrics_dir(baseline_dir)
    cnn_payload = load_metrics_dir(cnn_dir)
    table = build_comparison_table(
        [pick_method(baseline_payload), pick_method(cnn_payload)]
    )
    assert "baseline_EAR" in table
    assert "CNN_eye" in table
    assert "N/A" in table
    assert "0.9200" in table

    report = build_report(
        baseline_payload, cnn_payload, baseline_dir, cnn_dir
    )
    assert "# Kết quả đánh giá" in report
    assert "demo.mp4" in report
    assert "không có metadata" in report or "eye_cnn" in report
    assert "## Hạn chế" in report

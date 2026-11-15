"""Unit tests for labeled-video evaluation helpers (no video/model required)."""

import pytest

from scripts.evaluate import (
    LabelInterval,
    MethodMetrics,
    format_comparison_table,
    hard_binary_metrics,
    label_at_time,
    load_label_intervals,
    metrics_from_scores,
)


def test_load_label_intervals_and_lookup(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text(
        "start_seconds,end_seconds,label\n"
        "0.0,1.5,open\n1.5,3.0,closed\n4.0,5.0,open\n",
        encoding="utf-8",
    )

    intervals = load_label_intervals(path)

    assert label_at_time(0.2, intervals) is False
    assert label_at_time(1.5, intervals) is True
    assert label_at_time(2.9, intervals) is True
    assert label_at_time(3.5, intervals) is None


def test_load_label_intervals_rejects_invalid_label(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "start_seconds,end_seconds,label\n0,1,yawning\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="closed"):
        load_label_intervals(path)


def test_load_label_intervals_rejects_empty_and_overlapping_spans(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("start_seconds,end_seconds,label\n", encoding="utf-8")
    with pytest.raises(ValueError, match="không có đoạn"):
        load_label_intervals(empty)

    overlap = tmp_path / "overlap.csv"
    overlap.write_text(
        "start_seconds,end_seconds,label\n0,2,open\n1,3,closed\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="chồng lấn"):
        load_label_intervals(overlap)


def test_hard_binary_metrics_closed_class():
    metrics = hard_binary_metrics([1, 1, 0, 0], [1, 0, 1, 0])
    assert metrics["confusion_matrix"] == [[1, 1], [1, 1]]
    assert metrics["precision_closed"] == pytest.approx(0.5)
    assert metrics["recall_closed"] == pytest.approx(0.5)
    assert metrics["f1_closed"] == pytest.approx(0.5)
    assert metrics["accuracy"] == pytest.approx(0.5)


def test_metrics_from_scores_uses_threshold_and_roc():
    metrics = metrics_from_scores([0, 0, 1, 1], [0.1, 0.4, 0.6, 0.9], 0.5)
    assert metrics["precision_closed"] == pytest.approx(1.0)
    assert metrics["recall_closed"] == pytest.approx(1.0)
    assert metrics["roc_auc"] == pytest.approx(1.0)


def test_metrics_from_scores_requires_both_classes():
    with pytest.raises(ValueError, match="open"):
        metrics_from_scores([1, 1], [0.8, 0.9], 0.5)


def test_format_comparison_table_lists_methods_and_missing_auc():
    rows = [
        MethodMetrics("baseline_EAR", 0.5, 0.5, 0.5, 0.5, [[1, 1], [1, 1]], None, 30, 100),
        MethodMetrics("CNN_eye", 0.9, 0.8, 0.847, 0.85, [[40, 5], [10, 45]], 0.92, 18, 100),
    ]
    table = format_comparison_table(rows)
    assert "baseline_EAR" in table
    assert "CNN_eye" in table
    assert "N/A" in table


def test_label_lookup_uses_half_open_interval():
    intervals = [LabelInterval(2.0, 3.0, True)]
    assert label_at_time(2.0, intervals) is True
    assert label_at_time(3.0, intervals) is None

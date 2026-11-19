"""Kiểm thử logic thuần sequence_features."""

import pytest

from core.sequence_features import (
    assign_window_label,
    load_label_intervals,
    normalize_sample,
    sliding_windows,
)


def test_normalize_marks_missing_values_and_uses_session_baseline():
    features = normalize_sample(
        {
            "ear": None,
            "mar": 0.5,
            "pitch": 5.0,
            "perclos": None,
            "diem_met_moi": 20.0,
        },
        {"ear0": 0.3, "mar0": 0.4, "pitch0": 10.0},
    )

    assert features["ear_norm"] == 0.0
    assert features["ear_missing"] == 1.0
    assert features["mar_norm"] == pytest.approx(0.5 / 0.4)
    assert features["mar_missing"] == 0.0
    assert features["pitch_delta"] == pytest.approx(-5.0)
    assert features["perclos_missing"] == 1.0
    assert features["diem_met_moi"] == 20.0


def test_normalize_does_not_infer_alert_from_missing_face_metrics():
    features = normalize_sample(
        {"ear": None, "mar": None, "pitch": None},
        {"ear0": 0.3, "mar0": 0.4, "pitch0": 0.0},
    )

    assert features["ear_missing"] == 1.0
    assert features["mar_missing"] == 1.0
    assert features["pitch_missing"] == 1.0


def test_sliding_windows_obeys_window_and_stride():
    feature = {
        "ear_norm": 1.0,
        "mar_norm": 1.0,
        "pitch_delta": 0.0,
        "perclos": 0.0,
        "diem_met_moi": 0.0,
        "ear_missing": 0.0,
        "mar_missing": 0.0,
        "pitch_missing": 0.0,
        "perclos_missing": 0.0,
        "diem_met_moi_missing": 0.0,
    }

    windows = sliding_windows(
        [feature] * 40,
        list(range(40)),
        window_seconds=10,
        stride_seconds=5,
        sample_hz=1.0,
        max_missing_ratio=1.0,
    )

    assert len(windows) == 7
    assert windows[0][0:2] == (0, 10)


def test_sliding_windows_drops_windows_with_too_much_missing_data():
    feature = {
        "ear_missing": 1.0,
        "mar_missing": 1.0,
        "pitch_missing": 1.0,
    }

    assert sliding_windows(
        [feature] * 30,
        list(range(30)),
        window_seconds=30,
        stride_seconds=5,
        sample_hz=1.0,
        max_missing_ratio=0.2,
    ) == []


def test_label_intervals_reject_overlap_and_nonfinite_times():
    with pytest.raises(ValueError, match="chồng lấn"):
        load_label_intervals(
            [
                {"start_seconds": 0, "end_seconds": 2, "label": "tinh_tao"},
                {"start_seconds": 1, "end_seconds": 3, "label": "buon_ngu"},
            ]
        )
    with pytest.raises(ValueError, match="không hợp lệ"):
        load_label_intervals(
            [{"start_seconds": "nan", "end_seconds": 2, "label": "tinh_tao"}]
        )


def test_majority_label_and_tie_rejection():
    intervals = load_label_intervals(
        [
            {"start_seconds": 0, "end_seconds": 10, "label": "tinh_tao"},
            {"start_seconds": 10, "end_seconds": 20, "label": "buon_ngu"},
        ]
    )
    timestamps = list(range(20))

    assert assign_window_label(timestamps, 0, 10, intervals) == "tinh_tao"
    assert (
        assign_window_label(
            timestamps, 5, 15, intervals, majority_min_ratio=0.5
        )
        is None
    )

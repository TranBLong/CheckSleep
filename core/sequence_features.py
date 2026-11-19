"""Đặc trưng chuỗi thời gian thuần: chuẩn hóa baseline, cửa sổ, gán nhãn."""

from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

from config import (
    SEQ_FEATURES,
    SEQ_LABELS,
    SEQ_MAJORITY_MIN_RATIO,
    SEQ_MAX_MISSING_RATIO,
    SEQ_SAMPLE_HZ,
    SEQ_STRIDE_SECONDS,
    SEQ_WINDOW_SECONDS,
)

LabelInterval = tuple[float, float, str]


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)
    except (TypeError, ValueError):
        return False


def normalize_sample(
    sample: Mapping[str, Any],
    baseline: Mapping[str, float | None],
) -> dict[str, float]:
    """Chuẩn hóa một mẫu theo baseline phiên; thiếu dữ liệu luôn có cờ riêng."""
    ear0 = baseline.get("ear0")
    mar0 = baseline.get("mar0")
    pitch0 = baseline.get("pitch0")
    ear = sample.get("ear")
    mar = sample.get("mar")
    pitch = sample.get("pitch")
    perclos = sample.get("perclos")
    fatigue_score = sample.get("diem_met_moi")

    ear_missing = (
        _is_missing(ear)
        or _is_missing(ear0)
        or float(ear0) == 0.0
    )
    mar_missing = (
        _is_missing(mar)
        or _is_missing(mar0)
        or float(mar0) == 0.0
    )
    pitch_missing = _is_missing(pitch) or _is_missing(pitch0)
    perclos_missing = _is_missing(perclos)
    fatigue_missing = _is_missing(fatigue_score)

    ear_norm = 0.0 if ear_missing else float(ear) / float(ear0)
    mar_norm = 0.0 if mar_missing else float(mar) / float(mar0)
    pitch_delta = 0.0 if pitch_missing else float(pitch) - float(pitch0)

    values = {
        "ear_norm": ear_norm,
        "mar_norm": mar_norm,
        "pitch_delta": pitch_delta,
        "perclos": 0.0 if perclos_missing else float(perclos),
        "diem_met_moi": 0.0 if fatigue_missing else float(fatigue_score),
        "ear_missing": float(ear_missing),
        "mar_missing": float(mar_missing),
        "pitch_missing": float(pitch_missing),
        "perclos_missing": float(perclos_missing),
        "diem_met_moi_missing": float(fatigue_missing),
    }
    if not all(isfinite(value) for value in values.values()):
        raise ValueError("Đặc trưng đầu vào phải là số hữu hạn.")
    return values


def normalize_series(
    samples: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, float | None],
) -> list[dict[str, float]]:
    """Chuẩn hóa cả chuỗi mẫu theo cùng baseline phiên."""
    return [normalize_sample(sample, baseline) for sample in samples]


def _sample_missing_ratio(feat: Mapping[str, float]) -> float:
    flags = (
        feat.get("ear_missing", 0.0),
        feat.get("mar_missing", 0.0),
        feat.get("pitch_missing", 0.0),
    )
    return sum(flags) / len(flags)


def sliding_windows(
    features: Sequence[Mapping[str, float]],
    timestamps: Sequence[float],
    *,
    window_seconds: float = SEQ_WINDOW_SECONDS,
    stride_seconds: float = SEQ_STRIDE_SECONDS,
    sample_hz: float = SEQ_SAMPLE_HZ,
    max_missing_ratio: float = SEQ_MAX_MISSING_RATIO,
) -> list[tuple[int, int, list[dict[str, float]]]]:
    """Cắt cửa sổ trượt và bỏ cửa sổ có tỷ lệ EAR/MAR/pitch thiếu quá cao."""
    if len(features) != len(timestamps):
        raise ValueError("features và timestamps phải cùng độ dài.")
    if not all(
        isfinite(value) and value > 0
        for value in (window_seconds, stride_seconds, sample_hz)
    ):
        raise ValueError("window/stride/sample_hz phải là số hữu hạn > 0.")
    if not isfinite(max_missing_ratio) or not 0 <= max_missing_ratio <= 1:
        raise ValueError("max_missing_ratio phải nằm trong [0, 1].")
    if any(not isfinite(float(timestamp)) for timestamp in timestamps):
        raise ValueError("timestamps phải là số hữu hạn.")
    if any(
        float(current) < float(previous)
        for previous, current in zip(timestamps, timestamps[1:])
    ):
        raise ValueError("timestamps không được giảm.")
    if not features:
        return []

    window_len = max(1, int(round(window_seconds * sample_hz)))
    stride = max(1, int(round(stride_seconds * sample_hz)))
    out: list[tuple[int, int, list[dict[str, float]]]] = []
    start = 0
    while start + window_len <= len(features):
        end = start + window_len
        window = [dict(features[index]) for index in range(start, end)]
        missing_ratio = sum(_sample_missing_ratio(feat) for feat in window) / window_len
        if missing_ratio <= max_missing_ratio:
            out.append((start, end, window))
        start += stride
    return out


def load_label_intervals(
    rows: Iterable[Mapping[str, Any]],
    *,
    allowed_labels: Sequence[str] = SEQ_LABELS,
) -> list[LabelInterval]:
    """Đọc khoảng nhãn CSV start_seconds,end_seconds,label; không cho chồng lấn."""
    allowed = set(allowed_labels)
    intervals: list[LabelInterval] = []
    for row in rows:
        try:
            start = float(row["start_seconds"])
            end = float(row["end_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("start_seconds/end_seconds phải là số.") from exc
        label = str(row.get("label", "")).strip()
        if not isfinite(start) or not isfinite(end) or end <= start:
            raise ValueError(f"Khoảng nhãn không hợp lệ: {start}–{end}.")
        if label not in allowed:
            raise ValueError(f"Nhãn '{label}' không thuộc {tuple(allowed_labels)}.")
        intervals.append((start, end, label))

    intervals.sort(key=lambda interval: interval[0])
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            raise ValueError("Các khoảng nhãn bị chồng lấn.")
    return intervals


def label_at_time(t: float, intervals: Sequence[LabelInterval]) -> str | None:
    """Nhãn tại thời điểm t; None nếu ngoài mọi khoảng."""
    for start, end, label in intervals:
        if start <= t < end:
            return label
    return None


def assign_window_label(
    timestamps: Sequence[float],
    start_idx: int,
    end_idx: int,
    intervals: Sequence[LabelInterval],
    *,
    majority_min_ratio: float = SEQ_MAJORITY_MIN_RATIO,
) -> str | None:
    """Gán nhãn theo đa số mẫu có nhãn; vùng không nhãn hoặc hòa bị loại."""
    if not isfinite(majority_min_ratio) or not 0 <= majority_min_ratio <= 1:
        raise ValueError("majority_min_ratio phải nằm trong [0, 1].")
    if start_idx < 0 or end_idx > len(timestamps) or end_idx <= start_idx:
        return None

    counts: Counter[str] = Counter()
    for index in range(start_idx, end_idx):
        label = label_at_time(float(timestamps[index]), intervals)
        if label is not None:
            counts[label] += 1
    if not counts:
        return None
    label, count = counts.most_common(1)[0]
    if count / sum(counts.values()) < majority_min_ratio:
        return None
    if len(counts) > 1 and counts.most_common(2)[1][1] == count:
        return None
    return label


def feature_vector(
    feat: Mapping[str, float], names: Sequence[str] = SEQ_FEATURES
) -> list[float]:
    """Vector theo thứ tự SEQ_FEATURES."""
    return [float(feat[name]) for name in names]


def window_to_matrix(
    window: Sequence[Mapping[str, float]],
    names: Sequence[str] = SEQ_FEATURES,
) -> list[list[float]]:
    """Ma trận (T, F) cho một cửa sổ."""
    return [feature_vector(feat, names) for feat in window]

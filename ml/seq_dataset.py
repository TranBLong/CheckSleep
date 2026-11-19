"""Dataset cửa sổ chuỗi: tách train/validation/test theo phiên hoặc người."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from config import SEQ_LABELS, SEQ_SAMPLE_HZ
from core.sequence_features import (
    assign_window_label,
    load_label_intervals,
    normalize_series,
    sliding_windows,
    window_to_matrix,
)
from ml.colab_training import SampleRecord, split_by_subject


@dataclass(frozen=True)
class SeqWindowRecord:
    """One labeled window; subject_id groups all windows for split isolation."""

    matrix: list[list[float]]
    label: int
    subject_id: str
    session_id: str


def _label_to_index(name: str) -> int:
    try:
        return SEQ_LABELS.index(name)
    except ValueError as exc:
        raise ValueError(f"Nhãn '{name}' không thuộc SEQ_LABELS.") from exc


def _read_feature_csv(path: Path) -> tuple[list[dict], dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return [], {}

    def parse_float(row: dict, key: str) -> float | None:
        value = row.get(key)
        if value is None or value == "":
            return None
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"Cột {key} chứa giá trị không phải số: {value!r}.") from exc

    samples = [
        {
            "t_seconds": parse_float(row, "t_seconds"),
            "ear": parse_float(row, "ear"),
            "mar": parse_float(row, "mar"),
            "perclos": parse_float(row, "perclos"),
            "pitch": parse_float(row, "pitch"),
            "diem_met_moi": parse_float(row, "diem_met_moi"),
        }
        for row in rows
    ]
    baseline = {
        "ear0": parse_float(rows[0], "ear0"),
        "mar0": parse_float(rows[0], "mar0"),
        "pitch0": parse_float(rows[0], "pitch0"),
    }
    return samples, baseline


def build_windows_from_pair(
    feature_csv: Path,
    label_csv: Path,
    *,
    subject_id: str,
    session_id: str | None = None,
) -> list[SeqWindowRecord]:
    """Đọc cặp CSV đặc trưng/nhãn và tạo các cửa sổ có nhãn."""
    samples, baseline = _read_feature_csv(feature_csv)
    if not samples:
        return []
    timestamps = [
        float(index) / SEQ_SAMPLE_HZ
        if sample["t_seconds"] is None
        else float(sample["t_seconds"])
        for index, sample in enumerate(samples)
    ]
    with label_csv.open(newline="", encoding="utf-8-sig") as handle:
        intervals = load_label_intervals(list(csv.DictReader(handle)))

    features = normalize_series(samples, baseline)
    windows = sliding_windows(features, timestamps)
    output = []
    resolved_session_id = session_id or subject_id
    for start, end, window in windows:
        label = assign_window_label(timestamps, start, end, intervals)
        if label is not None:
            output.append(
                SeqWindowRecord(
                    matrix=window_to_matrix(window),
                    label=_label_to_index(label),
                    subject_id=str(subject_id),
                    session_id=str(resolved_session_id),
                )
            )
    return output


def load_dataset(
    pairs: Sequence[tuple[Path, Path, str]],
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    seed: int = 42,
) -> tuple[list[SeqWindowRecord], list[SeqWindowRecord], list[SeqWindowRecord]]:
    """Build windows and split by subject, never by overlapping window."""
    all_windows = []
    for feature_csv, label_csv, subject_id in pairs:
        all_windows.extend(
            build_windows_from_pair(
                feature_csv, label_csv, subject_id=subject_id
            )
        )
    if not all_windows:
        raise ValueError("Không dựng được cửa sổ nào từ các cặp CSV.")
    subjects = {window.subject_id for window in all_windows}
    if len(subjects) < 3:
        raise ValueError(
            f"Cần ít nhất 3 phiên/người để tách train/val/test, hiện có {len(subjects)}."
        )
    labels_present = {window.label for window in all_windows}
    if len(labels_present) < 2:
        raise ValueError(
            "Cần ít nhất 2 lớp nhãn; hiện chỉ có "
            f"{[SEQ_LABELS[index] for index in sorted(labels_present)]}."
        )

    records = [
        SampleRecord(
            path=str(index),
            label=window.label,
            subject_id=window.subject_id,
        )
        for index, window in enumerate(all_windows)
    ]
    train_records, validation_records, test_records = split_by_subject(
        records,
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
        seed=seed,
    )
    by_index = {str(index): window for index, window in enumerate(all_windows)}
    return tuple(
        [by_index[record.path] for record in split]
        for split in (train_records, validation_records, test_records)
    )


def stack_xy(
    windows: Sequence[SeqWindowRecord],
) -> tuple[np.ndarray, np.ndarray]:
    """Return X with shape (N,T,F) and y with shape (N,)."""
    if not windows:
        raise ValueError("Danh sách cửa sổ rỗng.")
    return (
        np.asarray([window.matrix for window in windows], dtype=np.float32),
        np.asarray([window.label for window in windows], dtype=np.int32),
    )

"""Dataset chuỗi: CSV giả, cửa sổ và tách theo subject."""

from pathlib import Path

import pytest

from ml.seq_dataset import build_windows_from_pair, load_dataset, stack_xy
from ml.train_sequence_model import parse_pairs


def _write_pair(
    directory: Path, name: str, label: str, sample_count: int = 40
) -> tuple[Path, Path]:
    features = directory / f"{name}_features.csv"
    labels = directory / f"{name}_labels.csv"
    with features.open("w", encoding="utf-8", newline="") as handle:
        handle.write(
            "session_id,ma_nd,thoi_gian,t_seconds,ear,mar,perclos,pitch,"
            "trang_thai,diem_met_moi,ear0,mar0,pitch0\n"
        )
        for index in range(sample_count):
            handle.write(
                f",,{index},{index},0.3,0.4,5.0,10.0,ALERT,10.0,0.3,0.4,10.0\n"
            )
    labels.write_text(
        "start_seconds,end_seconds,label\n"
        f"0,{sample_count},{label}\n",
        encoding="utf-8",
    )
    return features, labels


def test_build_windows_from_feature_and_label_csv(tmp_path):
    features, labels = _write_pair(tmp_path, "driver1", "tinh_tao")

    windows = build_windows_from_pair(
        features, labels, subject_id="driver1", session_id="session1"
    )

    assert windows
    assert windows[0].subject_id == "driver1"
    assert windows[0].session_id == "session1"
    assert windows[0].label == 0
    assert len(windows[0].matrix[0]) == 10


def test_load_dataset_splits_by_subject(tmp_path):
    pairs = []
    labels = ("tinh_tao", "met_moi", "buon_ngu", "ngu_gat", "tinh_tao", "met_moi")
    for index, label in enumerate(labels):
        features, label_file = _write_pair(tmp_path, f"subject{index}", label)
        pairs.append((features, label_file, f"person{index}"))

    train, validation, test = load_dataset(pairs, seed=0)
    subject_sets = [
        {window.subject_id for window in split}
        for split in (train, validation, test)
    ]

    assert all(subject_sets)
    assert subject_sets[0].isdisjoint(subject_sets[1])
    assert subject_sets[0].isdisjoint(subject_sets[2])
    assert subject_sets[1].isdisjoint(subject_sets[2])
    assert stack_xy(train)[0].shape[1:] == (30, 10)


def test_load_dataset_rejects_fewer_than_three_subjects(tmp_path):
    pairs = []
    for index in range(2):
        features, label_file = _write_pair(tmp_path, f"subject{index}", "tinh_tao")
        pairs.append((features, label_file, f"person{index}"))

    with pytest.raises(ValueError, match="3 phiên/người"):
        load_dataset(pairs)


def test_parse_pairs_accepts_windows_drive_paths():
    pairs = parse_pairs(
        [r"C:\seq\features.csv:C:\seq\labels.csv:personA"]
    )

    assert pairs == [
        (
            Path(r"C:\seq\features.csv"),
            Path(r"C:\seq\labels.csv"),
            "personA",
        )
    ]

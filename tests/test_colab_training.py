from pathlib import Path

import pytest

from ml.colab_training import (
    SampleRecord,
    compute_binary_metrics,
    scan_mrl_eye_dataset,
    split_by_subject,
)


def test_mrl_eye_parser_reads_standard_subject_and_state_fields(tmp_path):
    for filename in (
        "s0001_0_0_0_0_0_0_01.png",
        "s0002_0_0_1_0_0_0_01.png",
    ):
        (tmp_path / filename).write_bytes(b"placeholder")

    records = scan_mrl_eye_dataset(tmp_path)

    assert [(Path(record.path).name, record.subject_id, record.label) for record in records] == [
        ("s0001_0_0_0_0_0_0_01.png", "s0001", 1),
        ("s0002_0_0_1_0_0_0_01.png", "s0002", 0),
    ]


def test_subject_split_has_disjoint_subjects_and_all_three_sets():
    records = [
        SampleRecord(f"{subject}-{index}.png", label=index % 2, subject_id=subject)
        for subject in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")
        for index in range(10)
    ]

    train, validation, test = split_by_subject(records, seed=7)
    subject_sets = [
        {record.subject_id for record in split}
        for split in (train, validation, test)
    ]

    assert all(subject_sets)
    assert subject_sets[0].isdisjoint(subject_sets[1])
    assert subject_sets[0].isdisjoint(subject_sets[2])
    assert subject_sets[1].isdisjoint(subject_sets[2])
    assert len(train) + len(validation) + len(test) == len(records)


def test_subject_split_rejects_too_few_subjects():
    with pytest.raises(ValueError, match="At least 3 distinct subjects"):
        split_by_subject(
            [SampleRecord("a.png", 0, "same"), SampleRecord("b.png", 1, "same")]
        )


def test_binary_metrics_return_correct_confusion_and_roc_auc():
    result = compute_binary_metrics(
        actual=[0, 0, 1, 1],
        probabilities=[0.1, 0.4, 0.6, 0.9],
    )

    assert result["confusion_matrix"].tolist() == [[2, 0], [0, 2]]
    assert result["per_class"][1]["f1"] == 1.0
    assert result["roc_auc"] == pytest.approx(1.0)

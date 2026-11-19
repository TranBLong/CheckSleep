"""Unit tests cho điểm mệt mỏi (thuần, không camera/DB)."""

import pytest

from config import (
    FATIGUE_SCORE_ASLEEP_FLOOR,
    FATIGUE_SCORE_HEAD_NOD_REF_COUNT,
    FATIGUE_SCORE_LONG_BLINK_REF_COUNT,
    FATIGUE_SCORE_PERCLOS_REF_PERCENT,
    FATIGUE_SCORE_YAWN_REF_COUNT,
)
from core.fatigue_score import (
    BoDiemMetMoi,
    apply_asleep_floor,
    compute_raw_fatigue_score,
)
from core.types import TrangThai


def test_all_zero_yields_low_score():
    score = compute_raw_fatigue_score(0.0, 0, 0, 0)
    assert score == pytest.approx(0.0)


def test_all_at_reference_yields_100():
    score = compute_raw_fatigue_score(
        FATIGUE_SCORE_PERCLOS_REF_PERCENT,
        FATIGUE_SCORE_LONG_BLINK_REF_COUNT,
        FATIGUE_SCORE_YAWN_REF_COUNT,
        FATIGUE_SCORE_HEAD_NOD_REF_COUNT,
    )
    assert score == pytest.approx(100.0)


def test_missing_one_renormalizes_weights():
    score = compute_raw_fatigue_score(
        FATIGUE_SCORE_PERCLOS_REF_PERCENT,
        None,
        None,
        None,
    )
    assert score == pytest.approx(100.0)


def test_all_missing_returns_none():
    assert compute_raw_fatigue_score(None, None, None, None) is None


def test_asleep_floor():
    assert apply_asleep_floor(40.0, TrangThai.ASLEEP) == pytest.approx(
        FATIGUE_SCORE_ASLEEP_FLOOR
    )
    assert apply_asleep_floor(95.0, TrangThai.ASLEEP) == pytest.approx(95.0)
    assert apply_asleep_floor(40.0, TrangThai.ALERT) == pytest.approx(40.0)


def test_smoother_does_not_jump_to_raw_immediately():
    meter = BoDiemMetMoi(alpha=0.3)
    first = meter.update(0.0, 0, 0, 0, TrangThai.ALERT)
    assert first == pytest.approx(0.0)
    second = meter.update(
        FATIGUE_SCORE_PERCLOS_REF_PERCENT,
        FATIGUE_SCORE_LONG_BLINK_REF_COUNT,
        FATIGUE_SCORE_YAWN_REF_COUNT,
        FATIGUE_SCORE_HEAD_NOD_REF_COUNT,
        TrangThai.ALERT,
    )
    assert second == pytest.approx(30.0)
    assert second < 100.0


def test_smoother_all_missing_returns_none():
    meter = BoDiemMetMoi()
    meter.update(10.0, 1, 1, 1, TrangThai.ALERT)
    assert meter.update(None, None, None, None, TrangThai.UNKNOWN) is None

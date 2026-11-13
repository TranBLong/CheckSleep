import pytest

from config import (
    EYES_CLOSED_EAR_BASELINE_RATIO,
    HEAD_NOD_PITCH_DROP_DEGREES,
    YAWN_MAR_BASELINE_MULTIPLIER,
)
from core.calibration import BoHieuChinhCaNhan
from core.types import KetQuaPhatHien


def _result(ear=0.3, mar=1.0, pitch=0.0, has_face=True):
    return KetQuaPhatHien(
        has_face=has_face,
        ear=ear,
        mar=mar,
        pitch=pitch,
    )


def test_calibration_uses_medians_and_derives_personal_thresholds():
    calibration = BoHieuChinhCaNhan(duration_seconds=5, minimum_valid_frames=3)
    calibration.start(10.0)
    calibration.add_sample(_result(ear=0.2, mar=1.0, pitch=-50), 10.2)
    calibration.add_sample(_result(has_face=False), 11.0)
    calibration.add_sample(_result(ear=0.3, mar=2.0, pitch=0), 12.5)
    calibration.add_sample(_result(pitch=None), 13.5)
    calibration.add_sample(_result(ear=0.4, mar=100.0, pitch=50), 14.9)

    result = calibration.finish(15.0)

    assert result.ear0 == pytest.approx(0.3)
    assert result.mar0 == pytest.approx(2.0)
    assert result.pitch0 == pytest.approx(0.0)
    assert result.ear_closed_threshold == pytest.approx(
        result.ear0 * EYES_CLOSED_EAR_BASELINE_RATIO
    )
    assert result.mar_yawn_threshold == pytest.approx(
        result.mar0 * YAWN_MAR_BASELINE_MULTIPLIER
    )
    assert result.pitch_nod_threshold == pytest.approx(
        result.pitch0 - HEAD_NOD_PITCH_DROP_DEGREES
    )
    assert result.valid_frame_count == 3


def test_calibration_requires_duration_to_elapse():
    calibration = BoHieuChinhCaNhan()
    calibration.start(0.0)

    assert not calibration.is_complete(4.99)
    assert calibration.is_complete(5.0)
    with pytest.raises(RuntimeError, match="duration has not elapsed"):
        calibration.finish(4.99)


def test_calibration_reports_when_too_few_valid_frames_were_collected():
    calibration = BoHieuChinhCaNhan(duration_seconds=5, minimum_valid_frames=3)
    calibration.start(0.0)
    calibration.add_sample(_result(), 1.0)
    calibration.add_sample(_result(has_face=False), 2.0)
    calibration.add_sample(_result(), 3.0)

    with pytest.raises(ValueError, match="hiệu chỉnh lại"):
        calibration.finish(5.0)


def test_calibration_ignores_samples_after_the_window():
    calibration = BoHieuChinhCaNhan(duration_seconds=5, minimum_valid_frames=1)
    calibration.start(0.0)
    calibration.add_sample(_result(), 1.0)
    calibration.add_sample(_result(ear=0.9, mar=9.0, pitch=-90), 5.1)

    result = calibration.finish(5.1)

    assert result.ear0 == pytest.approx(0.3)
    assert result.mar0 == pytest.approx(1.0)
    assert result.pitch0 == pytest.approx(0.0)


def test_default_calibration_requires_thirty_valid_frames():
    calibration = BoHieuChinhCaNhan()
    calibration.start(0.0)
    for frame_index in range(29):
        calibration.add_sample(_result(), frame_index / 6.0)

    with pytest.raises(ValueError, match="29/30"):
        calibration.finish(5.0)

    calibration.add_sample(_result(), 5.0)
    result = calibration.finish(5.0)

    assert result.valid_frame_count == 30

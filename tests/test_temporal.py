import pytest

from config import (
    EYES_CLOSED_ASLEEP_DURATION_SECONDS,
    HEAD_BOW_ASLEEP_DURATION_SECONDS,
    HEAD_NOD_MIN_DURATION_SECONDS,
    LONG_BLINK_MAX_DURATION_MS,
    LONG_BLINK_MIN_DURATION_MS,
    PERCLOS_WINDOW_SECONDS,
    YAWN_MIN_DURATION_SECONDS,
)
from core.temporal import BoTheoDoiThoiGian


def _update(
    tracker,
    timestamp,
    *,
    eyes_closed=False,
    mouth_yawn=False,
    pitch=0.0,
    valid=True,
):
    return tracker.update(timestamp, eyes_closed, mouth_yawn, pitch, valid)


def test_normal_blink_is_not_counted_as_long_blink():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, eyes_closed=True)
    result = _update(tracker, 0.25, eyes_closed=False)

    assert result.long_blink_count_60s == 0


def test_long_blink_is_counted_once_when_eye_reopens():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    duration = (LONG_BLINK_MIN_DURATION_MS + LONG_BLINK_MAX_DURATION_MS) / 2 / 1000
    _update(tracker, 0.0, eyes_closed=True)
    result = _update(tracker, duration, eyes_closed=False)

    assert result.long_blink_count_60s == 1


@pytest.mark.parametrize(
    "duration",
    [LONG_BLINK_MIN_DURATION_MS / 1000, LONG_BLINK_MAX_DURATION_MS / 1000],
)
def test_long_blink_excludes_duration_boundaries(duration):
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, eyes_closed=True)
    result = _update(tracker, duration, eyes_closed=False)

    assert result.long_blink_count_60s == 0


def test_continuous_eye_closure_reaches_asleep_threshold():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, eyes_closed=True)
    result = _update(
        tracker,
        EYES_CLOSED_ASLEEP_DURATION_SECONDS,
        eyes_closed=False,
    )

    assert result.eyes_closed_duration_seconds == pytest.approx(
        EYES_CLOSED_ASLEEP_DURATION_SECONDS
    )
    assert result.eyes_closed_asleep


def test_yawn_requires_two_continuous_seconds_and_counts_once():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, mouth_yawn=True)
    _update(tracker, YAWN_MIN_DURATION_SECONDS - 0.01, mouth_yawn=True)
    interrupted = _update(
        tracker, YAWN_MIN_DURATION_SECONDS - 0.01, mouth_yawn=False
    )
    assert interrupted.yawn_count_5m == 0

    _update(tracker, 3.0, mouth_yawn=True)
    counted = _update(tracker, 3.0 + YAWN_MIN_DURATION_SECONDS, mouth_yawn=True)
    repeated = _update(tracker, 3.0 + YAWN_MIN_DURATION_SECONDS + 1, mouth_yawn=True)
    ended = _update(tracker, 7.0, mouth_yawn=False)
    assert counted.yawn_count_5m == 1
    assert repeated.yawn_count_5m == 1
    assert ended.yawn_count_5m == 1


def test_yawn_is_counted_when_a_long_interval_ends():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, mouth_yawn=True)
    result = _update(tracker, YAWN_MIN_DURATION_SECONDS, mouth_yawn=False)

    assert result.yawn_count_5m == 1


def test_nod_is_counted_after_sustained_pitch_drop_and_recovery():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, pitch=-15.0)
    _update(tracker, HEAD_NOD_MIN_DURATION_SECONDS, pitch=-20.0)
    recovered = _update(tracker, HEAD_NOD_MIN_DURATION_SECONDS + 0.1, pitch=0.0)

    assert recovered.nod_count_60s == 1


def test_prolonged_bow_is_reported_without_recovery():
    tracker = BoTheoDoiThoiGian(pitch0=10.0)
    _update(tracker, 0.0, pitch=-5.0)
    result = _update(
        tracker,
        HEAD_BOW_ASLEEP_DURATION_SECONDS,
        pitch=-5.0,
    )

    assert result.prolonged_bow
    assert result.nod_count_60s == 0


def test_perclos_uses_closed_eye_samples_in_rolling_window():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    for frame_index in range(PERCLOS_WINDOW_SECONDS + 1):
        _update(tracker, frame_index, eyes_closed=frame_index < 15)

    result = _update(
        tracker, PERCLOS_WINDOW_SECONDS + 1, eyes_closed=False
    )

    assert result.perclos_percent == pytest.approx(14 / 61 * 100)


def test_perclos_excludes_frames_where_eye_metric_is_occluded():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, eyes_closed=True)
    result = _update(tracker, 1.0, eyes_closed=None, mouth_yawn=False, pitch=0.0)

    assert result.perclos_percent == pytest.approx(100.0)
    assert result.partial_data
    assert result.has_valid_data


def test_partial_face_data_keeps_available_metrics_and_invalid_face_is_unknown():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    partial = _update(
        tracker,
        0.0,
        eyes_closed=None,
        mouth_yawn=True,
        pitch=None,
    )
    unknown = _update(
        tracker,
        1.0,
        eyes_closed=None,
        mouth_yawn=None,
        pitch=None,
        valid=False,
    )

    assert partial.has_valid_data
    assert partial.partial_data
    assert partial.perclos_percent is None
    assert unknown.has_valid_data is False
    assert unknown.partial_data is False
    assert unknown.eyes_closed_duration_seconds is None


def test_missing_metric_breaks_its_continuous_measurement_only():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, eyes_closed=True, mouth_yawn=True)
    partial = _update(
        tracker,
        1.0,
        eyes_closed=None,
        mouth_yawn=True,
        pitch=0.0,
    )
    yawn = _update(
        tracker,
        2.0,
        eyes_closed=False,
        mouth_yawn=True,
        pitch=0.0,
    )

    assert partial.eyes_closed_duration_seconds is None
    assert yawn.yawn_count_5m == 1
    assert yawn.long_blink_count_60s == 0


def test_invalid_whole_frame_breaks_continuous_closure():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 0.0, eyes_closed=True)
    _update(
        tracker,
        1.0,
        eyes_closed=True,
        mouth_yawn=True,
        pitch=0.0,
        valid=False,
    )
    result = _update(tracker, 2.0, eyes_closed=True)

    assert result.eyes_closed_duration_seconds == 0.0
    assert not result.eyes_closed_asleep


def test_tracker_rejects_timestamp_that_moves_backwards():
    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    _update(tracker, 2.0)

    with pytest.raises(ValueError, match="move backwards"):
        _update(tracker, 1.0)

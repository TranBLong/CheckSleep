import pytest

from config import (
    FACE_TRACKING_LOSS_UNKNOWN_SECONDS,
    QUALITY_LOSS_UNKNOWN_SECONDS,
)
from core.state_machine import MayTrangThai
from core.temporal import KetQuaTheoDoiThoiGian
from core.types import TrangThai


def _metrics(
    *,
    eyes_closed_asleep=False,
    long_blinks=0,
    perclos=0.0,
    yawns_5m=0,
    yawns_10m=0,
    nods=0,
    prolonged_bow=False,
    has_valid_data=True,
    partial_data=False,
):
    return KetQuaTheoDoiThoiGian(
        eyes_closed_duration_seconds=None,
        eyes_closed_asleep=eyes_closed_asleep,
        long_blink_count_60s=long_blinks,
        perclos_percent=perclos,
        yawn_count_5m=yawns_5m,
        yawn_count_10m=yawns_10m,
        nod_count_60s=nods,
        prolonged_bow=prolonged_bow,
        has_valid_data=has_valid_data,
        partial_data=partial_data,
    )


@pytest.mark.parametrize(
    "metrics, expected",
    [
        (_metrics(yawns_5m=2), TrangThai.FATIGUED),
        (_metrics(perclos=10.0), TrangThai.FATIGUED),
        (_metrics(long_blinks=1), TrangThai.FATIGUED),
        (_metrics(perclos=15.0), TrangThai.DROWSY),
        (_metrics(long_blinks=3), TrangThai.DROWSY),
        (_metrics(nods=2), TrangThai.DROWSY),
        (_metrics(yawns_10m=3, nods=1), TrangThai.DROWSY),
        (_metrics(yawns_10m=3), TrangThai.ALERT),
        (_metrics(), TrangThai.ALERT),
    ],
)
def test_classifies_spec_thresholds(metrics, expected):
    machine = MayTrangThai()

    assert machine.update(0.0, metrics, has_face=True, quality_ok=True) == expected


@pytest.mark.parametrize(
    "metrics",
    [_metrics(eyes_closed_asleep=True), _metrics(prolonged_bow=True)],
)
def test_asleep_escalates_immediately_from_any_state(metrics):
    machine = MayTrangThai()
    machine.update(
        0.0, _metrics(perclos=10.0), has_face=True, quality_ok=True
    )
    assert machine.state == TrangThai.FATIGUED

    result = machine.update(0.1, metrics, has_face=True, quality_ok=True)

    assert result == TrangThai.ASLEEP


def test_table_3_4_downgrades_one_step_each_thirty_normal_seconds():
    machine = MayTrangThai()
    machine.update(
        0.0,
        _metrics(eyes_closed_asleep=True),
        has_face=True,
        quality_ok=True,
    )
    normal = _metrics()

    assert machine.update(1.0, normal, has_face=True, quality_ok=True) == TrangThai.ASLEEP
    assert machine.update(31.0, normal, has_face=True, quality_ok=True) == TrangThai.DROWSY
    assert machine.update(60.9, normal, has_face=True, quality_ok=True) == TrangThai.DROWSY
    assert machine.update(61.0, normal, has_face=True, quality_ok=True) == TrangThai.FATIGUED
    assert machine.update(91.0, normal, has_face=True, quality_ok=True) == TrangThai.ALERT


def test_non_normal_indicator_does_not_block_deescalation():
    """Candidate FATIGUED khi đang ASLEEP vẫn cho phép hạ bậc sau 30 s."""
    machine = MayTrangThai()
    machine.update(
        0.0,
        _metrics(eyes_closed_asleep=True),
        has_face=True,
        quality_ok=True,
    )
    machine.update(1.0, _metrics(perclos=10.0), has_face=True, quality_ok=True)
    assert (
        machine.update(31.0, _metrics(perclos=10.0), has_face=True, quality_ok=True)
        == TrangThai.DROWSY
    )


def test_asleep_deescalates_step_by_step_when_candidate_stays_fatigued():
    """ASLEEP → DROWSY → FATIGUED khi candidate FATIGUED liên tục mỗi 30 s."""
    machine = MayTrangThai()
    machine.update(0.0, _metrics(eyes_closed_asleep=True), has_face=True, quality_ok=True)
    fatigued = _metrics(perclos=10.0)
    assert machine.update(1.0, fatigued, has_face=True, quality_ok=True) == TrangThai.ASLEEP
    assert machine.update(31.0, fatigued, has_face=True, quality_ok=True) == TrangThai.DROWSY
    assert machine.update(61.0, fatigued, has_face=True, quality_ok=True) == TrangThai.FATIGUED
    assert machine.update(91.0, fatigued, has_face=True, quality_ok=True) == TrangThai.FATIGUED


def test_low_quality_becomes_unknown_only_after_sustained_duration():
    machine = MayTrangThai()
    machine.update(0.0, _metrics(perclos=15.0), has_face=True, quality_ok=True)

    assert (
        machine.update(
            1.0,
            _metrics(perclos=15.0),
            has_face=True,
            quality_ok=False,
        )
        == TrangThai.DROWSY
    )
    assert (
        machine.update(
            1.0 + QUALITY_LOSS_UNKNOWN_SECONDS,
            _metrics(perclos=15.0),
            has_face=True,
            quality_ok=False,
        )
        == TrangThai.DROWSY
    )
    assert (
        machine.update(
            1.0 + QUALITY_LOSS_UNKNOWN_SECONDS + 0.01,
            _metrics(perclos=15.0),
            has_face=True,
            quality_ok=False,
        )
        == TrangThai.UNKNOWN
    )
    assert machine.update(
        2.0 + QUALITY_LOSS_UNKNOWN_SECONDS,
        _metrics(),
        has_face=True,
        quality_ok=True,
    ) == TrangThai.ALERT


def test_face_loss_becomes_unknown_only_after_configured_seconds():
    machine = MayTrangThai()
    machine.update(0.0, _metrics(), has_face=True, quality_ok=True)

    assert machine.update(1.0, None, has_face=False, quality_ok=True) == TrangThai.ALERT
    assert (
        machine.update(
            1.0 + FACE_TRACKING_LOSS_UNKNOWN_SECONDS,
            None,
            has_face=False,
            quality_ok=True,
        )
        == TrangThai.ALERT
    )
    assert (
        machine.update(
            1.01 + FACE_TRACKING_LOSS_UNKNOWN_SECONDS,
            None,
            has_face=False,
            quality_ok=True,
        )
        == TrangThai.UNKNOWN
    )


def test_initial_invalid_input_never_defaults_to_alert():
    machine = MayTrangThai()

    assert machine.update(0.0, None, has_face=True, quality_ok=True) == TrangThai.UNKNOWN
    assert machine.update(1.0, None, has_face=False, quality_ok=True) == TrangThai.UNKNOWN


def test_partial_valid_metrics_are_classified_from_available_signals():
    machine = MayTrangThai()
    partial_metrics = _metrics(perclos=10.0, partial_data=True)

    assert (
        machine.update(0.0, partial_metrics, has_face=True, quality_ok=True)
        == TrangThai.FATIGUED
    )


def test_state_machine_rejects_timestamp_that_moves_backwards():
    machine = MayTrangThai()
    machine.update(2.0, _metrics(), has_face=True, quality_ok=True)

    with pytest.raises(ValueError, match="move backwards"):
        machine.update(1.0, _metrics(), has_face=True, quality_ok=True)


def test_temporal_windows_reset_after_each_real_deescalation():
    """Combine the real temporal tracker and state machine for the downgrade path."""
    from config import STATE_DEESCALATION_NORMAL_DURATION_SECONDS
    from core.temporal import BoTheoDoiThoiGian

    tracker = BoTheoDoiThoiGian(pitch0=0.0)
    machine = MayTrangThai()
    severity = {
        TrangThai.UNKNOWN: -1,
        TrangThai.ALERT: 0,
        TrangThai.FATIGUED: 1,
        TrangThai.DROWSY: 2,
        TrangThai.ASLEEP: 3,
    }
    previous = TrangThai.UNKNOWN
    transitions = []
    timestamp = 0.0
    end = 4 * STATE_DEESCALATION_NORMAL_DURATION_SECONDS + 70.0

    while timestamp <= end:
        eyes_closed = timestamp < 2.1
        metrics = tracker.update(
            timestamp, eyes_closed, False, 0.0, valid=True
        )
        state = machine.update(
            timestamp, metrics, has_face=True, quality_ok=True
        )
        if severity[state] < severity[previous] and state != TrangThai.UNKNOWN:
            transitions.append(state)
            tracker.reset_windows()
            assert not tracker._eye_samples
            assert not tracker._long_blinks
            assert not tracker._nods
        previous = state
        timestamp += 0.1

    assert transitions == [
        TrangThai.DROWSY,
        TrangThai.FATIGUED,
        TrangThai.ALERT,
    ]
    assert state == TrangThai.ALERT

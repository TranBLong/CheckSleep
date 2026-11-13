import pytest

from core.alert import BoDieuKhienCanhBao
from core.types import TrangThai


@pytest.mark.parametrize(
    "state, level",
    [
        (TrangThai.FATIGUED, 1),
        (TrangThai.DROWSY, 2),
        (TrangThai.ASLEEP, 3),
    ],
)
def test_alert_maps_states_to_levels(state, level):
    alerts = BoDieuKhienCanhBao()

    result = alerts.evaluate(0.0, state)

    assert result.level == level
    assert result.should_emit
    assert result.sound_enabled


def test_same_level_is_not_repeated_within_ten_seconds():
    alerts = BoDieuKhienCanhBao()
    alerts.evaluate(0.0, TrangThai.DROWSY)

    assert not alerts.evaluate(9.99, TrangThai.DROWSY).should_emit
    assert alerts.evaluate(10.0, TrangThai.DROWSY).should_emit


def test_acknowledgement_temporarily_mutes_level_one_and_two():
    for state in (TrangThai.FATIGUED, TrangThai.DROWSY):
        alerts = BoDieuKhienCanhBao()
        alerts.evaluate(0.0, state)
        acknowledged = alerts.acknowledge(1.0, state)

        assert acknowledged.acknowledged
        assert not acknowledged.should_emit
        assert not acknowledged.sound_enabled
        still_muted = alerts.evaluate(10.99, state)
        resumed = alerts.evaluate(11.0, state)
        assert not still_muted.sound_enabled
        assert not still_muted.should_emit
        assert resumed.sound_enabled
        assert resumed.should_emit


def test_acknowledging_asleep_never_silences_level_three():
    alerts = BoDieuKhienCanhBao()
    alerts.evaluate(0.0, TrangThai.ASLEEP)

    acknowledged = alerts.acknowledge(1.0, TrangThai.ASLEEP)

    assert acknowledged.level == 3
    assert acknowledged.sound_enabled
    assert acknowledged.acknowledged
    assert not acknowledged.should_emit


def test_unknown_and_alert_have_no_alert_level():
    alerts = BoDieuKhienCanhBao()

    for state in (TrangThai.UNKNOWN, TrangThai.ALERT):
        result = alerts.evaluate(0.0, state)
        assert result.level is None
        assert not result.should_emit
        assert not result.sound_enabled


def test_alert_controller_rejects_timestamp_that_moves_backwards():
    alerts = BoDieuKhienCanhBao()
    alerts.evaluate(2.0, TrangThai.UNKNOWN)

    with pytest.raises(ValueError, match="move backwards"):
        alerts.evaluate(1.0, TrangThai.FATIGUED)

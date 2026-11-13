"""Drowsiness state transitions with immediate escalation and hysteresis."""

from math import isfinite

from config import (
    FACE_TRACKING_LOSS_UNKNOWN_SECONDS,
    HEAD_NOD_DROWSY_COUNT_MIN,
    LONG_BLINK_DROWSY_COUNT_MIN,
    LONG_BLINK_FATIGUED_COUNT_MIN,
    PERCLOS_DROWSY_THRESHOLD_PERCENT,
    PERCLOS_FATIGUED_THRESHOLD_PERCENT,
    STATE_DEESCALATION_NORMAL_DURATION_SECONDS,
    YAWN_DROWSY_COUNT_MIN,
    YAWN_DROWSY_REQUIRES_OTHER_SIGN,
    YAWN_FATIGUED_COUNT_MIN,
)
from core.temporal import KetQuaTheoDoiThoiGian
from core.types import TrangThai

_SEVERITY = {
    TrangThai.UNKNOWN: -1,
    TrangThai.ALERT: 0,
    TrangThai.FATIGUED: 1,
    TrangThai.DROWSY: 2,
    TrangThai.ASLEEP: 3,
}


class MayTrangThai:
    """Classify temporal metrics into the five driver alert states."""

    def __init__(self) -> None:
        self.state = TrangThai.UNKNOWN
        self._last_timestamp: float | None = None
        self._face_missing_since: float | None = None
        self._normal_since: float | None = None

    def reset(self) -> None:
        """Return to UNKNOWN and clear transition timers."""
        self.state = TrangThai.UNKNOWN
        self._last_timestamp = None
        self._face_missing_since = None
        self._normal_since = None

    def update(
        self,
        timestamp_seconds: float,
        metrics: KetQuaTheoDoiThoiGian | None,
        *,
        has_face: bool,
        quality_ok: bool,
    ) -> TrangThai:
        """Update state from one frame and its temporal summary."""
        if not isfinite(timestamp_seconds):
            raise ValueError("timestamp_seconds must be finite.")
        if self._last_timestamp is not None and timestamp_seconds < self._last_timestamp:
            raise ValueError("Timestamps must not move backwards.")
        if not isinstance(has_face, bool) or not isinstance(quality_ok, bool):
            raise ValueError("has_face and quality_ok must be bool values.")
        self._last_timestamp = timestamp_seconds

        if not quality_ok:
            self._face_missing_since = None
            self._normal_since = None
            self.state = TrangThai.UNKNOWN
            return self.state

        if not has_face:
            if self._face_missing_since is None:
                self._face_missing_since = timestamp_seconds
            self._normal_since = None
            if (
                timestamp_seconds - self._face_missing_since
                > FACE_TRACKING_LOSS_UNKNOWN_SECONDS
            ):
                self.state = TrangThai.UNKNOWN
            return self.state

        self._face_missing_since = None
        if metrics is None or not metrics.has_valid_data:
            self._normal_since = None
            self.state = TrangThai.UNKNOWN
            return self.state

        candidate = self._classify(metrics)
        if _SEVERITY[candidate] > _SEVERITY[self.state]:
            self.state = candidate
            self._normal_since = None
            return self.state

        if candidate == self.state:
            self._normal_since = None
            return self.state

        if candidate != TrangThai.ALERT:
            self._normal_since = None
            if self.state == TrangThai.UNKNOWN:
                self.state = candidate
            return self.state

        if self.state == TrangThai.UNKNOWN:
            self.state = TrangThai.ALERT
            self._normal_since = None
            return self.state

        if self._normal_since is None:
            self._normal_since = timestamp_seconds
        if (
            timestamp_seconds - self._normal_since
            >= STATE_DEESCALATION_NORMAL_DURATION_SECONDS
        ):
            self.state = self._one_step_lower(self.state)
            self._normal_since = timestamp_seconds
        return self.state

    @staticmethod
    def _classify(metrics: KetQuaTheoDoiThoiGian) -> TrangThai:
        if metrics.eyes_closed_asleep or metrics.prolonged_bow:
            return TrangThai.ASLEEP

        perclos = metrics.perclos_percent or 0.0
        long_blinks = metrics.long_blink_count_60s
        nods = metrics.nod_count_60s
        yawn_drowsy = metrics.yawn_count_10m >= YAWN_DROWSY_COUNT_MIN
        if YAWN_DROWSY_REQUIRES_OTHER_SIGN:
            yawn_drowsy = yawn_drowsy and (
                perclos >= PERCLOS_FATIGUED_THRESHOLD_PERCENT
                or long_blinks >= LONG_BLINK_FATIGUED_COUNT_MIN
                or nods > 0
            )
        if (
            perclos >= PERCLOS_DROWSY_THRESHOLD_PERCENT
            or long_blinks >= LONG_BLINK_DROWSY_COUNT_MIN
            or nods >= HEAD_NOD_DROWSY_COUNT_MIN
            or yawn_drowsy
        ):
            return TrangThai.DROWSY

        if (
            metrics.yawn_count_5m >= YAWN_FATIGUED_COUNT_MIN
            or perclos >= PERCLOS_FATIGUED_THRESHOLD_PERCENT
            or long_blinks >= LONG_BLINK_FATIGUED_COUNT_MIN
        ):
            return TrangThai.FATIGUED
        return TrangThai.ALERT

    @staticmethod
    def _one_step_lower(state: TrangThai) -> TrangThai:
        return {
            TrangThai.ASLEEP: TrangThai.DROWSY,
            TrangThai.DROWSY: TrangThai.FATIGUED,
            TrangThai.FATIGUED: TrangThai.ALERT,
            TrangThai.ALERT: TrangThai.ALERT,
            TrangThai.UNKNOWN: TrangThai.UNKNOWN,
        }[state]

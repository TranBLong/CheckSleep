"""Time-window tracking for drowsiness indicators."""

from collections import deque
from dataclasses import dataclass
from math import isfinite

from config import (
    EYES_CLOSED_ASLEEP_DURATION_SECONDS,
    HEAD_BOW_ASLEEP_DURATION_SECONDS,
    HEAD_NOD_COUNT_WINDOW_SECONDS,
    HEAD_NOD_MIN_DURATION_SECONDS,
    HEAD_NOD_PITCH_DROP_DEGREES,
    LONG_BLINK_COUNT_WINDOW_SECONDS,
    LONG_BLINK_MAX_DURATION_MS,
    LONG_BLINK_MIN_DURATION_MS,
    PERCLOS_WINDOW_SECONDS,
    YAWN_DROWSY_WINDOW_SECONDS,
    YAWN_FATIGUED_WINDOW_SECONDS,
    YAWN_MIN_DURATION_SECONDS,
)


@dataclass(frozen=True)
class KetQuaTheoDoiThoiGian:
    eyes_closed_duration_seconds: float | None
    eyes_closed_asleep: bool
    long_blink_count_60s: int
    perclos_percent: float | None
    yawn_count_5m: int
    yawn_count_10m: int
    nod_count_60s: int
    prolonged_bow: bool
    has_valid_data: bool
    partial_data: bool


class BoTheoDoiThoiGian:
    """Track timed indicators using caller-supplied timestamps."""

    def __init__(self, pitch0: float) -> None:
        if not isfinite(pitch0):
            raise ValueError("pitch0 must be finite.")
        self._pitch0 = pitch0
        self.reset()

    def reset(self) -> None:
        """Clear event history and all in-progress indicators."""
        self._last_timestamp: float | None = None
        self._eye_closed_since: float | None = None
        self._eye_samples: deque[tuple[float, bool]] = deque()
        self._long_blinks: deque[float] = deque()
        self._mouth_yawn_since: float | None = None
        self._yawn_counted_for_current_event = False
        self._yawns: deque[float] = deque()
        self._nod_since: float | None = None
        self._nods: deque[float] = deque()

    def update(
        self,
        timestamp_seconds: float,
        eyes_closed: bool | None,
        mouth_yawn: bool | None,
        pitch: float | None,
        valid: bool,
    ) -> KetQuaTheoDoiThoiGian:
        """Process one frame; ``None`` means that a specific metric is occluded."""
        if not isfinite(timestamp_seconds):
            raise ValueError("timestamp_seconds must be finite.")
        if self._last_timestamp is not None and timestamp_seconds < self._last_timestamp:
            raise ValueError("Timestamps must not move backwards.")
        if not isinstance(valid, bool):
            raise ValueError("valid must be a bool.")

        if valid:
            if eyes_closed is not None and not isinstance(eyes_closed, bool):
                raise ValueError("eyes_closed must be bool or None.")
            if mouth_yawn is not None and not isinstance(mouth_yawn, bool):
                raise ValueError("mouth_yawn must be bool or None.")
            if pitch is not None and not isfinite(pitch):
                raise ValueError("pitch must be finite or None.")

        self._last_timestamp = timestamp_seconds
        self._prune_events(timestamp_seconds)
        if not valid:
            self._reset_continuous_indicators()
            return self._result(
                timestamp_seconds,
                eyes_closed_duration=None,
                eyes_closed_asleep=False,
                perclos_percent=self._perclos_percent(),
                prolonged_bow=False,
                has_valid_data=False,
                partial_data=False,
            )

        closed_duration, eyes_closed_asleep = self._update_eyes(
            timestamp_seconds, eyes_closed
        )
        self._update_yawn(timestamp_seconds, mouth_yawn)
        prolonged_bow = self._update_nod(timestamp_seconds, pitch)

        has_valid_data = any(
            value is not None for value in (eyes_closed, mouth_yawn, pitch)
        )
        partial_data = has_valid_data and any(
            value is None for value in (eyes_closed, mouth_yawn, pitch)
        )
        return self._result(
            timestamp_seconds,
            eyes_closed_duration=closed_duration,
            eyes_closed_asleep=eyes_closed_asleep,
            perclos_percent=self._perclos_percent(),
            prolonged_bow=prolonged_bow,
            has_valid_data=has_valid_data,
            partial_data=partial_data,
        )

    def _update_eyes(
        self, timestamp: float, eyes_closed: bool | None
    ) -> tuple[float | None, bool]:
        if eyes_closed is None:
            self._eye_closed_since = None
            return None, False

        self._eye_samples.append((timestamp, eyes_closed))
        if eyes_closed:
            if self._eye_closed_since is None:
                self._eye_closed_since = timestamp
            duration = timestamp - self._eye_closed_since
            return duration, duration >= EYES_CLOSED_ASLEEP_DURATION_SECONDS

        if self._eye_closed_since is not None:
            duration = timestamp - self._eye_closed_since
            if (
                duration * 1000 > LONG_BLINK_MIN_DURATION_MS
                and duration * 1000 < LONG_BLINK_MAX_DURATION_MS
            ):
                self._long_blinks.append(timestamp)
            self._eye_closed_since = None
            return (
                duration,
                duration >= EYES_CLOSED_ASLEEP_DURATION_SECONDS,
            )
        self._eye_closed_since = None
        return 0.0, False

    def _update_yawn(self, timestamp: float, mouth_yawn: bool | None) -> None:
        """Count a continuous MAR-above-threshold interval once it reaches 2 s."""
        if mouth_yawn is None:
            self._mouth_yawn_since = None
            self._yawn_counted_for_current_event = False
            return
        if mouth_yawn is False:
            self._record_yawn_if_qualified(timestamp)
            self._mouth_yawn_since = None
            self._yawn_counted_for_current_event = False
            return
        if self._mouth_yawn_since is None:
            self._mouth_yawn_since = timestamp
            self._yawn_counted_for_current_event = False
            return
        self._record_yawn_if_qualified(timestamp)

    def _record_yawn_if_qualified(self, timestamp: float) -> None:
        if (
            self._mouth_yawn_since is not None
            and timestamp - self._mouth_yawn_since >= YAWN_MIN_DURATION_SECONDS
            and not self._yawn_counted_for_current_event
        ):
            self._yawns.append(timestamp)
            self._yawn_counted_for_current_event = True

    def _update_nod(self, timestamp: float, pitch: float | None) -> bool:
        """Count a pitch drop on recovery, or report a sustained bow in progress."""
        if pitch is None:
            self._nod_since = None
            return False
        nod_threshold = self._pitch0 - HEAD_NOD_PITCH_DROP_DEGREES
        if pitch <= nod_threshold:
            if self._nod_since is None:
                self._nod_since = timestamp
            return (
                timestamp - self._nod_since
                >= HEAD_BOW_ASLEEP_DURATION_SECONDS
            )

        if self._nod_since is not None:
            duration = timestamp - self._nod_since
            if duration >= HEAD_NOD_MIN_DURATION_SECONDS:
                self._nods.append(timestamp)
        self._nod_since = None
        return False

    def _reset_continuous_indicators(self) -> None:
        self._eye_closed_since = None
        self._mouth_yawn_since = None
        self._yawn_counted_for_current_event = False
        self._nod_since = None

    def _prune_events(self, timestamp: float) -> None:
        self._prune(self._long_blinks, timestamp, LONG_BLINK_COUNT_WINDOW_SECONDS)
        self._prune(self._yawns, timestamp, YAWN_DROWSY_WINDOW_SECONDS)
        self._prune(self._nods, timestamp, HEAD_NOD_COUNT_WINDOW_SECONDS)
        cutoff = timestamp - PERCLOS_WINDOW_SECONDS
        while self._eye_samples and self._eye_samples[0][0] < cutoff:
            self._eye_samples.popleft()

    @staticmethod
    def _prune(events: deque[float], timestamp: float, window_seconds: float) -> None:
        cutoff = timestamp - window_seconds
        while events and events[0] < cutoff:
            events.popleft()

    def _perclos_percent(self) -> float | None:
        if not self._eye_samples:
            return None
        closed_frames = sum(is_closed for _, is_closed in self._eye_samples)
        return closed_frames / len(self._eye_samples) * 100.0

    def _result(
        self,
        timestamp: float,
        *,
        eyes_closed_duration: float | None,
        eyes_closed_asleep: bool,
        perclos_percent: float | None,
        prolonged_bow: bool,
        has_valid_data: bool,
        partial_data: bool,
    ) -> KetQuaTheoDoiThoiGian:
        return KetQuaTheoDoiThoiGian(
            eyes_closed_duration_seconds=eyes_closed_duration,
            eyes_closed_asleep=eyes_closed_asleep,
            long_blink_count_60s=len(self._long_blinks),
            perclos_percent=perclos_percent,
            yawn_count_5m=self._count_since(
                self._yawns, timestamp, YAWN_FATIGUED_WINDOW_SECONDS
            ),
            yawn_count_10m=len(self._yawns),
            nod_count_60s=len(self._nods),
            prolonged_bow=prolonged_bow,
            has_valid_data=has_valid_data,
            partial_data=partial_data,
        )

    @staticmethod
    def _count_since(events: deque[float], timestamp: float, window: float) -> int:
        cutoff = timestamp - window
        return sum(event >= cutoff for event in events)

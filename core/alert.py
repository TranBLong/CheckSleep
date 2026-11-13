"""Alert-level mapping, repeat cooldown, and acknowledgement handling."""

from dataclasses import dataclass
from math import isfinite

from config import (
    ALERT_ACKNOWLEDGEMENT_SNOOZE_SECONDS,
    ALERT_REPEAT_COOLDOWN_SECONDS,
)
from core.types import TrangThai

_ALERT_LEVELS = {
    TrangThai.FATIGUED: 1,
    TrangThai.DROWSY: 2,
    TrangThai.ASLEEP: 3,
}


@dataclass(frozen=True)
class KetQuaCanhBao:
    level: int | None
    should_emit: bool
    sound_enabled: bool
    acknowledged: bool


class BoDieuKhienCanhBao:
    """Map states to alert levels and enforce cooldown/acknowledgement rules."""

    def __init__(
        self,
        repeat_cooldown_seconds: float = ALERT_REPEAT_COOLDOWN_SECONDS,
        acknowledgement_snooze_seconds: float = (
            ALERT_ACKNOWLEDGEMENT_SNOOZE_SECONDS
        ),
    ) -> None:
        if not isfinite(repeat_cooldown_seconds) or repeat_cooldown_seconds < 0:
            raise ValueError("repeat_cooldown_seconds must be non-negative.")
        if (
            not isfinite(acknowledgement_snooze_seconds)
            or acknowledgement_snooze_seconds < 0
        ):
            raise ValueError("acknowledgement_snooze_seconds must be non-negative.")
        self._repeat_cooldown_seconds = repeat_cooldown_seconds
        self._acknowledgement_snooze_seconds = acknowledgement_snooze_seconds
        self._last_emitted_at: dict[int, float] = {}
        self._acknowledged_until: dict[int, float] = {}
        self._last_timestamp: float | None = None

    def evaluate(
        self, timestamp_seconds: float, state: TrangThai
    ) -> KetQuaCanhBao:
        """Return whether this frame should emit the state's alert."""
        self._validate_timestamp(timestamp_seconds)
        self._check_timestamp_order(timestamp_seconds)
        level = _ALERT_LEVELS.get(state)
        if level is None:
            self._last_timestamp = timestamp_seconds
            return KetQuaCanhBao(None, False, False, False)

        acknowledged = (
            timestamp_seconds < self._acknowledged_until.get(level, float("-inf"))
        )
        last_emitted = self._last_emitted_at.get(level)
        cooldown_elapsed = (
            last_emitted is None
            or timestamp_seconds - last_emitted >= self._repeat_cooldown_seconds
        )
        should_emit = cooldown_elapsed and (level == 3 or not acknowledged)
        if should_emit:
            self._last_emitted_at[level] = timestamp_seconds

        self._last_timestamp = timestamp_seconds
        sound_enabled = level == 3 or not acknowledged
        return KetQuaCanhBao(level, should_emit, sound_enabled, acknowledged)

    def acknowledge(
        self, timestamp_seconds: float, state: TrangThai
    ) -> KetQuaCanhBao:
        """Temporarily acknowledge levels 1/2; never silence an active level 3."""
        self._validate_timestamp(timestamp_seconds)
        self._check_timestamp_order(timestamp_seconds)
        level = _ALERT_LEVELS.get(state)
        if level is None:
            self._last_timestamp = timestamp_seconds
            return KetQuaCanhBao(None, False, False, False)
        self._acknowledged_until[level] = (
            timestamp_seconds + self._acknowledgement_snooze_seconds
        )
        self._last_timestamp = timestamp_seconds
        return KetQuaCanhBao(
            level=level,
            should_emit=False,
            sound_enabled=level == 3,
            acknowledged=True,
        )

    def _check_timestamp_order(self, timestamp_seconds: float) -> None:
        if self._last_timestamp is not None and timestamp_seconds < self._last_timestamp:
            raise ValueError("Timestamps must not move backwards.")

    @staticmethod
    def _validate_timestamp(timestamp_seconds: float) -> None:
        if not isfinite(timestamp_seconds):
            raise ValueError("timestamp_seconds must be finite.")

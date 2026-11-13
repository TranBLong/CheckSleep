"""Personal baseline calibration from face measurements."""

from dataclasses import dataclass
from math import isfinite
from statistics import median

from config import (
    CALIBRATION_DURATION_SECONDS,
    CALIBRATION_MIN_VALID_FRAMES,
    EYES_CLOSED_EAR_BASELINE_RATIO,
    HEAD_NOD_PITCH_DROP_DEGREES,
    YAWN_MAR_BASELINE_MULTIPLIER,
)
from core.types import KetQuaPhatHien


@dataclass(frozen=True)
class KetQuaHieuChinh:
    ear0: float
    mar0: float
    pitch0: float
    ear_closed_threshold: float
    mar_yawn_threshold: float
    pitch_nod_threshold: float
    valid_frame_count: int


class BoHieuChinhCaNhan:
    """Collect valid measurements during the initial calibration window."""

    def __init__(
        self,
        duration_seconds: float = CALIBRATION_DURATION_SECONDS,
        minimum_valid_frames: int = CALIBRATION_MIN_VALID_FRAMES,
    ) -> None:
        if not isfinite(duration_seconds) or duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero.")
        if minimum_valid_frames <= 0:
            raise ValueError("minimum_valid_frames must be greater than zero.")
        self._duration_seconds = duration_seconds
        self._minimum_valid_frames = minimum_valid_frames
        self._started_at: float | None = None
        self._last_timestamp: float | None = None
        self._samples: list[tuple[float, float, float]] = []

    def start(self, timestamp_seconds: float) -> None:
        """Begin the five-second collection window."""
        self._validate_timestamp(timestamp_seconds)
        if self._started_at is not None:
            raise RuntimeError("Calibration has already started.")
        self._started_at = timestamp_seconds
        self._last_timestamp = timestamp_seconds

    def add_sample(
        self, result: KetQuaPhatHien, timestamp_seconds: float
    ) -> None:
        """Add a complete face measurement if it falls in the window."""
        if self._started_at is None:
            raise RuntimeError("Start calibration before adding samples.")
        self._validate_timestamp(timestamp_seconds)
        if timestamp_seconds < self._last_timestamp:
            raise ValueError("Calibration timestamps must not move backwards.")
        self._last_timestamp = timestamp_seconds

        if timestamp_seconds > self._started_at + self._duration_seconds:
            return
        values = (result.ear, result.mar, result.pitch)
        if not result.has_face or any(value is None for value in values):
            return
        if not all(isfinite(value) for value in values):
            return
        ear_value, mar_value, pitch_value = values
        if ear_value <= 0 or mar_value <= 0:
            return
        self._samples.append((ear_value, mar_value, pitch_value))

    def is_complete(self, timestamp_seconds: float) -> bool:
        """Return whether the calibration duration has elapsed."""
        if self._started_at is None:
            return False
        self._validate_timestamp(timestamp_seconds)
        return timestamp_seconds >= self._started_at + self._duration_seconds

    @property
    def has_minimum_samples(self) -> bool:
        return len(self._samples) >= self._minimum_valid_frames

    def finish(self, timestamp_seconds: float) -> KetQuaHieuChinh:
        """Return median baselines or report that calibration must be repeated."""
        if not self.is_complete(timestamp_seconds):
            raise RuntimeError("Calibration duration has not elapsed.")
        if timestamp_seconds < self._last_timestamp:
            raise ValueError("Calibration timestamps must not move backwards.")
        if not self.has_minimum_samples:
            raise ValueError(
                "Không đủ khung hình hợp lệ; vui lòng hiệu chỉnh lại "
                f"({len(self._samples)}/{self._minimum_valid_frames})."
            )

        ear0 = median(sample[0] for sample in self._samples)
        mar0 = median(sample[1] for sample in self._samples)
        pitch0 = median(sample[2] for sample in self._samples)
        return KetQuaHieuChinh(
            ear0=ear0,
            mar0=mar0,
            pitch0=pitch0,
            ear_closed_threshold=ear0 * EYES_CLOSED_EAR_BASELINE_RATIO,
            mar_yawn_threshold=mar0 * YAWN_MAR_BASELINE_MULTIPLIER,
            pitch_nod_threshold=pitch0 - HEAD_NOD_PITCH_DROP_DEGREES,
            valid_frame_count=len(self._samples),
        )

    @staticmethod
    def _validate_timestamp(timestamp_seconds: float) -> None:
        if not isfinite(timestamp_seconds):
            raise ValueError("Calibration timestamp must be finite.")

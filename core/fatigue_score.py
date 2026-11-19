"""Điểm mệt mỏi liên tục 0–100 (logic thuần, không camera/DB)."""

from __future__ import annotations

from math import isfinite

from config import (
    FATIGUE_SCORE_ASLEEP_FLOOR,
    FATIGUE_SCORE_HEAD_NOD_REF_COUNT,
    FATIGUE_SCORE_LONG_BLINK_REF_COUNT,
    FATIGUE_SCORE_PERCLOS_REF_PERCENT,
    FATIGUE_SCORE_SMOOTHING_ALPHA,
    FATIGUE_SCORE_WEIGHTS,
    FATIGUE_SCORE_YAWN_REF_COUNT,
)
from core.types import TrangThai


def _clip01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def normalize_component(value: float | None, reference: float) -> float | None:
    """Quy chuẩn về [0, 1]; None giữ nguyên (thiếu dữ liệu)."""
    if value is None:
        return None
    if not isfinite(value) or not isfinite(reference) or reference <= 0:
        return None
    return _clip01(float(value) / float(reference))


def compute_raw_fatigue_score(
    perclos_percent: float | None,
    long_blink_count: int | None,
    yawn_count: int | None,
    head_nod_count: int | None,
    *,
    weights: dict[str, float] | None = None,
    perclos_ref: float = FATIGUE_SCORE_PERCLOS_REF_PERCENT,
    long_blink_ref: float = FATIGUE_SCORE_LONG_BLINK_REF_COUNT,
    yawn_ref: float = FATIGUE_SCORE_YAWN_REF_COUNT,
    head_nod_ref: float = FATIGUE_SCORE_HEAD_NOD_REF_COUNT,
) -> float | None:
    """
    Điểm thô 0–100 từ 4 thành phần.
    Thiếu một chỉ số → bỏ và chia lại trọng số; thiếu hết → None (không trả 0).
    """
    w = weights or FATIGUE_SCORE_WEIGHTS
    components = {
        "perclos": normalize_component(perclos_percent, perclos_ref),
        "long_blink": normalize_component(
            None if long_blink_count is None else float(long_blink_count),
            long_blink_ref,
        ),
        "yawn": normalize_component(
            None if yawn_count is None else float(yawn_count),
            yawn_ref,
        ),
        "head_nod": normalize_component(
            None if head_nod_count is None else float(head_nod_count),
            head_nod_ref,
        ),
    }
    total_weight = 0.0
    weighted = 0.0
    for key, unit in components.items():
        if unit is None:
            continue
        weight = float(w.get(key, 0.0))
        if weight <= 0:
            continue
        total_weight += weight
        weighted += weight * unit
    if total_weight <= 0:
        return None
    return 100.0 * (weighted / total_weight)


def apply_asleep_floor(
    score: float | None,
    state: TrangThai | str,
    floor: float = FATIGUE_SCORE_ASLEEP_FLOOR,
) -> float | None:
    """Khi trạng thái Ngủ gật, điểm không thấp hơn mức sàn."""
    if score is None:
        return None
    state_value = state.value if isinstance(state, TrangThai) else str(state)
    if state_value == TrangThai.ASLEEP.value:
        return max(float(score), float(floor))
    return float(score)


class BoDiemMetMoi:
    """Làm mượt mũ theo thời gian; thiếu hết dữ liệu → None."""

    def __init__(
        self,
        alpha: float = FATIGUE_SCORE_SMOOTHING_ALPHA,
        asleep_floor: float = FATIGUE_SCORE_ASLEEP_FLOOR,
    ) -> None:
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha phải trong (0, 1].")
        self._alpha = float(alpha)
        self._asleep_floor = float(asleep_floor)
        self._smoothed: float | None = None

    def reset(self) -> None:
        self._smoothed = None

    @property
    def value(self) -> float | None:
        return self._smoothed

    def update(
        self,
        perclos_percent: float | None,
        long_blink_count: int | None,
        yawn_count: int | None,
        head_nod_count: int | None,
        state: TrangThai | str,
    ) -> float | None:
        raw = compute_raw_fatigue_score(
            perclos_percent,
            long_blink_count,
            yawn_count,
            head_nod_count,
        )
        if raw is None:
            self._smoothed = None
            return None
        if self._smoothed is None:
            smoothed = raw
        else:
            smoothed = (
                self._alpha * raw + (1.0 - self._alpha) * self._smoothed
            )
        smoothed = apply_asleep_floor(smoothed, state, self._asleep_floor)
        self._smoothed = smoothed
        return smoothed

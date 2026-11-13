"""Pure-Python geometric metrics for MediaPipe Face Mesh landmarks."""

from collections import deque
from math import hypot
from typing import Deque, Sequence, Tuple

from config import METRICS_SMOOTHING_FRAME_COUNT

Point = Sequence[float]  # Image-space (x, y); depth is intentionally ignored.

# Each eye is ordered p1..p6: outer corner, upper points, inner corner,
# then lower points. Names refer to the driver's anatomical left/right.
LEFT_EYE_LANDMARK_INDICES = (362, 385, 387, 263, 373, 380)
RIGHT_EYE_LANDMARK_INDICES = (33, 160, 158, 133, 153, 144)

# Inner lip outline ordered p1..p8 around the mouth:
# left corner, upper-left, upper-center, upper-right, right corner,
# lower-right, lower-center, lower-left.
INNER_MOUTH_LANDMARK_INDICES = (78, 81, 13, 311, 308, 402, 14, 178)


def _validate_landmarks(landmarks: Sequence[Point], expected_count: int) -> None:
    if len(landmarks) != expected_count:
        raise ValueError(f"Expected {expected_count} landmarks, got {len(landmarks)}.")


def _distance(first: Point, second: Point) -> float:
    return hypot(first[0] - second[0], first[1] - second[1])


def _require_nonzero_width(width: float) -> None:
    if width == 0:
        raise ValueError("Landmark points must have nonzero horizontal width.")


def ear(landmarks: Sequence[Point]) -> float:
    """Calculate EAR from six eye points ordered according to the constants above."""
    _validate_landmarks(landmarks, 6)
    width = _distance(landmarks[0], landmarks[3])
    _require_nonzero_width(width)
    return (
        _distance(landmarks[1], landmarks[5])
        + _distance(landmarks[2], landmarks[4])
    ) / (2 * width)


def mar(landmarks: Sequence[Point]) -> float:
    """Calculate inner-mouth MAR from eight points ordered as the constant above."""
    _validate_landmarks(landmarks, 8)
    width = _distance(landmarks[0], landmarks[4])
    _require_nonzero_width(width)
    vertical_sum = (
        _distance(landmarks[1], landmarks[7])
        + _distance(landmarks[2], landmarks[6])
        + _distance(landmarks[3], landmarks[5])
    )
    return vertical_sum / (2 * width)


class MovingAverage:
    """Arithmetic moving average over the most recent frame values."""

    def __init__(self, window_size: int = METRICS_SMOOTHING_FRAME_COUNT) -> None:
        if window_size <= 0:
            raise ValueError("window_size must be greater than zero.")
        self._values: Deque[float] = deque(maxlen=window_size)

    def update(self, value: float) -> float:
        """Add a frame value and return the average of values seen in the window."""
        self._values.append(value)
        return sum(self._values) / len(self._values)

    def reset(self) -> None:
        """Clear accumulated frame values."""
        self._values.clear()

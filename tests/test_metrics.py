import pytest

from config import METRICS_SMOOTHING_FRAME_COUNT
from core.metrics import MovingAverage, ear, mar


def test_ear_is_about_point_three_for_open_eye():
    landmarks = [
        (0.0, 0.0),
        (1.0, 0.6),
        (3.0, 0.6),
        (4.0, 0.0),
        (3.0, -0.6),
        (1.0, -0.6),
    ]

    assert ear(landmarks) == pytest.approx(0.3)


def test_ear_is_below_point_fifteen_for_closed_eye():
    landmarks = [
        (0.0, 0.0),
        (1.0, 0.2),
        (3.0, 0.2),
        (4.0, 0.0),
        (3.0, -0.2),
        (1.0, -0.2),
    ]

    assert ear(landmarks) < 0.15


def test_mar_is_small_for_closed_mouth_and_larger_for_open_mouth():
    closed_mouth = [
        (0.0, 0.0),
        (1.0, 0.05),
        (2.0, 0.0),
        (3.0, 0.05),
        (4.0, 0.0),
        (3.0, -0.05),
        (2.0, 0.0),
        (1.0, -0.05),
    ]
    open_mouth = [
        (0.0, 0.0),
        (1.0, 0.5),
        (2.0, 0.5),
        (3.0, 0.5),
        (4.0, 0.0),
        (3.0, -0.5),
        (2.0, -0.5),
        (1.0, -0.5),
    ]

    assert mar(closed_mouth) < 0.1
    assert mar(open_mouth) > mar(closed_mouth)


def test_moving_average_reduces_frame_to_frame_variation():
    smoother = MovingAverage()
    smoothed_values = [smoother.update(0.2) for _ in range(METRICS_SMOOTHING_FRAME_COUNT - 1)]
    smoothed_values.append(smoother.update(0.8))

    assert smoothed_values[-1] == pytest.approx(0.24)
    assert abs(smoothed_values[-1] - 0.2) < abs(0.8 - 0.2)


def test_moving_average_uses_only_latest_values_in_window():
    smoother = MovingAverage(window_size=2)

    assert smoother.update(0.0) == pytest.approx(0.0)
    assert smoother.update(1.0) == pytest.approx(0.5)
    assert smoother.update(1.0) == pytest.approx(1.0)

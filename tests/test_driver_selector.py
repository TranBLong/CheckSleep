import pytest

from core.driver_selector import (
    BoXacDinhTaiXe,
    non_maximum_suppression,
)
from core.types import FaceCandidate, KetQuaPhatHien


def _candidate(box, ear=0.3, confidence=0.9):
    return FaceCandidate(
        bounding_box=box,
        result=KetQuaPhatHien(
            has_face=True,
            ear=ear,
            mar=0.2,
            pitch=0.0,
            confidence=confidence,
        ),
    )


def test_selector_chooses_only_a_face_inside_driver_roi():
    selector = BoXacDinhTaiXe()
    driver = _candidate((0.08, 0.2, 0.34, 0.6), ear=0.31)
    larger_passenger = _candidate((0.58, 0.1, 0.98, 0.8), ear=0.05)

    selection = selector.update((larger_passenger, driver), 1.0)

    assert selection.detection.ear == pytest.approx(0.31)
    assert selection.driver_id is not None
    assert selection.recalibration_required is False


def test_non_maximum_suppression_merges_overlapping_faces():
    first = _candidate((0.1, 0.1, 0.5, 0.6), confidence=0.8)
    duplicate = _candidate((0.12, 0.11, 0.52, 0.61), confidence=0.95)
    separate = _candidate((0.6, 0.1, 0.9, 0.5))

    result = non_maximum_suppression((first, duplicate, separate), 0.5)

    assert result == (duplicate, separate)


def test_selector_retains_driver_id_for_three_seconds_then_recalibrates():
    selector = BoXacDinhTaiXe()
    face = _candidate((0.1, 0.2, 0.3, 0.5))
    initial = selector.update((face,), 0.0)

    held = selector.update((), 3.0)
    expired = selector.update((), 3.01)
    reacquired = selector.update((face,), 3.1)

    assert held.driver_id == initial.driver_id
    assert held.detection is None
    assert held.recalibration_required is False
    assert expired.driver_id is None
    assert expired.detection is None
    assert expired.recalibration_required is True
    assert reacquired.driver_id != initial.driver_id
    assert reacquired.detection == face.result


def test_selector_rejects_non_monotonic_timestamps():
    selector = BoXacDinhTaiXe()
    selector.update((), 2.0)

    with pytest.raises(ValueError, match="move backwards"):
        selector.update((), 1.0)

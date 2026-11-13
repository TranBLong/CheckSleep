"""Driver-seat face selection, suppression, and IoU-based identity tracking."""

from dataclasses import dataclass
from math import hypot, isfinite, sqrt
from typing import Any, Protocol, Sequence

from config import (
    DRIVER_SEAT_ROI,
    DRIVER_SELECTION_CENTER_WEIGHT,
    DRIVER_SELECTION_SIZE_WEIGHT,
    DRIVER_TRACKING_IOU_THRESHOLD,
    FACE_NMS_IOU_THRESHOLD,
    FACE_TRACKING_LOSS_UNKNOWN_SECONDS,
)
from core.types import FaceCandidate, KetQuaPhatHien

BoundingBox = tuple[float, float, float, float]


class SteeringWheelDetector(Protocol):
    """Extension point for a future steering-wheel detector; no model is loaded."""

    def detect(self, frame: Any) -> Sequence[BoundingBox]: ...


@dataclass(frozen=True)
class DriverSelection:
    detection: KetQuaPhatHien | None
    driver_id: int | None
    recalibration_required: bool = False


@dataclass
class _Track:
    bounding_box: BoundingBox
    last_seen: float


def non_maximum_suppression(
    candidates: Sequence[FaceCandidate],
    iou_threshold: float = FACE_NMS_IOU_THRESHOLD,
) -> tuple[FaceCandidate, ...]:
    """Remove duplicate face boxes, preferring confidence and then box size."""
    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("iou_threshold must be between 0 and 1.")
    for candidate in candidates:
        _validate_box(candidate.bounding_box)
        if (
            candidate.result.confidence is not None
            and not isfinite(candidate.result.confidence)
        ):
            raise ValueError("Face confidence must be finite.")

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate.result.confidence
            if candidate.result.confidence is not None
            else -1.0,
            _area(candidate.bounding_box),
        ),
        reverse=True,
    )
    kept: list[FaceCandidate] = []
    for candidate in ranked:
        if any(
            _intersection_over_union(candidate.bounding_box, accepted.bounding_box)
            > iou_threshold
            for accepted in kept
        ):
            continue
        kept.append(candidate)
    return tuple(kept)


class BoXacDinhTaiXe:
    """Select and retain the driver face (class: BoXacDinhTaiXe)."""

    def __init__(
        self,
        roi: BoundingBox = DRIVER_SEAT_ROI,
        *,
        nms_iou_threshold: float = FACE_NMS_IOU_THRESHOLD,
        tracking_iou_threshold: float = DRIVER_TRACKING_IOU_THRESHOLD,
        lost_timeout_seconds: float = FACE_TRACKING_LOSS_UNKNOWN_SECONDS,
        center_weight: float = DRIVER_SELECTION_CENTER_WEIGHT,
        size_weight: float = DRIVER_SELECTION_SIZE_WEIGHT,
    ) -> None:
        _validate_roi(roi)
        if not 0.0 <= tracking_iou_threshold <= 1.0:
            raise ValueError("tracking_iou_threshold must be between 0 and 1.")
        if not isfinite(lost_timeout_seconds) or lost_timeout_seconds < 0:
            raise ValueError("lost_timeout_seconds must be finite and non-negative.")
        if (
            not isfinite(center_weight)
            or not isfinite(size_weight)
            or center_weight < 0
            or size_weight < 0
            or center_weight + size_weight == 0
        ):
            raise ValueError("Selection weights must be non-negative and non-zero.")

        self._roi = roi
        self._nms_iou_threshold = nms_iou_threshold
        self._tracking_iou_threshold = tracking_iou_threshold
        self._lost_timeout_seconds = lost_timeout_seconds
        self._center_weight = center_weight
        self._size_weight = size_weight
        self._tracks: dict[int, _Track] = {}
        self._next_track_id = 1
        self._driver_id: int | None = None
        self._last_timestamp: float | None = None

    def update(
        self,
        candidates: Sequence[FaceCandidate],
        timestamp_seconds: float,
    ) -> DriverSelection:
        """Return only the locked driver's result; no face yields no detection."""
        if not isfinite(timestamp_seconds):
            raise ValueError("timestamp_seconds must be finite.")
        if (
            self._last_timestamp is not None
            and timestamp_seconds < self._last_timestamp
        ):
            raise ValueError("Timestamps must not move backwards.")
        self._last_timestamp = timestamp_seconds

        suppressed = non_maximum_suppression(candidates, self._nms_iou_threshold)

        expired_driver = self._driver_id is not None and (
            timestamp_seconds - self._tracks[self._driver_id].last_seen
            > self._lost_timeout_seconds
        )
        self._tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if timestamp_seconds - track.last_seen <= self._lost_timeout_seconds
        }
        if expired_driver:
            self._driver_id = None

        assigned_ids = self._assign_tracks(suppressed, timestamp_seconds)
        if expired_driver:
            return DriverSelection(None, None, recalibration_required=True)

        if self._driver_id is not None:
            for candidate, track_id in zip(suppressed, assigned_ids):
                if track_id == self._driver_id:
                    return DriverSelection(candidate.result, self._driver_id)
            return DriverSelection(None, self._driver_id)

        chosen = self._choose_driver(suppressed)
        if chosen is None:
            return DriverSelection(None, None)

        self._driver_id = assigned_ids[chosen]
        return DriverSelection(suppressed[chosen].result, self._driver_id)

    def _assign_tracks(
        self,
        candidates: Sequence[FaceCandidate],
        timestamp_seconds: float,
    ) -> list[int]:
        matches = sorted(
            (
                (
                    _intersection_over_union(candidate.bounding_box, track.bounding_box),
                    track_id,
                    candidate_index,
                )
                for candidate_index, candidate in enumerate(candidates)
                for track_id, track in self._tracks.items()
            ),
            reverse=True,
        )
        assigned_candidates: set[int] = set()
        assigned_tracks: set[int] = set()
        assigned_ids: list[int | None] = [None] * len(candidates)
        for iou, track_id, candidate_index in matches:
            if (
                iou < self._tracking_iou_threshold
                or candidate_index in assigned_candidates
                or track_id in assigned_tracks
            ):
                continue
            assigned_ids[candidate_index] = track_id
            assigned_candidates.add(candidate_index)
            assigned_tracks.add(track_id)

        for index, candidate in enumerate(candidates):
            track_id = assigned_ids[index]
            if track_id is None:
                track_id = self._next_track_id
                self._next_track_id += 1
                assigned_ids[index] = track_id
            self._tracks[track_id] = _Track(candidate.bounding_box, timestamp_seconds)
        return [track_id for track_id in assigned_ids if track_id is not None]

    def _choose_driver(
        self, candidates: Sequence[FaceCandidate]
    ) -> int | None:
        eligible = [
            (index, _area(candidate.bounding_box))
            for index, candidate in enumerate(candidates)
            if _center_in_roi(candidate.bounding_box, self._roi)
        ]
        if not eligible:
            return None
        largest_area = max(area for _, area in eligible)
        weight_total = self._center_weight + self._size_weight

        def score(item: tuple[int, float]) -> tuple[float, float, int]:
            index, area = item
            candidate = candidates[index]
            center_score = _center_score(candidate.bounding_box, self._roi)
            size_score = area / largest_area if largest_area else 0.0
            combined = (
                self._center_weight * center_score
                + self._size_weight * size_score
            ) / weight_total
            return combined, center_score, -index

        return max(eligible, key=score)[0]


def _validate_roi(roi: BoundingBox) -> None:
    _validate_box(roi)
    if roi[0] < 0 or roi[1] < 0 or roi[2] > 1 or roi[3] > 1:
        raise ValueError("roi coordinates must be normalized between 0 and 1.")


def _validate_box(box: BoundingBox) -> None:
    if (
        len(box) != 4
        or not all(isfinite(value) for value in box)
        or box[2] <= box[0]
        or box[3] <= box[1]
    ):
        raise ValueError("Bounding boxes must be finite and have positive area.")


def _area(box: BoundingBox) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _center_in_roi(box: BoundingBox, roi: BoundingBox) -> bool:
    center_x = (box[0] + box[2]) / 2
    center_y = (box[1] + box[3]) / 2
    return roi[0] <= center_x <= roi[2] and roi[1] <= center_y <= roi[3]


def _center_score(box: BoundingBox, roi: BoundingBox) -> float:
    center_x = (box[0] + box[2]) / 2
    center_y = (box[1] + box[3]) / 2
    roi_center_x = (roi[0] + roi[2]) / 2
    roi_center_y = (roi[1] + roi[3]) / 2
    normalized_x = (center_x - roi_center_x) / ((roi[2] - roi[0]) / 2)
    normalized_y = (center_y - roi_center_y) / ((roi[3] - roi[1]) / 2)
    return max(0.0, 1.0 - hypot(normalized_x, normalized_y) / sqrt(2))


def _intersection_over_union(first: BoundingBox, second: BoundingBox) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = _area(first) + _area(second) - intersection
    return intersection / union if union else 0.0

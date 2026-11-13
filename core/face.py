"""MediaPipe face landmarks and geometric eye/mouth metrics."""

from dataclasses import replace
from typing import Optional, Sequence, Tuple

import cv2
import mediapipe as mp

from config import (
    FACE_DETECTION_MIN_CONFIDENCE,
    FACE_DETECTION_MODEL_SELECTION,
    FACE_MESH_MAX_NUM_FACES,
    FACE_MESH_MIN_DETECTION_CONFIDENCE,
    FACE_MESH_MIN_TRACKING_CONFIDENCE,
)
from core.head_pose import estimate_head_pose
from core.metrics import (
    INNER_MOUTH_LANDMARK_INDICES,
    LEFT_EYE_LANDMARK_INDICES,
    RIGHT_EYE_LANDMARK_INDICES,
    ear,
    mar,
)
from core.quality import feature_region_is_usable
from core.types import FaceCandidate, KetQuaPhatHien, Landmark


class FaceLandmarkDetector:
    """Analyze detected faces in an in-memory BGR frame."""

    def __init__(self) -> None:
        self._face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=FACE_MESH_MAX_NUM_FACES,
            refine_landmarks=True,
            min_detection_confidence=FACE_MESH_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=FACE_MESH_MIN_TRACKING_CONFIDENCE,
        )
        self._face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=FACE_DETECTION_MODEL_SELECTION,
            min_detection_confidence=FACE_DETECTION_MIN_CONFIDENCE,
        )

    def process(self, frame) -> KetQuaPhatHien:
        """Return face results for the frame; confidence is the matched detector score."""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mesh_result = self._face_mesh.process(rgb_frame)
        detection_result = self._face_detection.process(rgb_frame)

        detected_faces = getattr(mesh_result, "multi_face_landmarks", None)
        if not detected_faces:
            return KetQuaPhatHien(has_face=False)

        detections = getattr(detection_result, "detections", None)
        height, width = frame.shape[:2]
        candidates = tuple(
            candidate
            for detected_face in detected_faces
            if (
                candidate := self._analyze_face(
                    detected_face.landmark, detections, frame, width, height
                )
            )
            is not None
        )
        if not candidates:
            return KetQuaPhatHien(has_face=False)
        return replace(
            candidates[0].result,
            face_candidates=candidates,
        )

    @staticmethod
    def _analyze_face(
        points: Sequence[object],
        detections: Optional[Sequence[object]],
        frame,
        frame_width: int,
        frame_height: int,
    ) -> FaceCandidate | None:
        landmarks = tuple(
            (float(point.x), float(point.y), float(point.z)) for point in points
        )
        bounds = _normalized_bounds(landmarks)
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            return None
        coordinates = tuple((point[0], point[1]) for point in landmarks)
        eyes_visible = all(
            feature_region_is_usable(frame, landmarks, eye_indices)
            for eye_indices in (
                LEFT_EYE_LANDMARK_INDICES,
                RIGHT_EYE_LANDMARK_INDICES,
            )
        )
        mouth_visible = feature_region_is_usable(
            frame, landmarks, INNER_MOUTH_LANDMARK_INDICES
        )
        eye_ear = (
            (
                ear(_select_points(coordinates, LEFT_EYE_LANDMARK_INDICES))
                + ear(_select_points(coordinates, RIGHT_EYE_LANDMARK_INDICES))
            )
            / 2
            if eyes_visible
            else None
        )
        mouth_mar = (
            mar(_select_points(coordinates, INNER_MOUTH_LANDMARK_INDICES))
            if mouth_visible
            else None
        )
        pose = estimate_head_pose(landmarks, frame_width, frame_height)
        partial_reason = None
        if not eyes_visible and not mouth_visible:
            partial_reason = "Mắt và miệng bị che"
        elif not eyes_visible:
            partial_reason = "Mắt bị che"
        elif not mouth_visible:
            partial_reason = "Miệng bị che"

        result = KetQuaPhatHien(
            has_face=True,
            ear=eye_ear,
            mar=mouth_mar,
            pitch=pose.pitch if eyes_visible or mouth_visible else None,
            yaw=pose.yaw,
            roll=pose.roll,
            confidence=_matched_detection_confidence(landmarks, detections),
            landmarks=landmarks,
            partial_data=partial_reason is not None,
            partial_reason=partial_reason,
        )
        return FaceCandidate(bounding_box=bounds, result=result)

    def close(self) -> None:
        try:
            self._face_mesh.close()
        finally:
            self._face_detection.close()

    def __enter__(self) -> "FaceLandmarkDetector":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def _select_points(
    landmarks: Sequence[Landmark], indices: Sequence[int]
) -> tuple[tuple[float, float], ...]:
    return tuple((landmarks[index][0], landmarks[index][1]) for index in indices)


def _matched_detection_confidence(
    landmarks: Sequence[Landmark], detections: Optional[Sequence[object]]
) -> Optional[float]:
    if not detections or not landmarks:
        return None

    mesh_bounds = _bounds(landmarks)
    best_iou = 0.0
    best_score = None
    for detection in detections:
        location = detection.location_data.relative_bounding_box
        detection_bounds = (
            location.xmin,
            location.ymin,
            location.xmin + location.width,
            location.ymin + location.height,
        )
        iou = _intersection_over_union(mesh_bounds, detection_bounds)
        if iou > best_iou:
            best_iou = iou
            best_score = float(detection.score[0])
    return best_score


def _bounds(landmarks: Sequence[Landmark]) -> Tuple[float, float, float, float]:
    xs = [point[0] for point in landmarks]
    ys = [point[1] for point in landmarks]
    return min(xs), min(ys), max(xs), max(ys)


def _normalized_bounds(
    landmarks: Sequence[Landmark],
) -> Tuple[float, float, float, float]:
    left, top, right, bottom = _bounds(landmarks)
    return (
        max(0.0, min(1.0, left)),
        max(0.0, min(1.0, top)),
        max(0.0, min(1.0, right)),
        max(0.0, min(1.0, bottom)),
    )


def _intersection_over_union(
    first: Tuple[float, float, float, float],
    second: Tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection == 0:
        return 0.0

    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0

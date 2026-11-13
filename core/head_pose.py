"""Head pose estimation from MediaPipe Face Mesh landmarks."""

from dataclasses import dataclass
from math import atan2, degrees, isfinite, sqrt
from typing import Sequence

import cv2
import numpy as np

from core.types import Landmark

_POSE_LANDMARK_INDICES = (1, 152, 33, 263, 61, 291)
_FACE_MODEL_POINTS = np.array(
    [
        (0.0, 0.0, 0.0),
        (0.0, 330.0, -65.0),
        (-225.0, -170.0, -135.0),
        (225.0, -170.0, -135.0),
        (-150.0, 150.0, -125.0),
        (150.0, 150.0, -125.0),
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class HeadPose:
    pitch: float
    yaw: float
    roll: float


def estimate_head_pose(
    landmarks: Sequence[Landmark], frame_width: int, frame_height: int
) -> HeadPose:
    """Estimate Euler angles in degrees; downward nods decrease pitch."""
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("Frame dimensions must be greater than zero.")
    if len(landmarks) <= max(_POSE_LANDMARK_INDICES):
        raise ValueError(
            f"At least {max(_POSE_LANDMARK_INDICES) + 1} landmarks are required."
        )

    image_points = np.asarray(
        [
            (
                landmarks[index][0] * frame_width,
                landmarks[index][1] * frame_height,
            )
            for index in _POSE_LANDMARK_INDICES
        ],
        dtype=np.float64,
    )
    if not np.isfinite(image_points).all():
        raise ValueError("Pose landmarks must contain finite coordinates.")

    focal_length = float(max(frame_width, frame_height))
    camera_matrix = np.array(
        [
            [focal_length, 0.0, frame_width / 2.0],
            [0.0, focal_length, frame_height / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    distortion = np.zeros((4, 1), dtype=np.float64)
    solved, rotation_vector, _ = cv2.solvePnP(
        _FACE_MODEL_POINTS,
        image_points,
        camera_matrix,
        distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not solved:
        raise ValueError("Could not estimate head pose from the landmarks.")

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    pitch = -degrees(atan2(rotation_matrix[2, 1], rotation_matrix[2, 2]))
    yaw = degrees(
        atan2(
            -rotation_matrix[2, 0],
            sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2),
        )
    )
    roll = degrees(atan2(rotation_matrix[1, 0], rotation_matrix[0, 0]))
    if not all(isfinite(angle) for angle in (pitch, yaw, roll)):
        raise ValueError("Estimated head pose is not finite.")
    return HeadPose(pitch=pitch, yaw=yaw, roll=roll)

import cv2
import numpy as np
import pytest

from core.head_pose import estimate_head_pose


def _project_landmarks(rotation_vector):
    width, height = 640, 480
    focal_length = float(max(width, height))
    camera_matrix = np.array(
        [
            [focal_length, 0.0, width / 2.0],
            [0.0, focal_length, height / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    object_points = np.array(
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
    projected, _ = cv2.projectPoints(
        object_points,
        rotation_vector,
        np.array([[0.0], [0.0], [1000.0]], dtype=np.float64),
        camera_matrix,
        np.zeros((4, 1), dtype=np.float64),
    )
    landmarks = [(0.0, 0.0, 0.0) for _ in range(292)]
    for index, point in zip((1, 152, 33, 263, 61, 291), projected.reshape(-1, 2)):
        landmarks[index] = (point[0] / width, point[1] / height, 0.0)
    return landmarks


def test_estimates_neutral_pose_from_projected_landmarks():
    pose = estimate_head_pose(
        _project_landmarks(np.zeros((3, 1), dtype=np.float64)), 640, 480
    )

    assert pose.pitch == pytest.approx(0.0, abs=0.01)
    assert pose.yaw == pytest.approx(0.0, abs=0.01)
    assert pose.roll == pytest.approx(0.0, abs=0.01)


def test_downward_nod_reduces_pitch():
    downward_nod = np.array([[np.deg2rad(20.0)], [0.0], [0.0]])
    pose = estimate_head_pose(_project_landmarks(downward_nod), 640, 480)

    assert pose.pitch == pytest.approx(-20.0, abs=0.1)


def test_estimate_head_pose_requires_pose_landmarks():
    with pytest.raises(ValueError, match="landmarks are required"):
        estimate_head_pose([(0.0, 0.0, 0.0)] * 10, 640, 480)

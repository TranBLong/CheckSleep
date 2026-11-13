from types import SimpleNamespace

import pytest

from core import face as face_module
from core.head_pose import HeadPose
from core.types import KetQuaPhatHien


class FakeProcessor:
    def __init__(self, result):
        self.result = result
        self.closed = False

    def process(self, _frame):
        return self.result

    def close(self):
        self.closed = True


def _landmarks():
    points = [SimpleNamespace(x=0.3, y=0.3, z=0.0) for _ in range(478)]
    # Left eye, open.
    points[362] = SimpleNamespace(x=0.4, y=0.4, z=0.0)
    points[385] = SimpleNamespace(x=0.45, y=0.35, z=0.0)
    points[387] = SimpleNamespace(x=0.55, y=0.35, z=0.0)
    points[263] = SimpleNamespace(x=0.6, y=0.4, z=0.0)
    points[373] = SimpleNamespace(x=0.55, y=0.45, z=0.0)
    points[380] = SimpleNamespace(x=0.45, y=0.45, z=0.0)
    # Right eye, open.
    points[33] = SimpleNamespace(x=0.2, y=0.4, z=0.0)
    points[160] = SimpleNamespace(x=0.25, y=0.35, z=0.0)
    points[158] = SimpleNamespace(x=0.35, y=0.35, z=0.0)
    points[133] = SimpleNamespace(x=0.4, y=0.4, z=0.0)
    points[153] = SimpleNamespace(x=0.35, y=0.45, z=0.0)
    points[144] = SimpleNamespace(x=0.25, y=0.45, z=0.0)
    # Inner mouth.
    points[78] = SimpleNamespace(x=0.35, y=0.6, z=0.0)
    points[81] = SimpleNamespace(x=0.4, y=0.58, z=0.0)
    points[13] = SimpleNamespace(x=0.5, y=0.57, z=0.0)
    points[311] = SimpleNamespace(x=0.6, y=0.58, z=0.0)
    points[308] = SimpleNamespace(x=0.65, y=0.6, z=0.0)
    points[402] = SimpleNamespace(x=0.6, y=0.62, z=0.0)
    points[14] = SimpleNamespace(x=0.5, y=0.63, z=0.0)
    points[178] = SimpleNamespace(x=0.4, y=0.62, z=0.0)
    return points


def _detection(score, bounds):
    left, top, right, bottom = bounds
    return SimpleNamespace(
        location_data=SimpleNamespace(
            relative_bounding_box=SimpleNamespace(
                xmin=left,
                ymin=top,
                width=right - left,
                height=bottom - top,
            )
        ),
        score=[score],
    )


def test_face_detector_returns_metrics_and_matched_detection_confidence(monkeypatch):
    mesh = FakeProcessor(
        SimpleNamespace(multi_face_landmarks=[SimpleNamespace(landmark=_landmarks())])
    )
    detection = FakeProcessor(
        SimpleNamespace(detections=[_detection(0.91, (0.1, 0.1, 0.9, 0.9))])
    )
    monkeypatch.setattr(face_module.cv2, "cvtColor", lambda frame, _code: frame)
    monkeypatch.setattr(face_module.mp.solutions.face_mesh, "FaceMesh", lambda **_: mesh)
    monkeypatch.setattr(
        face_module.mp.solutions.face_detection,
        "FaceDetection",
        lambda **_: detection,
    )
    monkeypatch.setattr(
        face_module,
        "estimate_head_pose",
        lambda *_: HeadPose(pitch=1.0, yaw=2.0, roll=3.0),
    )
    monkeypatch.setattr(face_module, "feature_region_is_usable", lambda *_: True)

    frame = SimpleNamespace(shape=(480, 640, 3))
    with face_module.FaceLandmarkDetector() as analyzer:
        result = analyzer.process(frame)

    assert isinstance(result, KetQuaPhatHien)
    assert result.has_face is True
    assert result.ear > 0
    assert result.mar > 0
    assert result.pitch == 1.0
    assert result.yaw == 2.0
    assert result.roll == 3.0
    assert result.confidence == 0.91
    assert len(result.landmarks) == 478
    assert len(result.face_candidates) == 1
    assert result.face_candidates[0].bounding_box == (0.2, 0.3, 0.65, 0.63)
    assert mesh.closed
    assert detection.closed


def test_face_detector_returns_no_face_result(monkeypatch):
    mesh = FakeProcessor(SimpleNamespace(multi_face_landmarks=[]))
    detection = FakeProcessor(SimpleNamespace(detections=None))
    monkeypatch.setattr(face_module.cv2, "cvtColor", lambda frame, _code: frame)
    monkeypatch.setattr(face_module.mp.solutions.face_mesh, "FaceMesh", lambda **_: mesh)
    monkeypatch.setattr(
        face_module.mp.solutions.face_detection,
        "FaceDetection",
        lambda **_: detection,
    )

    with face_module.FaceLandmarkDetector() as analyzer:
        result = analyzer.process(object())

    assert result.has_face is False
    assert result.ear is None
    assert result.mar is None
    assert result.confidence is None
    assert mesh.closed
    assert detection.closed


def test_face_detector_returns_candidates_for_multiple_faces(monkeypatch):
    first = _landmarks()
    second = [
        SimpleNamespace(x=point.x + 0.5, y=point.y, z=point.z)
        for point in first
    ]
    mesh = FakeProcessor(
        SimpleNamespace(
            multi_face_landmarks=[
                SimpleNamespace(landmark=first),
                SimpleNamespace(landmark=second),
            ]
        )
    )
    detection = FakeProcessor(SimpleNamespace(detections=[]))
    monkeypatch.setattr(face_module.cv2, "cvtColor", lambda frame, _code: frame)
    monkeypatch.setattr(face_module.mp.solutions.face_mesh, "FaceMesh", lambda **_: mesh)
    monkeypatch.setattr(
        face_module.mp.solutions.face_detection,
        "FaceDetection",
        lambda **_: detection,
    )
    monkeypatch.setattr(
        face_module,
        "estimate_head_pose",
        lambda *_: HeadPose(pitch=1.0, yaw=2.0, roll=3.0),
    )
    monkeypatch.setattr(face_module, "feature_region_is_usable", lambda *_: True)

    with face_module.FaceLandmarkDetector() as analyzer:
        result = analyzer.process(SimpleNamespace(shape=(480, 640, 3)))

    assert len(result.face_candidates) == 2
    assert result.face_candidates[0].bounding_box[0] == pytest.approx(0.2)
    assert result.face_candidates[1].bounding_box[0] == pytest.approx(0.7)


@pytest.mark.parametrize(
    ("unusable_regions", "expected_ear", "expected_mar", "expected_pitch"),
    [
        ({face_module.LEFT_EYE_LANDMARK_INDICES}, None, True, 1.0),
        ({face_module.INNER_MOUTH_LANDMARK_INDICES}, True, None, 1.0),
        (
            {
                face_module.LEFT_EYE_LANDMARK_INDICES,
                face_module.RIGHT_EYE_LANDMARK_INDICES,
                face_module.INNER_MOUTH_LANDMARK_INDICES,
            },
            None,
            None,
            None,
        ),
    ],
)
def test_face_detector_omits_metrics_for_occluded_regions(
    monkeypatch, unusable_regions, expected_ear, expected_mar, expected_pitch
):
    mesh = FakeProcessor(
        SimpleNamespace(multi_face_landmarks=[SimpleNamespace(landmark=_landmarks())])
    )
    detection = FakeProcessor(SimpleNamespace(detections=[]))
    monkeypatch.setattr(face_module.cv2, "cvtColor", lambda frame, _code: frame)
    monkeypatch.setattr(face_module.mp.solutions.face_mesh, "FaceMesh", lambda **_: mesh)
    monkeypatch.setattr(
        face_module.mp.solutions.face_detection,
        "FaceDetection",
        lambda **_: detection,
    )
    monkeypatch.setattr(
        face_module,
        "estimate_head_pose",
        lambda *_: HeadPose(pitch=1.0, yaw=2.0, roll=3.0),
    )
    monkeypatch.setattr(
        face_module,
        "feature_region_is_usable",
        lambda _frame, _landmarks, indices: tuple(indices) not in unusable_regions,
    )

    with face_module.FaceLandmarkDetector() as analyzer:
        result = analyzer.process(SimpleNamespace(shape=(480, 640, 3)))

    assert (result.ear is not None) is (expected_ear is True)
    assert (result.mar is not None) is (expected_mar is True)
    assert result.pitch == expected_pitch
    assert result.partial_data is True
    if expected_ear is None and expected_mar is None:
        assert result.partial_reason == "Mắt và miệng bị che"
    elif expected_ear is None:
        assert result.partial_reason == "Mắt bị che"
    else:
        assert result.partial_reason == "Miệng bị che"

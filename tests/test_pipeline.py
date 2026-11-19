import time
from threading import Event, Lock

import numpy as np
import pytest

from core.pipeline import (
    DieuKhienGiamSat,
    build_metric_sample,
    should_sample_metric,
)
from core.classifier import KetQuaMoHinh
from core.types import FaceCandidate, KetQuaPhatHien


class FakeCamera:
    def __init__(self, opened, closed):
        self.opened = opened
        self.closed = closed

    def open(self):
        self.opened.set()

    def read(self):
        time.sleep(0.001)
        pattern = np.indices((8, 8)).sum(axis=0) % 2
        gray = np.where(pattern, 220, 30).astype(np.uint8)
        return np.repeat(gray[:, :, None], 3, axis=2)

    def close(self):
        self.closed.set()


class FakeDetector:
    def __init__(self, processed):
        self.processed = processed

    def process(self, frame):
        self.processed.set()
        return KetQuaPhatHien(has_face=True, ear=0.3, mar=0.1, pitch=0.0)

    def close(self):
        pass


class AdvancingClock:
    def __init__(self):
        self._value = 0.0
        self._lock = Lock()

    def __call__(self):
        with self._lock:
            self._value += 0.1
            return self._value


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _valid_landmarks():
    landmarks = [(0.5, 0.5, 0.0) for _ in range(478)]
    for index, point in {
        362: (0.3, 0.4, 0.0), 385: (0.35, 0.35, 0.0),
        387: (0.4, 0.35, 0.0), 263: (0.45, 0.4, 0.0),
        373: (0.4, 0.45, 0.0), 380: (0.35, 0.45, 0.0),
        33: (0.5, 0.4, 0.0), 160: (0.55, 0.35, 0.0),
        158: (0.6, 0.35, 0.0), 133: (0.65, 0.4, 0.0),
        153: (0.6, 0.45, 0.0), 144: (0.55, 0.45, 0.0),
        78: (0.35, 0.6, 0.0), 81: (0.4, 0.58, 0.0),
        13: (0.5, 0.57, 0.0), 311: (0.6, 0.58, 0.0),
        308: (0.65, 0.6, 0.0), 402: (0.6, 0.62, 0.0),
        14: (0.5, 0.63, 0.0), 178: (0.4, 0.62, 0.0),
    }.items():
        landmarks[index] = point
    return tuple(landmarks)


def test_should_sample_metric_interval():
    assert should_sample_metric(None, 0.0, 1.0) is True
    assert should_sample_metric(0.0, 0.5, 1.0) is False
    assert should_sample_metric(0.0, 1.0, 1.0) is True


def test_build_metric_sample_fields():
    sample = build_metric_sample(0.3, 0.1, 5.0, 2.0, "ALERT")
    assert sample["ear"] == 0.3
    assert sample["trang_thai"] == "ALERT"
    assert sample["thoi_gian"] is not None


def test_pipeline_opens_camera_only_after_start_and_releases_it():
    opened = Event()
    processed = Event()
    closed = Event()
    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: FakeCamera(opened, closed),
        detector_factory=lambda: FakeDetector(processed),
        clock=AdvancingClock(),
    )

    assert not opened.is_set()
    assert pipeline.snapshot()["session_started"] is False
    assert pipeline.start() is True
    assert opened.wait(1)
    assert processed.wait(1)
    assert _wait_for(lambda: pipeline.snapshot()["calibration"] is not None)

    status = pipeline.snapshot()
    assert status["state"] == "ALERT"
    assert status["ear"] == pytest.approx(0.3)
    assert status["error"] is None

    assert pipeline.stop() is True
    assert closed.is_set()
    assert pipeline.snapshot()["running"] is False


def test_pipeline_reports_camera_startup_error():
    class BrokenCamera:
        def open(self):
            raise RuntimeError("Camera đang được ứng dụng khác sử dụng.")

        def close(self):
            pass

    pipeline = DieuKhienGiamSat(camera_factory=BrokenCamera)

    assert pipeline.start() is True
    assert _wait_for(lambda: pipeline.snapshot()["error"] is not None)
    assert pipeline.snapshot()["error"] == "Camera đang được ứng dụng khác sử dụng."
    assert pipeline.snapshot()["state"] == "UNKNOWN"
    assert pipeline.snapshot()["running"] is False


def test_pipeline_stops_cleanly_when_finite_source_returns_no_frame():
    class FiniteCamera(FakeCamera):
        def __init__(self, opened, closed):
            super().__init__(opened, closed)
            self.read_count = 0

        def read(self):
            self.read_count += 1
            if self.read_count > 1:
                return None
            return super().read()

    opened = Event()
    processed = Event()
    closed = Event()
    camera = FiniteCamera(opened, closed)
    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: camera,
        detector_factory=lambda: FakeDetector(processed),
        clock=AdvancingClock(),
    )

    assert pipeline.start()
    assert _wait_for(lambda: not pipeline.snapshot()["running"])
    assert processed.is_set()
    assert pipeline.snapshot()["error"] is None
    assert pipeline.frame_snapshot()[0] == 1
    assert closed.is_set()


def test_pipeline_calibrates_from_driver_face_only_when_two_faces_are_present():
    opened = Event()
    closed = Event()
    driver = FaceCandidate(
        bounding_box=(0.3, 0.2, 0.7, 0.6),
        result=KetQuaPhatHien(
            has_face=True, ear=0.31, mar=0.2, pitch=0.0, confidence=0.9
        ),
    )
    passenger = FaceCandidate(
        bounding_box=(0.86, 0.1, 0.99, 0.8),
        result=KetQuaPhatHien(
            has_face=True, ear=0.05, mar=0.8, pitch=-50.0, confidence=0.9
        ),
    )

    class TwoFaceDetector:
        def process(self, _frame):
            return KetQuaPhatHien(
                has_face=True,
                face_candidates=(passenger, driver),
            )

        def close(self):
            pass

    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: FakeCamera(opened, closed),
        detector_factory=TwoFaceDetector,
        clock=AdvancingClock(),
    )

    assert pipeline.start()
    assert _wait_for(lambda: pipeline.snapshot()["calibration"] is not None)
    status = pipeline.snapshot()
    assert status["calibration"]["ear0"] == pytest.approx(0.31)
    assert status["calibration"]["mar0"] == pytest.approx(0.2)
    assert status["driver_id"] is not None
    assert pipeline.stop()


def test_pipeline_reports_low_quality_and_becomes_unknown_after_sustained_loss():
    class QualitySwitchCamera(FakeCamera):
        def __init__(self, opened, closed):
            super().__init__(opened, closed)
            self.read_count = 0

        def read(self):
            time.sleep(0.001)
            self.read_count += 1
            if self.read_count > 60:
                return np.zeros((8, 8, 3), dtype=np.uint8)
            pattern = np.indices((8, 8)).sum(axis=0) % 2
            gray = np.where(pattern, 220, 30).astype(np.uint8)
            return np.repeat(gray[:, :, None], 3, axis=2)

    opened = Event()
    closed = Event()
    camera = QualitySwitchCamera(opened, closed)
    detector_processed = Event()
    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: camera,
        detector_factory=lambda: FakeDetector(detector_processed),
        clock=AdvancingClock(),
    )

    assert pipeline.start()
    assert _wait_for(
        lambda: camera.read_count > 100
        and pipeline.snapshot()["state"] == "UNKNOWN"
        and pipeline.snapshot()["message"] == "Quá tối và ảnh bị mờ"
    )
    assert detector_processed.is_set()
    assert pipeline.stop()


def test_pipeline_uses_cnn_probabilities_when_cnn_mode_is_selected():
    opened = Event()
    closed = Event()
    classified = Event()
    landmarks = [(0.5, 0.5, 0.0) for _ in range(478)]
    for index, point in {
        362: (0.3, 0.4, 0.0),
        385: (0.35, 0.35, 0.0),
        387: (0.4, 0.35, 0.0),
        263: (0.45, 0.4, 0.0),
        373: (0.4, 0.45, 0.0),
        380: (0.35, 0.45, 0.0),
        33: (0.5, 0.4, 0.0),
        160: (0.55, 0.35, 0.0),
        158: (0.6, 0.35, 0.0),
        133: (0.65, 0.4, 0.0),
        153: (0.6, 0.45, 0.0),
        144: (0.55, 0.45, 0.0),
        78: (0.35, 0.6, 0.0),
        81: (0.4, 0.58, 0.0),
        13: (0.5, 0.57, 0.0),
        311: (0.6, 0.58, 0.0),
        308: (0.65, 0.6, 0.0),
        402: (0.6, 0.62, 0.0),
        14: (0.5, 0.63, 0.0),
        178: (0.4, 0.62, 0.0),
    }.items():
        landmarks[index] = point
    landmarks = tuple(landmarks)

    class LandmarkDetector:
        def process(self, _frame):
            return KetQuaPhatHien(
                has_face=True,
                ear=0.3,
                mar=0.2,
                pitch=0.0,
                landmarks=landmarks,
            )

        def close(self):
            pass

    class FakeClassifier:
        def predict(self, eye_crops, mouth_crop):
            assert len(eye_crops) == 2
            assert mouth_crop is not None
            classified.set()
            return KetQuaMoHinh(eye_closed_probability=0.9, mouth_yawn_probability=0.1)

        def close(self):
            pass

    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: FakeCamera(opened, closed),
        detector_factory=LandmarkDetector,
        clock=AdvancingClock(),
        classifier_mode="cnn",
        classifier_factory=FakeClassifier,
    )

    assert pipeline.start()
    assert classified.wait(1)
    assert _wait_for(lambda: pipeline.snapshot()["eye_closed_probability"] == 0.9)
    assert pipeline.snapshot()["mouth_yawn_probability"] == 0.1
    assert pipeline.stop()


def test_pipeline_cnn_eye_only_uses_mar_and_does_not_mark_partial(monkeypatch):
    monkeypatch.setattr("core.pipeline.CNN_USE_MOUTH_MODEL", False)
    opened = Event()
    closed = Event()
    classified = Event()

    landmarks = [(0.5, 0.5, 0.0)] * 478
    for index, point in {
        33: (0.5, 0.4, 0.0), 160: (0.55, 0.35, 0.0),
        158: (0.6, 0.35, 0.0), 133: (0.65, 0.4, 0.0),
        153: (0.6, 0.45, 0.0), 144: (0.55, 0.45, 0.0),
        362: (0.3, 0.4, 0.0), 385: (0.35, 0.35, 0.0),
        387: (0.4, 0.35, 0.0), 263: (0.45, 0.4, 0.0),
        373: (0.4, 0.45, 0.0), 380: (0.35, 0.45, 0.0),
        78: (0.35, 0.6, 0.0), 81: (0.4, 0.58, 0.0),
        13: (0.5, 0.57, 0.0), 311: (0.6, 0.58, 0.0),
        308: (0.65, 0.6, 0.0), 402: (0.6, 0.62, 0.0),
        14: (0.5, 0.63, 0.0), 178: (0.4, 0.62, 0.0),
    }.items():
        landmarks[index] = point

    class LandmarkDetector:
        def process(self, _frame):
            return KetQuaPhatHien(
                has_face=True, ear=0.3, mar=0.9, pitch=0.0,
                landmarks=tuple(landmarks),
            )

        def close(self):
            pass

    class EyeOnlyClassifier:
        def predict(self, eye_crops, mouth_crop):
            classified.set()
            return KetQuaMoHinh(eye_closed_probability=0.2, mouth_yawn_probability=None)

        def close(self):
            pass

    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: FakeCamera(opened, closed),
        detector_factory=LandmarkDetector,
        clock=AdvancingClock(),
        classifier_mode="cnn",
        classifier_factory=EyeOnlyClassifier,
    )

    assert pipeline.start()
    assert classified.wait(1)
    assert _wait_for(lambda: pipeline.snapshot()["eye_closed_probability"] == 0.2)
    snap = pipeline.snapshot()
    assert snap["mouth_yawn_probability"] is None
    assert snap["partial_data"] is False
    assert pipeline.stop()


@pytest.mark.parametrize("occluded_feature", ["eyes", "mouth", "both"])
def test_pipeline_cnn_does_not_classify_occluded_features(occluded_feature):
    opened = Event()
    closed = Event()
    classified = Event()
    landmarks = _valid_landmarks()
    expected_eye_crops = 0 if occluded_feature in {"eyes", "both"} else 2
    expected_mouth_crop = occluded_feature not in {"mouth", "both"}

    class OccludedDetector:
        def process(self, _frame):
            return KetQuaPhatHien(
                has_face=True,
                ear=None if occluded_feature in {"eyes", "both"} else 0.3,
                mar=None if occluded_feature in {"mouth", "both"} else 0.2,
                pitch=0.0,
                landmarks=landmarks,
            )

        def close(self):
            pass

    class OcclusionClassifier:
        def predict(self, eye_crops, mouth_crop):
            assert len(eye_crops) == expected_eye_crops
            assert (mouth_crop is not None) is expected_mouth_crop
            classified.set()
            # High scores must not override missing geometric measurements.
            return KetQuaMoHinh(0.99, 0.99)

        def close(self):
            pass

    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: FakeCamera(opened, closed),
        detector_factory=OccludedDetector,
        clock=AdvancingClock(),
        classifier_mode="cnn",
        classifier_factory=OcclusionClassifier,
    )

    assert pipeline.start()
    assert classified.wait(1)
    assert pipeline.snapshot()["state"] != "ASLEEP"
    assert pipeline.stop()


def test_pipeline_stops_when_client_heartbeat_times_out():
    from config import CLIENT_HEARTBEAT_TIMEOUT_SECONDS

    opened = Event()
    closed = Event()
    processed = Event()
    clock_value = {"value": 0.0}
    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: FakeCamera(opened, closed),
        detector_factory=lambda: FakeDetector(processed),
        clock=lambda: clock_value["value"],
    )

    assert pipeline.start(session_id=1)
    assert opened.wait(1)
    assert processed.wait(1)
    pipeline.touch()
    clock_value["value"] += CLIENT_HEARTBEAT_TIMEOUT_SECONDS + 0.1

    assert _wait_for(lambda: not pipeline.snapshot()["running"])
    assert closed.is_set()
    assert "mất kết nối trình duyệt" in pipeline.snapshot()["message"]


def test_pipeline_persists_emitted_alert_and_highest_session_state():
    opened = Event()
    closed = Event()
    alert_saved = Event()
    session_ended = Event()
    saved_alerts = []
    saved_sessions = []

    class ChangingDetector(FakeDetector):
        def process(self, frame):
            self.processed.set()
            count = getattr(self, "count", 0) + 1
            self.count = count
            ear = 0.3 if count <= 55 else 0.1
            return KetQuaPhatHien(has_face=True, ear=ear, mar=0.1, pitch=0.0)

    def save_alert(session_id, event):
        saved_alerts.append((session_id, event))
        if event["level"] == 3:
            alert_saved.set()

    def save_session(session_id, summary):
        saved_sessions.append((session_id, summary))
        session_ended.set()

    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: FakeCamera(opened, closed),
        detector_factory=lambda: ChangingDetector(Event()),
        clock=AdvancingClock(),
        on_alert=save_alert,
        on_session_end=save_session,
    )

    assert pipeline.start(session_id=42)
    assert alert_saved.wait(3)
    assert pipeline.stop()
    assert session_ended.wait(1)
    assert any(alert[1]["level"] == 3 for alert in saved_alerts)
    assert saved_sessions[0][0] == 42
    assert saved_sessions[0][1]["state"] == "ASLEEP"


def test_pipeline_continues_when_on_alert_raises():
    opened = Event()
    closed = Event()
    processed = Event()
    call_count = {"n": 0}

    class RaisingAlertDetector(FakeDetector):
        def process(self, frame):
            self.processed.set()
            self.count = getattr(self, "count", 0) + 1
            ear = 0.3 if self.count <= 55 else 0.05
            return KetQuaPhatHien(has_face=True, ear=ear, mar=0.1, pitch=0.0)

    def broken_on_alert(session_id, event):
        call_count["n"] += 1
        raise RuntimeError("SQL Server unavailable")

    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: FakeCamera(opened, closed),
        detector_factory=lambda: RaisingAlertDetector(processed),
        clock=AdvancingClock(),
        on_alert=broken_on_alert,
    )

    assert pipeline.start(session_id=7)
    assert opened.wait(1)
    assert processed.wait(1)
    assert _wait_for(
        lambda: call_count["n"] >= 1 and pipeline.snapshot()["running"] is True,
        timeout=4.0,
    )
    status = pipeline.snapshot()
    assert status["error"] is None
    assert "Không lưu được cảnh báo vào CSDL" in (status["message"] or "")
    assert pipeline.stop() is True
    assert closed.is_set()

import time
from threading import Event, Lock

import numpy as np
import pytest

from core.pipeline import DieuKhienGiamSat
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
        bounding_box=(0.08, 0.2, 0.34, 0.6),
        result=KetQuaPhatHien(
            has_face=True, ear=0.31, mar=0.2, pitch=0.0, confidence=0.9
        ),
    )
    passenger = FaceCandidate(
        bounding_box=(0.58, 0.1, 0.98, 0.8),
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

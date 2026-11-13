"""Background camera-to-alert processing pipeline."""

from collections import deque
from dataclasses import replace
from math import isfinite
from threading import Event, Lock, Thread
from time import monotonic
from typing import Any, Callable, Protocol

import cv2

from config import (
    CALIBRATION_DURATION_SECONDS,
    CLASSIFIER_MODE,
    CNN_EYE_CLOSED_THRESHOLD,
    CNN_MOUTH_YAWN_THRESHOLD,
)
from core.alert import BoDieuKhienCanhBao
from core.calibration import BoHieuChinhCaNhan, KetQuaHieuChinh
from core.camera import QuanLyCamera
from core.classifier import (
    KetQuaMoHinh,
    MoHinhPhatHien,
    extract_eye_crops,
    extract_mouth_crop,
)
from core.driver_selector import BoXacDinhTaiXe, DriverSelection
from core.face import FaceLandmarkDetector
from core.metrics import MovingAverage
from core.quality import assess_frame_quality
from core.state_machine import MayTrangThai
from core.temporal import BoTheoDoiThoiGian, KetQuaTheoDoiThoiGian
from core.types import KetQuaPhatHien, Landmark, TrangThai

_STATE_LABELS = {
    TrangThai.UNKNOWN: "Không xác định",
    TrangThai.ALERT: "Tỉnh táo",
    TrangThai.FATIGUED: "Mệt mỏi",
    TrangThai.DROWSY: "Buồn ngủ",
    TrangThai.ASLEEP: "Ngủ gật",
}
_STATE_SEVERITY = {
    TrangThai.UNKNOWN: -1,
    TrangThai.ALERT: 0,
    TrangThai.FATIGUED: 1,
    TrangThai.DROWSY: 2,
    TrangThai.ASLEEP: 3,
}


class CameraSource(Protocol):
    def open(self) -> None: ...

    def read(self) -> Any | None: ...

    def close(self) -> None: ...


class FaceDetector(Protocol):
    def process(self, frame: Any) -> KetQuaPhatHien: ...

    def close(self) -> None: ...


class DieuKhienGiamSat:
    """Run camera processing on a dedicated thread (class: DieuKhienGiamSat)."""

    def __init__(
        self,
        camera_factory: Callable[[], CameraSource] = QuanLyCamera,
        detector_factory: Callable[[], FaceDetector] = FaceLandmarkDetector,
        clock: Callable[[], float] = monotonic,
        on_alert: Callable[[int, dict], None] | None = None,
        on_session_end: Callable[[int, dict], None] | None = None,
        classifier_mode: str = CLASSIFIER_MODE,
        classifier_factory: Callable[[], MoHinhPhatHien] = MoHinhPhatHien,
    ) -> None:
        if classifier_mode not in {"baseline", "cnn"}:
            raise ValueError("classifier_mode must be 'baseline' or 'cnn'.")
        self._camera_factory = camera_factory
        self._detector_factory = detector_factory
        self._clock = clock
        self._on_alert = on_alert
        self._on_session_end = on_session_end
        self._classifier_mode = classifier_mode
        self._classifier_factory = classifier_factory
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._frame: Any | None = None
        self._landmarks: tuple[Landmark, ...] | None = None
        self._frame_id = 0
        self._frame_times: deque[float] = deque()
        self._alert_sequence = 0
        self._calibration: KetQuaHieuChinh | None = None
        self._alerts = BoDieuKhienCanhBao()
        self._session_id: int | None = None
        self._highest_state = TrangThai.UNKNOWN
        self._status = self._empty_status()

    def start(self, session_id: int | None = None) -> bool:
        """Start a fresh session; camera access begins only inside the worker."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event = Event()
            self._frame = None
            self._landmarks = None
            self._frame_id = 0
            self._frame_times.clear()
            self._calibration = None
            self._session_id = session_id
            self._highest_state = TrangThai.UNKNOWN
            self._alerts = BoDieuKhienCanhBao()
            self._alert_sequence = 0
            self._status = self._empty_status()
            self._status.update(
                session_started=True,
                running=True,
                state=TrangThai.UNKNOWN.value,
                state_label=_STATE_LABELS[TrangThai.UNKNOWN],
                message="Đang khởi động camera...",
            )
            self._thread = Thread(
                target=self._run,
                name="drowsyguard-monitor",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 3.0) -> bool:
        """Request shutdown and wait briefly for camera resources to be released."""
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return True
            self._stop_event.set()
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def snapshot(self) -> dict:
        """Return a thread-safe copy of the latest public status."""
        with self._lock:
            return dict(self._status)

    def acknowledge(self) -> dict:
        """Acknowledge the currently active alert without muting level three."""
        with self._lock:
            state = TrangThai(self._status["state"])
            result = self._alerts.acknowledge(self._clock(), state)
            self._status["alert_acknowledged"] = result.acknowledged
            self._status["alert_sound_enabled"] = result.sound_enabled
            return dict(self._status)

    def frame_snapshot(
        self,
    ) -> tuple[int, Any | None, tuple[Landmark, ...] | None]:
        """Return the newest in-memory frame and landmarks for MJPEG rendering."""
        with self._lock:
            if self._frame is None:
                return self._frame_id, None, None
            return self._frame_id, self._frame.copy(), self._landmarks

    def encode_frame(self, overlay: bool = False) -> bytes | None:
        """Encode the current in-memory frame for a single MJPEG response."""
        _, frame, landmarks = self.frame_snapshot()
        if frame is None:
            return None
        if overlay and landmarks:
            height, width = frame.shape[:2]
            points = [
                (round(x * width), round(y * height))
                for x, y, _ in landmarks
            ]
            left = max(0, min(point[0] for point in points))
            top = max(0, min(point[1] for point in points))
            right = min(width - 1, max(point[0] for point in points))
            bottom = min(height - 1, max(point[1] for point in points))
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 220, 100), 2)
        success, encoded = cv2.imencode(".jpg", frame)
        if not success:
            raise RuntimeError("Không thể mã hóa khung hình camera.")
        return encoded.tobytes()

    def _run(self) -> None:
        camera: CameraSource | None = None
        detector: FaceDetector | None = None
        classifier: MoHinhPhatHien | None = None
        error: str | None = None
        try:
            if self._stop_event.is_set():
                return
            if self._classifier_mode == "cnn":
                classifier = self._classifier_factory()
            camera = self._camera_factory()
            camera.open()
            detector = self._detector_factory()
            self._process_frames(camera, detector, classifier)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
        finally:
            for resource in (detector, classifier, camera):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception as exc:
                        if error is None:
                            error = str(exc) or exc.__class__.__name__
            with self._lock:
                self._status["running"] = False
                self._status["calibrating"] = False
                if error:
                    self._status.update(
                        state=TrangThai.UNKNOWN.value,
                        state_label=_STATE_LABELS[TrangThai.UNKNOWN],
                        error=error,
                        message=f"Không thể tiếp tục giám sát: {error}",
                    )
                elif not self._status["error"]:
                    self._status["message"] = "Đã dừng giám sát."
                session_id = self._session_id
                summary = {
                    "state": self._highest_state.value,
                    "calibration": self._status["calibration"],
                }
            if session_id is not None and self._on_session_end is not None:
                try:
                    self._on_session_end(session_id, summary)
                except Exception as exc:
                    with self._lock:
                        self._status.update(
                            error=f"Không lưu được tóm tắt phiên: {exc}",
                            message=f"Không lưu được tóm tắt phiên: {exc}",
                        )

    def _process_frames(
        self,
        camera: CameraSource,
        detector: FaceDetector,
        classifier: MoHinhPhatHien | None = None,
    ) -> None:
        calibration = BoHieuChinhCaNhan()
        smoothers = (MovingAverage(), MovingAverage(), MovingAverage())
        state_machine = MayTrangThai()
        alerts = BoDieuKhienCanhBao()
        with self._lock:
            self._alerts = alerts

        calibration_started_at = None
        temporal = None
        driver_recalibration_pending = False
        calibration_retry_pending = False
        driver_selector = BoXacDinhTaiXe()
        while not self._stop_event.is_set():
            source_frame = camera.read()
            if source_frame is None:
                return
            timestamp = self._clock()
            frame_quality = assess_frame_quality(source_frame)
            frame = frame_quality.frame
            result = (
                detector.process(frame)
                if frame_quality.accepted
                else KetQuaPhatHien(has_face=False)
            )
            selection: DriverSelection | None = None
            if result.face_candidates:
                selection = driver_selector.update(
                    result.face_candidates, timestamp
                )
                result = selection.detection or KetQuaPhatHien(has_face=False)
            elif not result.has_face:
                selection = driver_selector.update((), timestamp)

            model_result = KetQuaMoHinh(None, None)
            if (
                classifier is not None
                and result.has_face
                and result.landmarks is not None
            ):
                model_result = classifier.predict(
                    extract_eye_crops(frame, result.landmarks),
                    extract_mouth_crop(frame, result.landmarks),
                )

            if selection is not None:
                with self._lock:
                    self._status["driver_id"] = selection.driver_id

            if selection is not None and selection.recalibration_required:
                driver_recalibration_pending = True
                calibration = BoHieuChinhCaNhan()
                calibration.start(timestamp)
                calibration_started_at = timestamp
                self._calibration = None
                temporal = None
                state_machine.reset()
                for smoother in smoothers:
                    smoother.reset()
                with self._lock:
                    self._status.update(
                        state=TrangThai.UNKNOWN.value,
                        state_label=_STATE_LABELS[TrangThai.UNKNOWN],
                        calibrating=True,
                        calibration=None,
                        calibration_remaining=CALIBRATION_DURATION_SECONDS,
                        driver_recalibration_required=driver_recalibration_pending,
                        ear=None,
                        mar=None,
                        pitch=None,
                        perclos=None,
                        partial_data=False,
                        message="Mất theo dõi tài xế quá 3 giây; cần xác minh và hiệu chỉnh lại.",
                    )

            measured = self._smooth_result(result, smoothers)
            self._publish_frame(frame, result.landmarks, timestamp)
            frame_reason = (
                frame_quality.reason
                if not frame_quality.accepted
                else (
                    "Mất khóa tài xế quá 3 giây; cần xác minh và hiệu chỉnh lại."
                    if selection is not None and selection.recalibration_required
                    else (
                        result.partial_reason
                        if result.partial_reason
                        else None if result.has_face else "Không thấy mặt"
                    )
                )
            )

            if calibration_started_at is None:
                calibration_started_at = timestamp
                calibration.start(timestamp)

            if temporal is None:
                if measured is not None:
                    calibration.add_sample(measured, timestamp)
                elapsed = timestamp - calibration_started_at
                remaining = max(0.0, CALIBRATION_DURATION_SECONDS - elapsed)
                with self._lock:
                    self._status.update(
                        calibrating=True,
                        calibration_remaining=remaining,
                        partial_data=result.partial_data,
                        partial_reason=result.partial_reason,
                        quality_reason=frame_reason,
                        message=(
                            frame_reason
                            or (
                                "Mất theo dõi tài xế quá 3 giây; cần xác minh và hiệu chỉnh lại."
                                if driver_recalibration_pending
                                else (
                                    "Không đủ dữ liệu khuôn mặt; vui lòng hiệu chỉnh lại."
                                    if calibration_retry_pending
                                    else "Ngồi thẳng, mở mắt, nhìn thẳng."
                                )
                            )
                        ),
                    )
                if not calibration.is_complete(timestamp):
                    continue
                if not calibration.has_minimum_samples:
                    calibration = BoHieuChinhCaNhan()
                    calibration.start(timestamp)
                    calibration_started_at = timestamp
                    calibration_retry_pending = True
                    state_machine.reset()
                    with self._lock:
                        self._status.update(
                            state=TrangThai.UNKNOWN.value,
                            state_label=_STATE_LABELS[TrangThai.UNKNOWN],
                            calibrating=True,
                            calibration=None,
                            calibration_remaining=CALIBRATION_DURATION_SECONDS,
                            driver_recalibration_required=driver_recalibration_pending,
                            message="Không đủ dữ liệu khuôn mặt; vui lòng xác minh và hiệu chỉnh lại.",
                        )
                    continue
                self._calibration = calibration.finish(timestamp)
                temporal = BoTheoDoiThoiGian(self._calibration.pitch0)
                driver_recalibration_pending = False
                calibration_retry_pending = False
                with self._lock:
                    self._status.update(
                        calibrating=False,
                        calibration_remaining=0.0,
                        driver_recalibration_required=False,
                        calibration={
                            "ear0": self._calibration.ear0,
                            "mar0": self._calibration.mar0,
                            "pitch0": self._calibration.pitch0,
                        },
                        message="Hiệu chỉnh hoàn tất.",
                    )

            has_face = bool(measured and measured.has_face)
            if measured is None:
                temporal_result = temporal.update(
                    timestamp, None, None, None, valid=False
                )
            else:
                eyes_closed = (
                    model_result.eye_closed_probability >= CNN_EYE_CLOSED_THRESHOLD
                    if classifier is not None
                    and model_result.eye_closed_probability is not None
                    else (
                        None
                        if classifier is not None
                        else (
                            measured.ear < self._calibration.ear_closed_threshold
                            if measured.ear is not None
                            else None
                        )
                    )
                )
                mouth_yawn = (
                    model_result.mouth_yawn_probability >= CNN_MOUTH_YAWN_THRESHOLD
                    if classifier is not None
                    and model_result.mouth_yawn_probability is not None
                    else (
                        None
                        if classifier is not None
                        else (
                            measured.mar > self._calibration.mar_yawn_threshold
                            if measured.mar is not None
                            else None
                        )
                    )
                )
                temporal_result = temporal.update(
                    timestamp,
                    eyes_closed,
                    mouth_yawn,
                    measured.pitch,
                    valid=has_face,
                )
            state = state_machine.update(
                timestamp,
                temporal_result,
                has_face=has_face,
                quality_ok=True,
            )
            alert = alerts.evaluate(timestamp, state)
            with self._lock:
                if _STATE_SEVERITY[state] > _STATE_SEVERITY[self._highest_state]:
                    self._highest_state = state
                if alert.should_emit:
                    self._alert_sequence += 1
                self._status.update(
                    state=state.value,
                    state_label=_STATE_LABELS[state],
                    alert_level=alert.level,
                    alert_sound_enabled=alert.sound_enabled,
                    alert_acknowledged=alert.acknowledged,
                    alert_sequence=self._alert_sequence,
                    ear=measured.ear if measured else None,
                    mar=measured.mar if measured else None,
                    pitch=measured.pitch if measured else None,
                    perclos=temporal_result.perclos_percent,
                    partial_data=(
                        temporal_result.partial_data
                        or result.partial_data
                        or (
                            classifier is not None
                            and (
                                model_result.eye_closed_probability is None
                                or model_result.mouth_yawn_probability is None
                            )
                        )
                    ),
                    partial_reason=result.partial_reason,
                    quality_reason=frame_reason,
                    eye_closed_probability=model_result.eye_closed_probability,
                    mouth_yawn_probability=model_result.mouth_yawn_probability,
                    fps=self._fps(timestamp),
                    message=(
                        frame_reason
                        or self._state_message(state, temporal_result)
                    ),
                )
            if (
                alert.should_emit
                and alert.level is not None
                and self._session_id is not None
                and self._on_alert is not None
            ):
                self._on_alert(
                    self._session_id,
                    {
                        "level": alert.level,
                        "state": state.value,
                        "ear": measured.ear if measured else None,
                        "mar": measured.mar if measured else None,
                        "perclos": temporal_result.perclos_percent,
                        "pitch": measured.pitch if measured else None,
                        "confidence": measured.confidence if measured else None,
                    },
                )

    @staticmethod
    def _smooth_result(
        result: KetQuaPhatHien, smoothers: tuple[MovingAverage, ...]
    ) -> KetQuaPhatHien | None:
        if not result.has_face:
            for smoother in smoothers:
                smoother.reset()
            return None
        values = (result.ear, result.mar, result.pitch)
        smoothed = []
        for smoother, value in zip(smoothers, values):
            if value is None or not isfinite(value):
                smoother.reset()
                smoothed.append(None)
            else:
                smoothed.append(smoother.update(value))
        return replace(
            result,
            ear=smoothed[0],
            mar=smoothed[1],
            pitch=smoothed[2],
        )

    def _publish_frame(
        self,
        frame: Any,
        landmarks: tuple[Landmark, ...] | None,
        timestamp: float,
    ) -> None:
        with self._lock:
            self._frame = frame.copy()
            self._landmarks = landmarks
            self._frame_id += 1
            self._frame_times.append(timestamp)
            while self._frame_times and timestamp - self._frame_times[0] > 1:
                self._frame_times.popleft()

    def _fps(self, timestamp: float) -> float:
        while self._frame_times and timestamp - self._frame_times[0] > 1:
            self._frame_times.popleft()
        return float(len(self._frame_times))

    @staticmethod
    def _state_message(
        state: TrangThai, metrics: KetQuaTheoDoiThoiGian
    ) -> str:
        if state == TrangThai.UNKNOWN:
            return "Không thể đánh giá. Hãy chỉnh camera để thấy rõ khuôn mặt."
        if state == TrangThai.FATIGUED:
            return "Có dấu hiệu mệt mỏi. Hãy chú ý nghỉ ngơi."
        if state == TrangThai.DROWSY:
            return "Bạn đang buồn ngủ. Hãy nghỉ ngơi sớm."
        if state == TrangThai.ASLEEP:
            return "Nguy hiểm: hãy dừng xe ở nơi an toàn."
        if metrics.partial_data:
            return "Tỉnh táo — dữ liệu một phần."
        return "Tỉnh táo."

    @staticmethod
    def _empty_status() -> dict:
        return {
            "session_started": False,
            "running": False,
            "state": TrangThai.UNKNOWN.value,
            "state_label": _STATE_LABELS[TrangThai.UNKNOWN],
            "alert_level": None,
            "alert_sound_enabled": False,
            "alert_acknowledged": False,
            "alert_sequence": 0,
            "ear": None,
            "mar": None,
            "perclos": None,
            "pitch": None,
            "fps": 0.0,
            "calibrating": False,
            "calibration_remaining": CALIBRATION_DURATION_SECONDS,
            "calibration": None,
            "partial_data": False,
            "partial_reason": None,
            "quality_reason": None,
            "eye_closed_probability": None,
            "mouth_yawn_probability": None,
            "error": None,
            "driver_id": None,
            "driver_recalibration_required": False,
            "message": "Chưa có phiên giám sát.",
        }

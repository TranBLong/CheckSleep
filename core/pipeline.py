"""Background camera-to-alert processing pipeline."""

from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from math import isfinite
from threading import Event, Lock, Thread
from time import monotonic
from typing import Any, Callable, Protocol

import cv2

from config import (
    CALIBRATION_DURATION_SECONDS,
    CLASSIFIER_MODE,
    CLIENT_HEARTBEAT_TIMEOUT_SECONDS,
    CNN_EYE_CLOSED_THRESHOLD,
    CNN_MOUTH_YAWN_THRESHOLD,
    CNN_USE_MOUTH_MODEL,
    METRIC_LOG_BATCH_SIZE,
    METRIC_LOG_INTERVAL_SECONDS,
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
from core.fatigue_score import BoDiemMetMoi
from core.face import FaceLandmarkDetector
from core.metrics import (
    INNER_MOUTH_LANDMARK_INDICES,
    LEFT_EYE_LANDMARK_INDICES,
    RIGHT_EYE_LANDMARK_INDICES,
    MovingAverage,
)
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


def should_sample_metric(
    last_log_at: float | None, now: float, interval: float
) -> bool:
    """True khi đến lúc gom một mẫu số liệu phiên."""
    return last_log_at is None or (now - last_log_at) >= interval


def build_metric_sample(
    ear: float | None,
    mar: float | None,
    perclos: float | None,
    pitch: float | None,
    state: str,
    fatigue_score: float | None = None,
) -> dict:
    """Tạo dict mẫu số liệu (thời gian wall-clock UTC)."""
    return {
        "thoi_gian": datetime.now(timezone.utc).replace(tzinfo=None),
        "ear": ear,
        "mar": mar,
        "perclos": perclos,
        "pitch": pitch,
        "trang_thai": state,
        "diem_met_moi": fatigue_score,
    }


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
        on_metrics_batch: Callable[[int, list[dict]], None] | None = None,
    ) -> None:
        if classifier_mode not in {"baseline", "cnn"}:
            raise ValueError("classifier_mode must be 'baseline' or 'cnn'.")
        self._camera_factory = camera_factory
        self._detector_factory = detector_factory
        self._clock = clock
        self._on_alert = on_alert
        self._on_session_end = on_session_end
        self._on_metrics_batch = on_metrics_batch
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
        self._last_client_status_at: float | None = None
        self._metric_buffer: list[dict] = []
        self._last_metric_log_at: float | None = None
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
            self._metric_buffer = []
            self._last_metric_log_at = None
            self._highest_state = TrangThai.UNKNOWN
            self._last_client_status_at = None
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

    def touch(self) -> None:
        """Record that the owning browser is still polling session status."""
        with self._lock:
            self._last_client_status_at = self._clock()

    def acknowledge(self) -> dict:
        """Acknowledge the currently active alert without muting level three."""
        with self._lock:
            state = TrangThai(self._status["state"])
            try:
                result = self._alerts.acknowledge(self._clock(), state)
                self._status["alert_acknowledged"] = result.acknowledged
                self._status["alert_sound_enabled"] = result.sound_enabled
            except ValueError:
                # Timestamp lệch do race condition giữa luồng camera và luồng web:
                # Vẫn ghi nhận acknowledged an toàn và không tắt âm mức 3 (ASLEEP).
                self._status["alert_acknowledged"] = True
                self._status["alert_sound_enabled"] = (state == TrangThai.ASLEEP)
            return dict(self._status)

    def frame_snapshot(
        self,
    ) -> tuple[int, Any | None, tuple[Landmark, ...] | None]:
        """Return the newest in-memory frame and landmarks for MJPEG rendering."""
        with self._lock:
            if self._frame is None:
                return self._frame_id, None, None
            return self._frame_id, self._frame.copy(), self._landmarks

    def encode_frame(
        self,
        overlay: bool = False,
        show_box: bool = False,
        show_landmarks: bool = False,
    ) -> bytes | None:
        """Encode the current in-memory frame; optionally draw face box and/or full face landmarks."""
        _, frame, landmarks = self.frame_snapshot()
        if frame is None:
            return None

        # Hỗ trợ cờ overlay cũ (nếu bật overlay -> bật show_box và show_landmarks)
        draw_box = show_box or overlay
        draw_landmarks = show_landmarks or overlay

        if landmarks and (draw_box or draw_landmarks):
            height, width = frame.shape[:2]
            points = [
                (round(x * width), round(y * height))
                for x, y, _ in landmarks
            ]

            # 1. Khung khuôn mặt
            if draw_box:
                left = max(0, min(p[0] for p in points))
                top = max(0, min(p[1] for p in points))
                right = min(width - 1, max(p[0] for p in points))
                bottom = min(height - 1, max(p[1] for p in points))
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 220, 100), 2)

            # 2. Toàn bộ điểm trên khuôn mặt (MediaPipe Face Mesh ~468 điểm)
            if draw_landmarks:
                for point in points:
                    cv2.circle(frame, point, 1, (0, 255, 255), -1)

                # Nối đường mắt + miệng nổi bật
                for indices in (
                    LEFT_EYE_LANDMARK_INDICES,
                    RIGHT_EYE_LANDMARK_INDICES,
                    INNER_MOUTH_LANDMARK_INDICES,
                ):
                    group = [
                        (
                            round(landmarks[i][0] * width),
                            round(landmarks[i][1] * height),
                        )
                        for i in indices
                    ]
                    for start, end in zip(group, group[1:] + group[:1]):
                        cv2.line(frame, start, end, (0, 255, 0), 1)
                    for p in group:
                        cv2.circle(frame, p, 2, (0, 0, 255), -1)

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
                elif (
                    not self._status["error"]
                    and "mất kết nối trình duyệt" not in self._status["message"].lower()
                ):
                    self._status["message"] = "Đã dừng giám sát."
                session_id = self._session_id
                summary = {
                    "state": self._highest_state.value,
                    "calibration": self._status["calibration"],
                }
            self._flush_metric_buffer()
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
        previous_state = TrangThai.UNKNOWN
        alerts = BoDieuKhienCanhBao()
        with self._lock:
            self._alerts = alerts

        calibration_started_at = None
        temporal = None
        fatigue_meter = BoDiemMetMoi()
        driver_recalibration_pending = False
        calibration_retry_pending = False
        driver_selector = BoXacDinhTaiXe()
        while not self._stop_event.is_set():
            with self._lock:
                last_heartbeat = self._last_client_status_at
            if (
                last_heartbeat is not None
                and self._clock() - last_heartbeat
                > CLIENT_HEARTBEAT_TIMEOUT_SECONDS
            ):
                with self._lock:
                    self._status["message"] = (
                        "Phiên dừng do mất kết nối trình duyệt."
                    )
                self._stop_event.set()
                break
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
                eye_crops = (
                    extract_eye_crops(frame, result.landmarks)
                    if result.ear is not None
                    else ()
                )
                mouth_crop = (
                    extract_mouth_crop(frame, result.landmarks)
                    if result.mar is not None
                    else None
                )
                model_result = classifier.predict(
                    eye_crops,
                    mouth_crop,
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
                fatigue_meter.reset()
                state_machine.reset()
                previous_state = TrangThai.UNKNOWN
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
                        fatigue_score=None,
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
                if not calibration.has_valid_baseline:
                    calibration = BoHieuChinhCaNhan()
                    calibration.start(timestamp)
                    calibration_started_at = timestamp
                    calibration_retry_pending = True
                    state_machine.reset()
                    previous_state = TrangThai.UNKNOWN
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
                fatigue_meter.reset()
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
                if classifier is not None:
                    eyes_closed = (
                        model_result.eye_closed_probability
                        >= CNN_EYE_CLOSED_THRESHOLD
                        if measured.ear is not None
                        and model_result.eye_closed_probability is not None
                        else None
                    )
                else:
                    eyes_closed = (
                        measured.ear < self._calibration.ear_closed_threshold
                        if measured.ear is not None
                        else None
                    )
                if classifier is not None and CNN_USE_MOUTH_MODEL:
                    mouth_yawn = (
                        model_result.mouth_yawn_probability
                        >= CNN_MOUTH_YAWN_THRESHOLD
                        if measured.mar is not None
                        and model_result.mouth_yawn_probability is not None
                        else None
                    )
                else:
                    mouth_yawn = (
                        measured.mar > self._calibration.mar_yawn_threshold
                        if measured.mar is not None
                        else None
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
            fatigue_score = fatigue_meter.update(
                temporal_result.perclos_percent
                if temporal_result.has_valid_data
                else None,
                temporal_result.long_blink_count_60s
                if temporal_result.has_valid_data
                else None,
                temporal_result.yawn_count_10m
                if temporal_result.has_valid_data
                else None,
                temporal_result.nod_count_60s
                if temporal_result.has_valid_data
                else None,
                state,
            )
            if (
                temporal is not None
                and _STATE_SEVERITY[state] < _STATE_SEVERITY[previous_state]
                and state != TrangThai.UNKNOWN
            ):
                temporal.reset_windows()
            previous_state = state
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
                    fatigue_score=fatigue_score,
                    partial_data=(
                        temporal_result.partial_data
                        or result.partial_data
                        or (
                            classifier is not None
                            and (
                                model_result.eye_closed_probability is None
                                or (
                                    CNN_USE_MOUTH_MODEL
                                    and model_result.mouth_yawn_probability is None
                                )
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
                    temporal is not None
                    and self._session_id is not None
                    and should_sample_metric(
                        self._last_metric_log_at,
                        timestamp,
                        METRIC_LOG_INTERVAL_SECONDS,
                    )
                ):
                    self._last_metric_log_at = timestamp
                    self._metric_buffer.append(
                        build_metric_sample(
                            measured.ear if measured else None,
                            measured.mar if measured else None,
                            temporal_result.perclos_percent,
                            measured.pitch if measured else None,
                            state.value,
                            fatigue_score,
                        )
                    )
                    if len(self._metric_buffer) >= METRIC_LOG_BATCH_SIZE:
                        self._flush_metric_buffer()
            if (
                alert.should_emit
                and alert.level is not None
                and self._session_id is not None
                and self._on_alert is not None
            ):
                try:
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
                except Exception:
                    # Lỗi CSDL không được dừng vòng giám sát.
                    with self._lock:
                        self._status["message"] = "Không lưu được cảnh báo vào CSDL"

    def _flush_metric_buffer(self) -> None:
        """Ghi lô số liệu qua callback; lỗi CSDL không dừng giám sát."""
        if not self._metric_buffer or self._session_id is None:
            return
        if self._on_metrics_batch is None:
            self._metric_buffer.clear()
            return
        batch = list(self._metric_buffer)
        self._metric_buffer.clear()
        try:
            self._on_metrics_batch(self._session_id, batch)
        except Exception:
            with self._lock:
                self._status["message"] = "Không lưu được số liệu phiên vào CSDL"

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
            "fatigue_score": None,
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

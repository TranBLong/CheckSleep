"""Measure local pipeline throughput and annotated event-to-alert latency."""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from time import perf_counter

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.pipeline import DieuKhienGiamSat


@dataclass(frozen=True)
class BenchmarkResult:
    frame_count: int
    elapsed_seconds: float
    fps: float
    event_start_seconds: float
    alert_time_seconds: float | None
    alert_latency_seconds: float | None


class VideoFileCamera:
    """Adapt a local video file to the pipeline camera interface."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.capture = None
        self.finished = Event()
        self.ready = Event()
        self.timestamp = 0.0
        self.fps = 0.0
        self.frame_count = 0
        self._last_frame = None

    def open(self) -> None:
        try:
            self.capture = cv2.VideoCapture(self.path)
            if not self.capture.isOpened():
                self.capture.release()
                self.capture = None
                raise RuntimeError(f"Không mở được video: {self.path}")
            self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
            if self.fps <= 0:
                self.close()
                raise RuntimeError(
                    "Video không cung cấp FPS hợp lệ để đồng bộ thời gian."
                )
        finally:
            self.ready.set()

    def read(self):
        if self.capture is None:
            raise RuntimeError("Video chưa được mở.")
        success, frame = self.capture.read()
        if success and frame is not None:
            self._last_frame = frame
            self.timestamp = self.frame_count / self.fps
            self.frame_count += 1
            return frame
        self.finished.set()
        if self._last_frame is None:
            raise RuntimeError("Video không chứa khung hình đọc được.")
        return None

    def close(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None


def measure_latency(
    event_start_seconds: float, alert_times: list[float]
) -> tuple[float | None, float | None]:
    """Return first alert at/after the annotated event start and its latency."""
    valid_alerts = sorted(
        timestamp
        for timestamp in alert_times
        if timestamp >= event_start_seconds
    )
    if not valid_alerts:
        return None, None
    first_alert = valid_alerts[0]
    return first_alert, first_alert - event_start_seconds


def format_results(result: BenchmarkResult) -> str:
    rows = (
        ("Số khung xử lý", str(result.frame_count)),
        ("Thời gian thực (s)", f"{result.elapsed_seconds:.3f}"),
        ("FPS xử lý", f"{result.fps:.2f}"),
        ("Mốc bắt đầu điều kiện (s)", f"{result.event_start_seconds:.3f}"),
        (
            "Thời điểm cảnh báo (s)",
            "N/A" if result.alert_time_seconds is None else f"{result.alert_time_seconds:.3f}",
        ),
        (
            "Độ trễ đến cảnh báo (s)",
            "N/A"
            if result.alert_latency_seconds is None
            else f"{result.alert_latency_seconds:.3f}",
        ),
    )
    width = max(len(label) for label, _ in rows)
    return "\n".join(
        [f"{'Chỉ số':<{width}} | Kết quả", f"{'-' * width}-+-{'-' * 12}"]
        + [f"{label:<{width}} | {value}" for label, value in rows]
    )


def run_benchmark(
    video_path: str | Path, event_start_seconds: float, timeout_seconds: float
) -> BenchmarkResult:
    camera = VideoFileCamera(video_path)
    alert_times = []
    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: camera,
        clock=lambda: camera.timestamp,
        on_alert=lambda _session_id, _event: alert_times.append(camera.timestamp),
    )
    started = perf_counter()
    if not pipeline.start(session_id=1):
        raise RuntimeError("Không khởi động được pipeline benchmark.")
    deadline = started + timeout_seconds
    try:
        if not camera.ready.wait(timeout=timeout_seconds):
            raise TimeoutError("Pipeline không mở được video.")
        while not camera.finished.wait(timeout=0.05):
            status = pipeline.snapshot()
            if not status.get("running"):
                raise RuntimeError(
                    status.get("error") or "Pipeline dừng trước khi kết thúc video."
                )
            if perf_counter() >= deadline:
                raise TimeoutError("Benchmark quá thời gian giới hạn.")
    finally:
        if not pipeline.stop(timeout=30.0):
            raise RuntimeError("Pipeline không dừng trong thời gian chờ.")
    error = pipeline.snapshot().get("error")
    if error:
        raise RuntimeError(error)
    elapsed = perf_counter() - started
    frame_count = pipeline.frame_snapshot()[0]
    alert_time, latency = measure_latency(event_start_seconds, alert_times)
    return BenchmarkResult(
        frame_count=frame_count,
        elapsed_seconds=elapsed,
        fps=frame_count / elapsed if elapsed > 0 else 0.0,
        event_start_seconds=event_start_seconds,
        alert_time_seconds=alert_time,
        alert_latency_seconds=latency,
    )


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Đường dẫn video cục bộ đã ghi")
    parser.add_argument(
        "--condition-start-seconds",
        type=float,
        required=True,
        help="Mốc (giây từ đầu video) khi điều kiện buồn ngủ bắt đầu",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300.0,
        help="Thời gian chờ tối đa (mặc định 300 giây)",
    )
    args = parser.parse_args()
    if args.condition_start_seconds < 0 or args.timeout_seconds <= 0:
        parser.error("Mốc điều kiện phải >= 0 và timeout phải > 0.")
    if not args.video.is_file():
        parser.error(f"Không tìm thấy video: {args.video}")
    result = run_benchmark(
        args.video, args.condition_start_seconds, args.timeout_seconds
    )
    print(format_results(result))


if __name__ == "__main__":
    main()

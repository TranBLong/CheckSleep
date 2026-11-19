"""Chạy pipeline trên video cục bộ và ghi CSV; không lưu khung hình."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (
    CALIBRATION_DURATION_SECONDS,
    CLASSIFIER_MODE,
    METRIC_LOG_INTERVAL_SECONDS,
)
from core.pipeline import DieuKhienGiamSat
from scripts.benchmark import VideoFileCamera

CSV_COLUMNS = (
    "session_id",
    "ma_nd",
    "thoi_gian",
    "t_seconds",
    "ear",
    "mar",
    "perclos",
    "pitch",
    "trang_thai",
    "diem_met_moi",
    "ear0",
    "mar0",
    "pitch0",
)


def process_video(
    video_path: Path,
    *,
    sample_interval: float = METRIC_LOG_INTERVAL_SECONDS,
    classifier_mode: str = CLASSIFIER_MODE,
    timeout_seconds: float = 300.0,
) -> tuple[list[dict], dict]:
    """Trích mẫu qua pipeline hiện có; t_seconds dùng nhịp lấy mẫu cấu hình."""
    camera = VideoFileCamera(video_path)
    samples: list[dict] = []
    summary: dict = {}

    def collect_metrics(_session_id: int, batch: list[dict]) -> None:
        samples.extend(batch)

    def collect_summary(_session_id: int, result: dict) -> None:
        summary.update(result)

    pipeline = DieuKhienGiamSat(
        camera_factory=lambda: camera,
        clock=lambda: camera.timestamp,
        on_session_end=collect_summary,
        classifier_mode=classifier_mode,
        on_metrics_batch=collect_metrics,
    )
    started_at = perf_counter()
    if not pipeline.start(session_id=1):
        raise RuntimeError("Pipeline không khởi động được.")
    try:
        if not camera.ready.wait(timeout=timeout_seconds):
            raise TimeoutError("Pipeline không mở được video.")
        while not camera.finished.wait(timeout=0.05):
            status = pipeline.snapshot()
            if not status.get("running"):
                if status.get("error"):
                    raise RuntimeError(status["error"])
                break
            if perf_counter() - started_at >= timeout_seconds:
                raise TimeoutError("Trích đặc trưng quá thời gian giới hạn.")
    finally:
        if not pipeline.stop(timeout=30.0):
            raise RuntimeError("Pipeline không dừng trong thời gian chờ.")

    error = pipeline.snapshot().get("error")
    if error:
        raise RuntimeError(error)
    calibration = summary.get("calibration")
    if not calibration:
        raise RuntimeError("Video quá ngắn hoặc không đủ dữ liệu hiệu chỉnh.")
    if not samples:
        raise RuntimeError("Pipeline không tạo được mẫu số liệu từ video.")

    rows = []
    for index, sample in enumerate(samples):
        rows.append(
            {
                "session_id": None,
                "ma_nd": None,
                "thoi_gian": sample.get("thoi_gian"),
                "t_seconds": CALIBRATION_DURATION_SECONDS + index * sample_interval,
                "ear": sample.get("ear"),
                "mar": sample.get("mar"),
                "perclos": sample.get("perclos"),
                "pitch": sample.get("pitch"),
                "trang_thai": sample.get("trang_thai"),
                "diem_met_moi": sample.get("diem_met_moi"),
                "ear0": calibration["ear0"],
                "mar0": calibration["mar0"],
                "pitch0": calibration["pitch0"],
            }
        )
    return rows, calibration


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(
            {column: row.get(column) for column in CSV_COLUMNS} for row in rows
        )


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Trích đặc trưng từ video cục bộ (không lưu khung hình)."
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--labels",
        type=Path,
        help="CSV start_seconds,end_seconds,label để kiểm tra định dạng.",
    )
    parser.add_argument(
        "--classifier-mode",
        choices=("baseline", "cnn"),
        default=CLASSIFIER_MODE,
    )
    args = parser.parse_args(argv)
    if not args.video.is_file():
        parser.error(f"Không tìm thấy video: {args.video}")
    if args.labels is not None:
        with args.labels.open(newline="", encoding="utf-8-sig") as handle:
            from core.sequence_features import load_label_intervals

            load_label_intervals(list(csv.DictReader(handle)))

    started_at = perf_counter()
    rows, baseline = process_video(
        args.video,
        classifier_mode=args.classifier_mode,
    )
    write_csv(args.output, rows)
    elapsed = perf_counter() - started_at
    print(
        f"Wrote {len(rows)} samples → {args.output} "
        f"(EAR0={baseline['ear0']}, MAR0={baseline['mar0']}, "
        f"Pitch0={baseline['pitch0']}, {elapsed:.1f}s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

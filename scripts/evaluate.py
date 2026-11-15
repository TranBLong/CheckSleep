"""So sánh phát hiện mắt nhắm: baseline EAR và CNN trên video có nhãn."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Sequence

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import (  # noqa: E402
    CALIBRATION_DURATION_SECONDS,
    CALIBRATION_MIN_VALID_FRAMES,
    CNN_EYE_CLOSED_THRESHOLD,
    CNN_USE_MOUTH_MODEL,
    EYES_CLOSED_EAR_BASELINE_RATIO,
    EYE_TFLITE_MODEL_PATH,
    MOUTH_TFLITE_MODEL_PATH,
)
from core.calibration import BoHieuChinhCaNhan  # noqa: E402
from core.classifier import MoHinhPhatHien, extract_eye_crops  # noqa: E402
from core.face import FaceLandmarkDetector  # noqa: E402
from core.types import KetQuaPhatHien  # noqa: E402
from ml.colab_training import compute_binary_metrics  # noqa: E402
from scripts.benchmark import VideoFileCamera  # noqa: E402


@dataclass(frozen=True)
class LabelInterval:
    start_seconds: float
    end_seconds: float
    is_closed: bool


@dataclass(frozen=True)
class MethodMetrics:
    name: str
    precision_closed: float
    recall_closed: float
    f1_closed: float
    accuracy: float
    confusion_matrix: list[list[int]]
    roc_auc: float | None
    fps: float
    n_frames: int


def load_label_intervals(path: str | Path) -> list[LabelInterval]:
    """Read CSV labels: start_seconds,end_seconds,label (closed|open)."""
    label_path = Path(path)
    if not label_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file nhãn: {label_path}")

    intervals = []
    with label_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV nhãn cần cột: start_seconds,end_seconds,label")
        field_map = {name.strip(): name for name in reader.fieldnames if name}
        required = {"start_seconds", "end_seconds", "label"}
        if not required.issubset(field_map):
            raise ValueError("CSV nhãn cần cột: start_seconds,end_seconds,label")

        for row_number, row in enumerate(reader, start=2):
            try:
                start = float(row[field_map["start_seconds"]])
                end = float(row[field_map["end_seconds"]])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Dòng {row_number}: start_seconds/end_seconds phải là số."
                ) from exc
            if not np.isfinite(start) or not np.isfinite(end) or not 0 <= start < end:
                raise ValueError(
                    f"Dòng {row_number}: cần 0 <= start_seconds < end_seconds."
                )
            label = str(row.get(field_map["label"], "")).strip().lower()
            if label not in {"closed", "open"}:
                raise ValueError(
                    f"Dòng {row_number}: label phải là 'closed' hoặc 'open'."
                )
            intervals.append(LabelInterval(start, end, label == "closed"))

    if not intervals:
        raise ValueError("File nhãn không có đoạn nào.")
    intervals.sort(key=lambda item: item.start_seconds)
    for previous, current in zip(intervals, intervals[1:]):
        if current.start_seconds < previous.end_seconds:
            raise ValueError("Các khoảng nhãn không được chồng lấn.")
    return intervals


def label_at_time(
    timestamp_seconds: float, intervals: Sequence[LabelInterval]
) -> bool | None:
    """Return label at timestamp, or None when it falls outside labeled spans."""
    for interval in intervals:
        if interval.start_seconds <= timestamp_seconds < interval.end_seconds:
            return interval.is_closed
    return None


def hard_binary_metrics(y_true: Sequence[int], y_pred: Sequence[int]) -> dict:
    """Metrics for closed eyes (1); confusion matrix rows=true, columns=predicted."""
    actual = np.asarray(y_true, dtype=np.int32).reshape(-1)
    predicted = np.asarray(y_pred, dtype=np.int32).reshape(-1)
    if actual.size == 0 or actual.size != predicted.size:
        raise ValueError("y_true và y_pred phải cùng độ dài và không rỗng.")
    if not set(np.unique(actual)).issubset({0, 1}) or not set(
        np.unique(predicted)
    ).issubset({0, 1}):
        raise ValueError("y_true và y_pred chỉ gồm 0 (open) và 1 (closed).")

    confusion = np.zeros((2, 2), dtype=np.int64)
    np.add.at(confusion, (actual, predicted), 1)
    tn, fp = int(confusion[0, 0]), int(confusion[0, 1])
    fn, tp = int(confusion[1, 0]), int(confusion[1, 1])
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    accuracy = (tp + tn) / actual.size
    return {
        "precision_closed": float(precision),
        "recall_closed": float(recall),
        "f1_closed": float(f1),
        "accuracy": float(accuracy),
        "confusion_matrix": confusion.tolist(),
    }


def metrics_from_scores(
    y_true: Sequence[int], scores: Sequence[float], threshold: float
) -> dict:
    """Compute threshold metrics and ROC-AUC for probability scores."""
    actual = np.asarray(y_true, dtype=np.int32).reshape(-1)
    probabilities = np.asarray(scores, dtype=np.float64).reshape(-1)
    if actual.size == 0 or actual.size != probabilities.size:
        raise ValueError("y_true và scores phải cùng độ dài và không rỗng.")
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold phải nằm trong [0, 1].")
    if set(np.unique(actual)) != {0, 1}:
        raise ValueError("Cần có cả khung 'open' và 'closed' để tính ROC.")
    predicted = (probabilities >= threshold).astype(np.int32)
    result = hard_binary_metrics(actual, predicted)
    result["roc_auc"] = float(
        compute_binary_metrics(actual, probabilities)["roc_auc"]
    )
    return result


def format_comparison_table(methods: Sequence[MethodMetrics]) -> str:
    headers = [
        "Phương pháp", "Precision(nhắm)", "Recall(nhắm)", "F1(nhắm)",
        "Accuracy", "ROC-AUC", "FPS", "N khung",
    ]
    rows = [headers]
    for method in methods:
        rows.append([
            method.name,
            f"{method.precision_closed:.4f}",
            f"{method.recall_closed:.4f}",
            f"{method.f1_closed:.4f}",
            f"{method.accuracy:.4f}",
            "N/A" if method.roc_auc is None else f"{method.roc_auc:.4f}",
            f"{method.fps:.2f}",
            str(method.n_frames),
        ])
    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]
    lines = [
        " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))
        for row in rows
    ]
    separator = "-+-".join("-" * width for width in widths)
    return "\n".join([lines[0], separator, *lines[1:]])


def _require_model_files() -> None:
    required_models = [("mắt", EYE_TFLITE_MODEL_PATH)]
    if CNN_USE_MOUTH_MODEL:
        required_models.append(("miệng", MOUTH_TFLITE_MODEL_PATH))
    for label, path in required_models:
        if not Path(path).is_file():
            raise FileNotFoundError(f"Thiếu model {label} TFLite: {path}")


def collect_predictions(
    video_path: str | Path,
    intervals: Sequence[LabelInterval],
    calibration_seconds: float,
) -> dict:
    """Collect labeled per-frame baseline and CNN eye-closure scores."""
    _require_model_files()
    camera = detector = classifier = calibrator = None
    y_true: list[int] = []
    baseline_pred: list[int] = []
    baseline_scores: list[float] = []
    cnn_scores: list[float] = []
    baseline_elapsed = 0.0
    cnn_elapsed = 0.0
    ear0 = closed_threshold = None
    try:
        camera = VideoFileCamera(video_path)
        detector = FaceLandmarkDetector()
        classifier = MoHinhPhatHien()
        calibrator = BoHieuChinhCaNhan(
            duration_seconds=calibration_seconds,
            minimum_valid_frames=CALIBRATION_MIN_VALID_FRAMES,
        )
        camera.open()
        calibration_started = False

        while True:
            frame = camera.read()
            if frame is None:
                break
            timestamp = float(camera.timestamp)

            started = perf_counter()
            detection: KetQuaPhatHien = detector.process(frame)
            face_elapsed = perf_counter() - started

            if not calibration_started:
                calibrator.start(timestamp)
                calibration_started = True
            if not calibrator.is_complete(timestamp):
                calibrator.add_sample(detection, timestamp)
                continue
            if ear0 is None:
                calibration = calibrator.finish(timestamp)
                ear0 = calibration.ear0
                closed_threshold = calibration.ear_closed_threshold

            label = label_at_time(timestamp, intervals)
            if label is None or not detection.has_face or detection.ear is None:
                continue
            if detection.landmarks is None:
                continue

            assert closed_threshold is not None and ear0 is not None
            started = perf_counter()
            baseline_closed = detection.ear < closed_threshold
            ratio = detection.ear / max(
                ear0 * EYES_CLOSED_EAR_BASELINE_RATIO, np.finfo(float).tiny
            )
            baseline_score = float(np.clip(1.0 - ratio, 0.0, 1.0))
            baseline_elapsed += perf_counter() - started + face_elapsed

            started = perf_counter()
            eye_crops = extract_eye_crops(frame, detection.landmarks)
            model_result = classifier.predict(eye_crops, None)
            cnn_elapsed += perf_counter() - started + face_elapsed
            if model_result.eye_closed_probability is None:
                continue

            y_true.append(int(label))
            baseline_pred.append(int(baseline_closed))
            baseline_scores.append(baseline_score)
            cnn_scores.append(float(model_result.eye_closed_probability))
    finally:
        for resource in (classifier, detector, camera):
            if resource is not None:
                resource.close()

    if not y_true:
        raise RuntimeError(
            "Không có khung vừa có nhãn vừa phát hiện được mặt/mắt. "
            "Kiểm tra video, CSV nhãn và khoảng hiệu chỉnh."
        )
    if set(y_true) != {0, 1}:
        raise RuntimeError(
            "Các khung có nhãn cần có cả 'open' và 'closed' để tính metric/ROC."
        )
    return {
        "y_true": y_true,
        "baseline_pred": baseline_pred,
        "baseline_scores": baseline_scores,
        "cnn_scores": cnn_scores,
        "time_baseline": baseline_elapsed,
        "time_cnn": cnn_elapsed,
        "ear0": ear0,
        "closed_threshold": closed_threshold,
    }


def build_method_metrics(raw: dict) -> list[MethodMetrics]:
    count = len(raw["y_true"])
    baseline = hard_binary_metrics(raw["y_true"], raw["baseline_pred"])
    try:
        baseline_auc = float(
            compute_binary_metrics(raw["y_true"], raw["baseline_scores"])["roc_auc"]
        )
    except ValueError:
        baseline_auc = None
    cnn = metrics_from_scores(
        raw["y_true"], raw["cnn_scores"], CNN_EYE_CLOSED_THRESHOLD
    )
    baseline_time = raw["time_baseline"]
    cnn_time = raw["time_cnn"]
    return [
        MethodMetrics(
            "baseline_EAR", baseline["precision_closed"],
            baseline["recall_closed"], baseline["f1_closed"],
            baseline["accuracy"], baseline["confusion_matrix"], baseline_auc,
            count / baseline_time if baseline_time > 0 else 0.0, count,
        ),
        MethodMetrics(
            "CNN_eye", cnn["precision_closed"], cnn["recall_closed"],
            cnn["f1_closed"], cnn["accuracy"],
            hard_binary_metrics(raw["y_true"],
                                (np.asarray(raw["cnn_scores"]) >= CNN_EYE_CLOSED_THRESHOLD).astype(int)
                                )["confusion_matrix"],
            cnn["roc_auc"], count / cnn_time if cnn_time > 0 else 0.0, count,
        ),
    ]


def write_outputs(methods: Sequence[MethodMetrics], output_dir: Path, extra: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "thresholds": {
            "EYES_CLOSED_EAR_BASELINE_RATIO": EYES_CLOSED_EAR_BASELINE_RATIO,
            "CNN_EYE_CLOSED_THRESHOLD": CNN_EYE_CLOSED_THRESHOLD,
            "ear0": extra.get("ear0"),
            "ear_closed_threshold": extra.get("closed_threshold"),
        },
        "methods": [
            {
                "name": method.name,
                "precision_closed": method.precision_closed,
                "recall_closed": method.recall_closed,
                "f1_closed": method.f1_closed,
                "accuracy": method.accuracy,
                "confusion_matrix": method.confusion_matrix,
                "roc_auc": method.roc_auc,
                "fps": method.fps,
                "n_frames": method.n_frames,
            }
            for method in methods
        ],
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (output_dir / "metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "method", "precision_closed", "recall_closed", "f1_closed",
            "accuracy", "roc_auc", "fps", "n_frames", "tn", "fp", "fn", "tp",
        ])
        for method in methods:
            tn, fp = method.confusion_matrix[0]
            fn, tp = method.confusion_matrix[1]
            writer.writerow([
                method.name, method.precision_closed, method.recall_closed,
                method.f1_closed, method.accuracy,
                "" if method.roc_auc is None else method.roc_auc,
                method.fps, method.n_frames, tn, fp, fn, tp,
            ])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="So sánh baseline EAR và CNN phát hiện mắt nhắm trên video có nhãn."
    )
    parser.add_argument("video", type=Path, help="Đường dẫn video cục bộ")
    parser.add_argument("--labels", type=Path, required=True,
                        help="CSV: start_seconds,end_seconds,label")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Thư mục ghi metrics.json và metrics.csv")
    parser.add_argument("--calibration-seconds", type=float,
                        default=CALIBRATION_DURATION_SECONDS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = parse_args(argv)
    if not np.isfinite(args.calibration_seconds) or args.calibration_seconds <= 0:
        raise SystemExit("--calibration-seconds phải > 0")
    if not args.video.is_file():
        raise SystemExit(f"Không tìm thấy video: {args.video}")
    intervals = load_label_intervals(args.labels)
    raw = collect_predictions(args.video, intervals, args.calibration_seconds)
    methods = build_method_metrics(raw)
    write_outputs(
        methods,
        args.output_dir,
        {"ear0": raw["ear0"], "closed_threshold": raw["closed_threshold"]},
    )
    print(format_comparison_table(methods))
    print(f"\nĐã ghi: {args.output_dir / 'metrics.json'}")
    print(f"Đã ghi: {args.output_dir / 'metrics.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Tổng hợp metrics.json từ evaluate.py thành báo cáo Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REQUIRED_METHOD_KEYS = (
    "name",
    "precision_closed",
    "recall_closed",
    "f1_closed",
    "accuracy",
    "roc_auc",
    "fps",
)

TABLE_COLUMNS = (
    ("name", "Phương pháp"),
    ("precision_closed", "Precision (nhắm)"),
    ("recall_closed", "Recall (nhắm)"),
    ("f1_closed", "F1 (nhắm)"),
    ("accuracy", "Accuracy"),
    ("roc_auc", "ROC-AUC"),
    ("fps", "FPS"),
)


def load_metrics_dir(path: str | Path) -> dict[str, Any]:
    """Đọc metrics.json (+ kiểm tra metrics.csv tồn tại). Không bịa số."""
    root = Path(path)
    json_path = root / "metrics.json"
    csv_path = root / "metrics.csv"
    if not json_path.is_file():
        raise FileNotFoundError(f"Thiếu metrics.json trong: {root}")
    if not csv_path.is_file():
        raise FileNotFoundError(f"Thiếu metrics.csv trong: {root}")
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"metrics.json không hợp lệ tại {json_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"metrics.json phải là object: {json_path}")
    methods = payload.get("methods")
    if not isinstance(methods, list) or not methods:
        raise ValueError(f"metrics.json thiếu mảng methods không rỗng: {json_path}")
    return payload


def pick_method(
    payload: dict[str, Any],
    preferred_name: str | None = None,
) -> dict[str, Any]:
    """Chọn một method; thiếu khóa bắt buộc → lỗi rõ."""
    methods = payload["methods"]
    chosen: dict[str, Any] | None = None
    if preferred_name:
        for method in methods:
            if isinstance(method, dict) and method.get("name") == preferred_name:
                chosen = method
                break
        if chosen is None:
            names = [
                method.get("name") for method in methods if isinstance(method, dict)
            ]
            raise ValueError(
                f"Không tìm thấy method '{preferred_name}'. Có: {names}"
            )
    else:
        first = methods[0]
        if not isinstance(first, dict):
            raise ValueError("Phần tử methods[0] phải là object")
        chosen = first

    missing = [key for key in REQUIRED_METHOD_KEYS if key not in chosen]
    if missing:
        raise ValueError(
            f"Method '{chosen.get('name', '?')}' thiếu khóa: {missing}"
        )
    return chosen


def format_metric_value(key: str, value: Any) -> str:
    """Định dạng ô bảng; roc_auc=None → N/A."""
    if key == "name":
        return str(value)
    if key == "roc_auc" and value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        if key == "fps":
            return f"{float(value):.2f}"
        return f"{float(value):.4f}"
    return str(value)


def build_comparison_table(rows: Sequence[dict[str, Any]]) -> str:
    """Dựng bảng Markdown so sánh các method."""
    if not rows:
        raise ValueError("Không có dòng số liệu để lập bảng")
    headers = [label for _, label in TABLE_COLUMNS]
    body = [
        [format_metric_value(key, row[key]) for key, _ in TABLE_COLUMNS]
        for row in rows
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for cells in body:
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def extract_run_notes(payload: dict[str, Any], source_dir: Path) -> str:
    """Ghi chú đo trên video/máy/nhãn nếu metadata có; không bịa."""
    meta = payload.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    video = meta.get("video") or payload.get("video")
    labels = meta.get("labels") or payload.get("labels")
    machine = meta.get("machine") or payload.get("machine")
    note = meta.get("note") or payload.get("note")

    parts = [f"Nguồn thư mục: `{source_dir}`"]
    if video:
        parts.append(f"video: `{video}`")
    if labels:
        parts.append(f"nhãn: `{labels}`")
    if machine:
        parts.append(f"máy: {machine}")
    if note:
        parts.append(str(note))
    if not any((video, labels, machine, note)):
        parts.append(
            "(metrics.json không có metadata video/nhãn/máy — "
            "không suy diễn điều kiện đo)"
        )
    return "; ".join(parts)


def build_report(
    baseline_payload: dict[str, Any],
    cnn_payload: dict[str, Any],
    baseline_dir: Path,
    cnn_dir: Path,
    baseline_method_name: str | None = None,
    cnn_method_name: str | None = None,
) -> str:
    """Ghép báo cáo Markdown đầy đủ từ hai kết quả evaluate."""
    baseline_row = pick_method(baseline_payload, baseline_method_name)
    cnn_row = pick_method(cnn_payload, cnn_method_name)
    table = build_comparison_table([baseline_row, cnn_row])

    lines = [
        "# Kết quả đánh giá phát hiện mắt nhắm",
        "",
        "Số liệu lấy trực tiếp từ `metrics.json` do `scripts/evaluate.py` ghi ra; "
        "không suy diễn thêm.",
        "",
        "## Bảng so sánh",
        "",
        table,
        "",
        "## Điều kiện đo",
        "",
        f"- **Baseline:** {extract_run_notes(baseline_payload, baseline_dir)}",
        f"- **CNN:** {extract_run_notes(cnn_payload, cnn_dir)}",
        "",
        "## Hạn chế",
        "",
        "_(Người dùng điền: video/nhãn dùng chung hay khác nhau, "
        "ánh sáng, góc camera, giới hạn tập nhãn, v.v.)_",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tổng hợp kết quả evaluate.py thành docs/RESULTS.md"
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="Thư mục kết quả baseline (có metrics.json, metrics.csv)",
    )
    parser.add_argument(
        "--cnn",
        type=Path,
        required=True,
        help="Thư mục kết quả CNN (có metrics.json, metrics.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/RESULTS.md"),
        help="File Markdown đầu ra (mặc định docs/RESULTS.md)",
    )
    parser.add_argument(
        "--baseline-method",
        default=None,
        help="Tên method trong metrics baseline (mặc định methods[0])",
    )
    parser.add_argument(
        "--cnn-method",
        default=None,
        help="Tên method trong metrics CNN (mặc định methods[0])",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = parse_args(argv)
    baseline_payload = load_metrics_dir(args.baseline)
    cnn_payload = load_metrics_dir(args.cnn)
    report = build_report(
        baseline_payload,
        cnn_payload,
        args.baseline.resolve(),
        args.cnn.resolve(),
        args.baseline_method,
        args.cnn_method,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Đã ghi: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Xuất SoLieuPhien và baseline phiên ra CSV; không lưu ảnh hoặc video."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.session_service import SessionService

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


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def rows_for_session(service: SessionService, session_id: int) -> list[dict]:
    session = service.get_session(session_id)
    if session is None:
        raise ValueError(f"Không tìm thấy phiên MaPhien={session_id}.")
    metrics = service.list_metrics(session_id)
    baseline = {
        "ear0": session.get("EAR0"),
        "mar0": session.get("MAR0"),
        "pitch0": session.get("Pitch0"),
    }
    first_timestamp = None
    output = []
    for metric in metrics:
        timestamp = _parse_time(metric.get("ThoiGian"))
        if first_timestamp is None and timestamp is not None:
            first_timestamp = timestamp
        elapsed = (
            (timestamp - first_timestamp).total_seconds()
            if timestamp is not None and first_timestamp is not None
            else None
        )
        output.append(
            {
                "session_id": session_id,
                "ma_nd": session.get("MaND"),
                "thoi_gian": metric.get("ThoiGian"),
                "t_seconds": elapsed,
                "ear": metric.get("EAR"),
                "mar": metric.get("MAR"),
                "perclos": metric.get("PERCLOS"),
                "pitch": metric.get("Pitch"),
                "trang_thai": metric.get("TrangThai"),
                "diem_met_moi": metric.get("DiemMetMoi"),
                **baseline,
            }
        )
    return output


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
    parser = argparse.ArgumentParser(description="Xuất số liệu phiên ra CSV.")
    parser.add_argument("--session-id", type=int, help="MaPhien cần xuất.")
    parser.add_argument(
        "--user-id",
        type=int,
        help="Xuất tất cả phiên của MaND (bỏ qua nếu đã có --session-id).",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.session_id is None and args.user_id is None:
        parser.error("Cần --session-id hoặc --user-id.")

    service = SessionService()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.session_id is not None:
        rows = rows_for_session(service, args.session_id)
        path = args.output_dir / f"session_{args.session_id}_metrics.csv"
        write_csv(path, rows)
        print(f"Wrote {len(rows)} rows → {path}")
        return 0

    sessions = service.list_for_user(args.user_id)
    if not sessions:
        print(f"Không có phiên cho MaND={args.user_id}.")
        return 0
    total = 0
    for session in sessions:
        session_id = int(session["MaPhien"])
        rows = rows_for_session(service, session_id)
        path = args.output_dir / f"session_{session_id}_metrics.csv"
        write_csv(path, rows)
        total += len(rows)
        print(f"session {session_id}: {len(rows)} rows → {path}")
    print(f"Tổng {total} dòng, {len(sessions)} phiên.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

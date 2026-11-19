"""Kiểm thử CSV export và integration SQL Server tùy chọn."""

import csv
import os
import re
import uuid
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from scripts.export_session_metrics import (
    CSV_COLUMNS,
    rows_for_session,
    write_csv,
)


def test_rows_for_session_includes_baseline_and_elapsed_time():
    class FakeSessionService:
        def get_session(self, session_id):
            assert session_id == 12
            return {
                "MaND": 4,
                "EAR0": 0.3,
                "MAR0": 0.4,
                "Pitch0": 10.0,
            }

        def list_metrics(self, session_id):
            return [
                {
                    "ThoiGian": "2025-01-01 10:00:00",
                    "EAR": 0.3,
                    "MAR": 0.4,
                    "PERCLOS": 5.0,
                    "Pitch": 10.0,
                    "TrangThai": "ALERT",
                    "DiemMetMoi": 10.0,
                },
                {
                    "ThoiGian": "2025-01-01 10:00:02",
                    "EAR": 0.2,
                    "MAR": 0.5,
                    "PERCLOS": 12.0,
                    "Pitch": 5.0,
                    "TrangThai": "FATIGUED",
                    "DiemMetMoi": 50.0,
                },
            ]

    rows = rows_for_session(FakeSessionService(), 12)

    assert len(rows) == 2
    assert rows[0]["ma_nd"] == 4
    assert rows[0]["ear0"] == pytest.approx(0.3)
    assert rows[1]["t_seconds"] == pytest.approx(2.0)


def test_rows_for_session_rejects_unknown_session():
    class MissingSessionService:
        def get_session(self, session_id):
            return None

    with pytest.raises(ValueError, match="MaPhien=21"):
        rows_for_session(MissingSessionService(), 21)


def test_write_csv_writes_expected_header(tmp_path):
    path = tmp_path / "nested" / "metrics.csv"
    write_csv(path, [{"session_id": 1, "ear": 0.25}])

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        row = next(reader)

    assert tuple(reader.fieldnames) == CSV_COLUMNS
    assert row["session_id"] == "1"
    assert row["ear"] == "0.25"


@pytest.fixture
def sql_services():
    if not os.getenv("TEST_DB_NAME"):
        pytest.skip("Cần TEST_DB_* trỏ đến database test riêng.")
    if "test" not in os.environ["TEST_DB_NAME"].casefold():
        pytest.fail("TEST_DB_NAME phải chỉ rõ database test riêng.")

    from db.connection import get_test_connection
    from services.session_service import SessionService
    from services.user_service import UserService

    connection = get_test_connection()
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
    script = schema_path.read_text(encoding="utf-8")
    try:
        cursor = connection.cursor()
        for batch in re.split(r"(?im)^\s*GO\s*$", script):
            if batch.strip():
                cursor.execute(batch)
        connection.commit()
    finally:
        connection.close()

    return {
        "users": UserService(connection_factory=get_test_connection),
        "sessions": SessionService(connection_factory=get_test_connection),
    }


def test_export_writes_csv_for_test_database_session(sql_services, tmp_path):
    username = f"export_{uuid.uuid4().hex[:20]}"
    user_id = sql_services["users"].create_driver(
        username,
        generate_password_hash("test-only-password"),
        "SQL Server export test",
    )
    session_id = sql_services["sessions"].start_session(user_id)
    sql_services["sessions"].append_metrics(
        session_id,
        [
            {
                "thoi_gian": None,
                "ear": 0.28,
                "mar": 0.12,
                "perclos": 8.5,
                "pitch": 1.0,
                "trang_thai": "ALERT",
                "diem_met_moi": 12.5,
            }
        ],
    )
    sql_services["sessions"].end_session(
        session_id,
        state="ALERT",
        calibration={"ear0": 0.3, "mar0": 0.1, "pitch0": 2.0},
    )
    rows = rows_for_session(sql_services["sessions"], session_id)
    output = tmp_path / f"session_{session_id}.csv"
    write_csv(output, rows)

    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        exported = list(reader)

    assert tuple(reader.fieldnames) == CSV_COLUMNS
    assert len(exported) == 1
    assert exported[0]["ear0"] == "0.3"
    assert exported[0]["ear"] == "0.28"

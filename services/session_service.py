"""Monitoring session creation, completion, and owner-scoped history."""

from services._database import row_as_dict, rows_as_dicts, transaction


class SessionService:
    def __init__(self, connection_factory=None):
        self._connection_factory = connection_factory or _default_connection

    def start_session(self, user_id: int) -> int:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO dbo.PhienGiamSat (MaND, TrangThai)
                OUTPUT INSERTED.MaPhien
                VALUES (?, N'Running')
                """,
                user_id,
            )
            return int(cursor.fetchone()[0])

    def end_session(
        self,
        session_id: int,
        state: str,
        calibration: dict | None = None,
    ) -> None:
        values = calibration or {}
        with transaction(self._connection_factory) as conn:
            conn.cursor().execute(
                """
                UPDATE dbo.PhienGiamSat
                SET ThoiGianKetThuc = SYSUTCDATETIME(),
                    TrangThai = ?,
                    SoLanCanhBao = (
                        SELECT COUNT(*)
                        FROM dbo.LichSuCanhBao
                        WHERE MaPhien = ?
                    ),
                    EAR0 = ?,
                    MAR0 = ?,
                    Pitch0 = ?
                WHERE MaPhien = ? AND ThoiGianKetThuc IS NULL
                """,
                state,
                session_id,
                values.get("ear0"),
                values.get("mar0"),
                values.get("pitch0"),
                session_id,
            )

    def list_for_user(self, user_id: int) -> list[dict]:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MaPhien, ThoiGianBatDau, ThoiGianKetThuc, TrangThai,
                       SoLanCanhBao, EAR0, MAR0, Pitch0
                FROM dbo.PhienGiamSat
                WHERE MaND = ?
                ORDER BY ThoiGianBatDau DESC
                """,
                user_id,
            )
            return rows_as_dicts(cursor, cursor.fetchall())

    def get_for_user(self, session_id: int, user_id: int) -> dict | None:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MaPhien, MaND, ThoiGianBatDau, ThoiGianKetThuc,
                       TrangThai, SoLanCanhBao, EAR0, MAR0, Pitch0
                FROM dbo.PhienGiamSat
                WHERE MaPhien = ? AND MaND = ?
                """,
                session_id,
                user_id,
            )
            return row_as_dict(cursor, cursor.fetchone())


def _default_connection():
    from db.connection import get_connection

    return get_connection()

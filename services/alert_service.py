"""Persist alert transitions with parameterized SQL."""

from services._database import transaction


class AlertService:
    def __init__(self, connection_factory=None):
        self._connection_factory = connection_factory or _default_connection

    def record_alert(
        self,
        session_id: int,
        level: int,
        state: str,
        ear: float | None,
        mar: float | None,
        perclos: float | None,
        pitch: float | None,
        confidence: float | None,
    ) -> None:
        signs = {
            "FATIGUED": "Dấu hiệu mệt mỏi",
            "DROWSY": "Dấu hiệu buồn ngủ",
            "ASLEEP": "Ngủ gật",
        }
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO dbo.LichSuCanhBao (
                    MaPhien, DauHieu, GiaTriEAR, GiaTriMAR,
                    GiaTriPERCLOS, GiaTriPitch, DiemTinCay, MucCanhBao
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                session_id,
                signs.get(state, "Cảnh báo"),
                ear,
                mar,
                perclos,
                pitch,
                confidence,
                level,
            )
            cursor.execute(
                """
                UPDATE dbo.PhienGiamSat
                SET SoLanCanhBao = SoLanCanhBao + 1
                WHERE MaPhien = ?
                """,
                session_id,
            )

    def list_for_user_session(self, session_id: int, user_id: int) -> list[dict]:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT a.MaCanhBao, a.ThoiGian, a.DauHieu, a.GiaTriEAR,
                       a.GiaTriMAR, a.GiaTriPERCLOS, a.GiaTriPitch,
                       a.DiemTinCay, a.MucCanhBao, a.TrangThaiXuLy
                FROM dbo.LichSuCanhBao AS a
                INNER JOIN dbo.PhienGiamSat AS p ON p.MaPhien = a.MaPhien
                WHERE a.MaPhien = ? AND p.MaND = ?
                ORDER BY a.ThoiGian DESC
                """,
                session_id,
                user_id,
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _default_connection():
    from db.connection import get_connection

    return get_connection()

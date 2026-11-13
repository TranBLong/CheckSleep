"""SQL-backed user configuration operations."""

from config import DEFAULT_DRIVER_CONFIG
from services._database import transaction


class ConfigService:
    def __init__(self, connection_factory=None):
        self._connection_factory = connection_factory

    def create_default(self, user_id: int, connection=None) -> None:
        values = DEFAULT_DRIVER_CONFIG
        if connection is not None:
            self._insert_default(connection.cursor(), user_id, values)
            return
        with transaction(self._connection_factory) as conn:
            self._insert_default(conn.cursor(), user_id, values)

    def get_for_user(self, user_id: int) -> dict | None:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MaND, NguongEAR, NguongMAR, NguongPERCLOS,
                       NguongGatPitch, SoKhungHinhLienTiep, ThoiGianHaMuc,
                       LoaiCanhBao, LuuHinhMinhHoa
                FROM dbo.CauHinh
                WHERE MaND = ?
                """,
                user_id,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                column[0]: value
                for column, value in zip(cursor.description, row)
            }

    @staticmethod
    def _insert_default(cursor, user_id: int, values: dict) -> None:
        cursor.execute(
            """
            INSERT INTO dbo.CauHinh (
                MaND, NguongEAR, NguongMAR, NguongPERCLOS,
                NguongGatPitch, SoKhungHinhLienTiep, ThoiGianHaMuc,
                LoaiCanhBao, LuuHinhMinhHoa
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            user_id,
            values["NguongEAR"],
            values["NguongMAR"],
            values["NguongPERCLOS"],
            values["NguongGatPitch"],
            values["SoKhungHinhLienTiep"],
            values["ThoiGianHaMuc"],
            values["LoaiCanhBao"],
            values["LuuHinhMinhHoa"],
        )

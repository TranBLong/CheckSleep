"""Parameterized account operations and driver registration."""

from services._database import row_as_dict, transaction
from services.config_service import ConfigService


class UserService:
    def __init__(self, connection_factory=None, config_service=None):
        self._connection_factory = connection_factory or _default_connection
        self._config_service = config_service or ConfigService(
            connection_factory=self._connection_factory
        )

    def get_by_id(self, user_id: int) -> dict | None:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MaND, TenDangNhap, MatKhau, HoTen, SoDienThoai, VaiTro, BiKhoa
                FROM dbo.TaiKhoan
                WHERE MaND = ?
                """,
                user_id,
            )
            return row_as_dict(cursor, cursor.fetchone())

    def get_by_username(self, username: str) -> dict | None:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MaND, TenDangNhap, MatKhau, HoTen, SoDienThoai, VaiTro, BiKhoa
                FROM dbo.TaiKhoan
                WHERE TenDangNhap = ?
                """,
                username,
            )
            return row_as_dict(cursor, cursor.fetchone())

    def create_driver(
        self,
        username: str,
        password_hash: str,
        full_name: str,
        phone: str | None = None,
    ) -> int:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO dbo.TaiKhoan
                    (TenDangNhap, MatKhau, HoTen, SoDienThoai, VaiTro)
                OUTPUT INSERTED.MaND
                VALUES (?, ?, ?, ?, N'Driver')
                """,
                username,
                password_hash,
                full_name,
                phone,
            )
            user_id = int(cursor.fetchone()[0])
            self._config_service.create_default(user_id, connection=conn)
            return user_id

    def seed_admin(
        self, username: str, password_hash: str, full_name: str = "Quản trị viên"
    ) -> int:
        existing = self.get_by_username(username)
        if existing:
            if existing["VaiTro"] != "Admin":
                raise ValueError(
                    "Tên ADMIN_USER đã thuộc tài khoản Driver; không tự nâng quyền."
                )
            return int(existing["MaND"])
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO dbo.TaiKhoan
                    (TenDangNhap, MatKhau, HoTen, VaiTro)
                OUTPUT INSERTED.MaND
                VALUES (?, ?, ?, N'Admin')
                """,
                username,
                password_hash,
                full_name,
            )
            return int(cursor.fetchone()[0])


def _default_connection():
    from db.connection import get_connection

    return get_connection()

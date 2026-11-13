"""Parameterized Admin dashboard and account-lock operations."""

from services._database import row_as_dict, rows_as_dicts, transaction


class AdminActionError(ValueError):
    """Raised when a requested account-lock action is not allowed."""


class AccountNotFoundError(AdminActionError):
    """Raised when the target account does not exist."""


class AdminService:
    def __init__(self, connection_factory=None):
        self._connection_factory = connection_factory or _default_connection

    def get_dashboard(self) -> dict:
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM dbo.TaiKhoan) AS TotalAccounts,
                    (SELECT COUNT(*) FROM dbo.PhienGiamSat) AS TotalSessions,
                    (SELECT COUNT(*) FROM dbo.LichSuCanhBao) AS TotalAlerts,
                    (SELECT COUNT(*) FROM dbo.LichSuCanhBao
                     WHERE MucCanhBao = 1) AS Level1Alerts,
                    (SELECT COUNT(*) FROM dbo.LichSuCanhBao
                     WHERE MucCanhBao = 2) AS Level2Alerts,
                    (SELECT COUNT(*) FROM dbo.LichSuCanhBao
                     WHERE MucCanhBao = 3) AS Level3Alerts
                """
            )
            summary = row_as_dict(cursor, cursor.fetchone())
            cursor.execute(
                """
                SELECT MaND, TenDangNhap, HoTen, SoDienThoai, VaiTro, BiKhoa
                FROM dbo.TaiKhoan
                ORDER BY MaND
                """
            )
            accounts = rows_as_dicts(cursor, cursor.fetchall())
        return {
            "total_accounts": summary["TotalAccounts"],
            "total_sessions": summary["TotalSessions"],
            "total_alerts": summary["TotalAlerts"],
            "alerts_by_level": {
                1: summary["Level1Alerts"],
                2: summary["Level2Alerts"],
                3: summary["Level3Alerts"],
            },
            "accounts": accounts,
        }

    def set_account_locked(
        self, user_id: int, locked: bool, current_admin_id: int
    ) -> None:
        if not isinstance(locked, bool):
            raise ValueError("locked must be a boolean.")
        with transaction(self._connection_factory) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT VaiTro, BiKhoa
                FROM dbo.TaiKhoan WITH (UPDLOCK, HOLDLOCK)
                WHERE MaND = ?
                """,
                user_id,
            )
            account = cursor.fetchone()
            if account is None:
                raise AccountNotFoundError("Không tìm thấy tài khoản.")
            role, currently_locked = account
            if not locked or currently_locked:
                cursor.execute(
                    "UPDATE dbo.TaiKhoan SET BiKhoa = ? WHERE MaND = ?",
                    locked,
                    user_id,
                )
                return
            if role == "Admin":
                if user_id == current_admin_id:
                    raise AdminActionError("Không thể khóa tài khoản Admin hiện tại.")
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM dbo.TaiKhoan WITH (UPDLOCK, HOLDLOCK)
                    WHERE VaiTro = N'Admin' AND BiKhoa = 0
                    """
                )
                if int(cursor.fetchone()[0]) <= 1:
                    raise AdminActionError(
                        "Không thể khóa Admin cuối cùng còn hoạt động."
                    )
            cursor.execute(
                "UPDATE dbo.TaiKhoan SET BiKhoa = ? WHERE MaND = ?",
                locked,
                user_id,
            )


def _default_connection():
    from db.connection import get_connection

    return get_connection()

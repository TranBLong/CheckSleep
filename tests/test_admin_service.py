import pytest

from services.admin_service import (
    AccountNotFoundError,
    AdminActionError,
    AdminService,
)


class FakeCursor:
    def __init__(self, account=("Driver", False), active_admins=2):
        self.account = account
        self.active_admins = active_admins
        self.executions = []
        self.description = []
        self.query = ""

    def execute(self, query, *params):
        self.query = query
        self.executions.append((query, params))
        if "AS TotalAccounts" in query:
            self.description = [
                ("TotalAccounts",),
                ("TotalSessions",),
                ("TotalAlerts",),
                ("Level1Alerts",),
                ("Level2Alerts",),
                ("Level3Alerts",),
            ]
        elif "SELECT MaND, TenDangNhap" in query:
            self.description = [
                ("MaND",),
                ("TenDangNhap",),
                ("HoTen",),
                ("SoDienThoai",),
                ("VaiTro",),
                ("BiKhoa",),
            ]
        return self

    def fetchone(self):
        if "AS TotalAccounts" in self.query:
            return (4, 3, 7, 2, 3, 2)
        if "SELECT VaiTro, BiKhoa" in self.query:
            return self.account
        if "SELECT COUNT(*)" in self.query:
            return (self.active_admins,)
        return None

    def fetchall(self):
        return [(1, "driver", "Tài xế", None, "Driver", False)]


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _service(cursor):
    connection = FakeConnection(cursor)
    return AdminService(lambda: connection), connection


def test_dashboard_returns_totals_and_account_rows():
    cursor = FakeCursor()
    service, connection = _service(cursor)

    dashboard = service.get_dashboard()

    assert dashboard["total_accounts"] == 4
    assert dashboard["total_sessions"] == 3
    assert dashboard["total_alerts"] == 7
    assert dashboard["alerts_by_level"] == {1: 2, 2: 3, 3: 2}
    assert dashboard["accounts"][0]["TenDangNhap"] == "driver"
    assert connection.closed


def test_account_lock_query_uses_bound_parameters():
    cursor = FakeCursor()
    service, _ = _service(cursor)

    service.set_account_locked(7, True, current_admin_id=9)

    assert cursor.executions[-1][1] == (True, 7)
    assert "SET BiKhoa = ?" in cursor.executions[-1][0]


def test_cannot_lock_current_or_last_active_admin():
    self_cursor = FakeCursor(account=("Admin", False))
    self_service, _ = _service(self_cursor)
    with pytest.raises(AdminActionError, match="hiện tại"):
        self_service.set_account_locked(9, True, current_admin_id=9)

    last_admin_cursor = FakeCursor(account=("Admin", False), active_admins=1)
    last_admin_service, _ = _service(last_admin_cursor)
    with pytest.raises(AdminActionError, match="cuối cùng"):
        last_admin_service.set_account_locked(9, True, current_admin_id=10)


def test_missing_account_has_specific_error():
    cursor = FakeCursor(account=None)
    service, _ = _service(cursor)

    with pytest.raises(AccountNotFoundError):
        service.set_account_locked(99, True, current_admin_id=10)

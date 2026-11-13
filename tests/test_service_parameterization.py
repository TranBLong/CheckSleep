from services.user_service import UserService


class FakeCursor:
    description = []

    def __init__(self):
        self.statement = None
        self.parameters = None

    def execute(self, statement, *parameters):
        self.statement = statement
        self.parameters = parameters

    def fetchone(self):
        return None


class FakeConnection:
    def __init__(self):
        self.result_cursor = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def close(self):
        pass

    def cursor(self):
        return self.result_cursor


def test_login_lookup_keeps_sql_injection_input_as_a_parameter():
    connection = FakeConnection()
    users = UserService(connection_factory=lambda: connection)
    injected_username = "' OR 1=1 --"

    result = users.get_by_username(injected_username)

    assert result is None
    assert "WHERE TenDangNhap = ?" in connection.result_cursor.statement
    assert connection.result_cursor.parameters == (injected_username,)

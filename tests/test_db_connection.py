import pyodbc

from db.connection import get_connection


def test_connection_uses_trusted_auth_without_user_credentials(monkeypatch):
    monkeypatch.setenv("DB_SERVER", "localhost")
    monkeypatch.setenv("DB_NAME", "LocalDb")
    monkeypatch.setenv("DB_TRUSTED", "yes")
    monkeypatch.setenv("DB_USER", "")
    monkeypatch.setenv("DB_PASSWORD", "")
    monkeypatch.setattr(pyodbc, "drivers", lambda: ["ODBC Driver 18 for SQL Server"])
    monkeypatch.setattr(
        pyodbc,
        "connect",
        lambda connection_string, timeout: connection_string,
    )

    connection_string = get_connection()

    assert "Trusted_Connection=yes" in connection_string
    assert "UID=" not in connection_string
    assert "PWD=" not in connection_string


def test_connection_escapes_odbc_values(monkeypatch):
    monkeypatch.setenv("DB_SERVER", "localhost")
    monkeypatch.setenv("DB_NAME", "LocalDb")
    monkeypatch.setenv("DB_USER", "app-user")
    monkeypatch.setenv("DB_PASSWORD", "test}password;")
    monkeypatch.setenv("DB_TRUSTED", "no")
    monkeypatch.setattr(pyodbc, "drivers", lambda: ["ODBC Driver 18 for SQL Server"])
    monkeypatch.setattr(
        pyodbc,
        "connect",
        lambda connection_string, timeout: connection_string,
    )

    connection_string = get_connection()

    assert "UID={app-user}" in connection_string
    assert "PWD={test}}password;}" in connection_string
    assert "DATABASE={LocalDb}" in connection_string

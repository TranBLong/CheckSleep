"""Create SQL Server connections from the application or test environment."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class DatabaseError(RuntimeError):
    """Raised when SQL Server cannot be configured or accessed."""


class DatabaseConfigurationError(DatabaseError):
    """Raised when SQL Server connection settings are incomplete."""


def _connection_value(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def get_connection(prefix: str = "DB_"):
    """Connect only with the explicitly selected environment-variable prefix."""
    server = os.getenv(f"{prefix}SERVER")
    database = os.getenv(f"{prefix}NAME")
    if not server or not database:
        raise DatabaseConfigurationError(
            f"Thiếu {prefix}SERVER hoặc {prefix}NAME trong cấu hình."
        )

    trusted = os.getenv(f"{prefix}TRUSTED", "").strip().lower() in {
        "yes",
        "true",
        "1",
    }
    username = os.getenv(f"{prefix}USER")
    password = os.getenv(f"{prefix}PASSWORD")
    if not trusted and (not username or not password):
        raise DatabaseConfigurationError(
            f"Cần {prefix}USER/{prefix}PASSWORD hoặc {prefix}TRUSTED=yes."
        )

    import pyodbc

    requested_driver = os.getenv(f"{prefix}DRIVER")
    installed_drivers = pyodbc.drivers()
    if requested_driver:
        if requested_driver not in installed_drivers:
            raise DatabaseConfigurationError(
                f"Không tìm thấy ODBC driver '{requested_driver}'."
            )
        driver = requested_driver
    else:
        driver = next(
            (
                candidate
                for candidate in (
                    "ODBC Driver 18 for SQL Server",
                    "ODBC Driver 17 for SQL Server",
                )
                if candidate in installed_drivers
            ),
            None,
        )
        if driver is None:
            raise DatabaseConfigurationError(
                "Cần cài ODBC Driver 17 hoặc 18 for SQL Server."
            )

    parts = [
        f"DRIVER={_connection_value(driver)}",
        f"SERVER={_connection_value(server)}",
        f"DATABASE={_connection_value(database)}",
        "Encrypt=yes",
        "TrustServerCertificate="
        + (
            "yes"
            if os.getenv(f"{prefix}TRUST_SERVER_CERTIFICATE", "").lower() == "yes"
            else "no"
        ),
    ]
    if trusted:
        parts.append("Trusted_Connection=yes")
    else:
        parts.extend(
            (
                f"UID={_connection_value(username)}",
                f"PWD={_connection_value(password)}",
            )
        )
    try:
        return pyodbc.connect(";".join(parts) + ";", timeout=5)
    except pyodbc.Error as exc:
        raise DatabaseError(
            "Không thể kết nối SQL Server theo cấu hình hiện tại."
        ) from exc


def get_test_connection():
    """Connect only to an explicitly named database whose name marks it as test."""
    database = os.getenv("TEST_DB_NAME")
    if not database or "test" not in database.casefold():
        raise DatabaseConfigurationError(
            "TEST_DB_NAME phải được cấu hình riêng và có chữ 'test'."
        )
    application_database = os.getenv("DB_NAME")
    if (
        application_database
        and database.casefold() == application_database.casefold()
    ):
        raise DatabaseConfigurationError(
            "TEST_DB_NAME không được trùng DB_NAME của ứng dụng."
        )
    return get_connection("TEST_DB_")

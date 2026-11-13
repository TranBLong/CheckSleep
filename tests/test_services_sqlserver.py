import os
import re
import uuid
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from db.connection import DatabaseConfigurationError, get_test_connection
from services.alert_service import AlertService
from services.config_service import ConfigService
from services.session_service import SessionService
from services.user_service import UserService


@pytest.fixture(scope="session")
def sql_services():
    if not os.getenv("TEST_DB_NAME"):
        pytest.skip("Set TEST_DB_* to use a dedicated SQL Server test database.")
    if "test" not in os.environ["TEST_DB_NAME"].casefold():
        pytest.fail("TEST_DB_NAME must identify a dedicated test database.")

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
        "configs": ConfigService(connection_factory=get_test_connection),
        "sessions": SessionService(connection_factory=get_test_connection),
        "alerts": AlertService(connection_factory=get_test_connection),
    }


def _new_driver(services):
    username = f"test_{uuid.uuid4().hex[:20]}"
    password = "test-only-password"
    user_id = services["users"].create_driver(
        username,
        generate_password_hash(password),
        "SQL Server test user",
    )
    return username, password, user_id


def test_driver_registration_hashes_password_and_creates_default_config(sql_services):
    username, password, user_id = _new_driver(sql_services)

    account = sql_services["users"].get_by_username(username)
    config = sql_services["configs"].get_for_user(user_id)

    assert account["VaiTro"] == "Driver"
    assert account["MatKhau"] != password
    assert check_password_hash(account["MatKhau"], password)
    assert config["NguongEAR"] > 0
    assert config["LuuHinhMinhHoa"] in (False, 0)


def test_session_alert_and_summary_are_persisted_in_test_database(sql_services):
    _, _, user_id = _new_driver(sql_services)
    session_id = sql_services["sessions"].start_session(user_id)

    sql_services["alerts"].record_alert(
        session_id=session_id,
        level=1,
        state="FATIGUED",
        ear=0.2,
        mar=0.4,
        perclos=10.0,
        pitch=1.5,
        confidence=0.9,
    )
    sql_services["sessions"].end_session(
        session_id,
        state="FATIGUED",
        calibration={"ear0": 0.3, "mar0": 0.1, "pitch0": 2.0},
    )

    session = sql_services["sessions"].get_for_user(session_id, user_id)
    alerts = sql_services["alerts"].list_for_user_session(session_id, user_id)

    assert session["ThoiGianKetThuc"] is not None
    assert session["SoLanCanhBao"] == 1
    assert session["EAR0"] == pytest.approx(0.3)
    assert len(alerts) == 1
    assert alerts[0]["MucCanhBao"] == 1


def test_history_queries_do_not_return_other_users_sessions(sql_services):
    _, _, first_user_id = _new_driver(sql_services)
    _, _, other_user_id = _new_driver(sql_services)
    session_id = sql_services["sessions"].start_session(first_user_id)

    assert sql_services["sessions"].get_for_user(session_id, other_user_id) is None


def test_admin_seed_creates_an_admin_without_driver_configuration(sql_services):
    username = f"admin_{uuid.uuid4().hex[:20]}"
    admin_id = sql_services["users"].seed_admin(
        username,
        generate_password_hash("test-only-admin-password"),
    )

    account = sql_services["users"].get_by_id(admin_id)

    assert account["VaiTro"] == "Admin"
    assert sql_services["configs"].get_for_user(admin_id) is None


def test_test_connection_refuses_application_database(monkeypatch):
    monkeypatch.setenv("TEST_DB_NAME", "Local_Test")
    monkeypatch.setenv("DB_NAME", "local_test")

    with pytest.raises(DatabaseConfigurationError):
        get_test_connection()


def test_login_rejects_sql_injection_string_in_dedicated_test_database(sql_services):
    username, password, _ = _new_driver(sql_services)
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key-only",
            "USER_SERVICE": sql_services["users"],
            "SESSION_SERVICE": sql_services["sessions"],
            "ALERT_SERVICE": sql_services["alerts"],
            "MONITOR_PIPELINE_FACTORY": lambda: object(),
        }
    )
    client = app.test_client()

    injected = client.post(
        "/login",
        data={"username": "' OR 1=1 --", "password": password},
    )
    valid = client.post(
        "/login",
        data={"username": username, "password": password},
    )

    assert injected.status_code == 401
    assert (
        "Tên đăng nhập hoặc mật khẩu không đúng."
        in injected.get_data(as_text=True)
    )
    assert valid.status_code == 302

from app import create_app
from services.admin_service import AdminActionError
from werkzeug.security import generate_password_hash


def test_app_initializes_and_renders_home_page():
    app = create_app()
    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"DrowsyGuard" in response.data


class FakePipeline:
    def __init__(self):
        self.status = {
            "session_started": False,
            "running": False,
            "state": "UNKNOWN",
            "state_label": "Không xác định",
            "alert_level": None,
            "error": None,
        }

    def start(self, session_id=None):
        self.status.update(session_started=True, running=True)
        return True

    def stop(self):
        self.status["running"] = False
        return True

    def snapshot(self):
        return dict(self.status)

    def acknowledge(self):
        return dict(self.status)

    def frame_snapshot(self):
        return 0, None, None

    def encode_frame(self, overlay=False):
        return None


class FakeUserService:
    def __init__(self):
        self.users = {
            1: {
                "MaND": 1,
                "TenDangNhap": "driver",
                "MatKhau": generate_password_hash("any"),
                "HoTen": "Tài xế",
                "VaiTro": "Driver",
            },
            2: {
                "MaND": 2,
                "TenDangNhap": "other",
                "MatKhau": generate_password_hash("any"),
                "HoTen": "Người khác",
                "VaiTro": "Driver",
                "BiKhoa": False,
            },
            3: {
                "MaND": 3,
                "TenDangNhap": "admin",
                "MatKhau": generate_password_hash("any"),
                "HoTen": "Quản trị",
                "VaiTro": "Admin",
                "BiKhoa": False,
            },
        }

    def get_by_id(self, user_id):
        return self.users.get(user_id)

    def get_by_username(self, username):
        return next(
            (user for user in self.users.values() if user["TenDangNhap"] == username),
            None,
        )


class FakeSessionService:
    def start_session(self, user_id):
        return 17

    def end_session(self, session_id, state, calibration=None):
        pass

    def list_for_user(self, user_id):
        return []

    def get_for_user(self, session_id, user_id):
        return None


class FakeAlertService:
    def list_for_user_session(self, session_id, user_id):
        return []


class FakeAdminService:
    def __init__(self, users):
        self.users = users

    def get_dashboard(self):
        accounts = []
        for user in self.users.users.values():
            accounts.append(
                {
                    "MaND": user["MaND"],
                    "TenDangNhap": user["TenDangNhap"],
                    "HoTen": user["HoTen"],
                    "SoDienThoai": user.get("SoDienThoai"),
                    "VaiTro": user["VaiTro"],
                    "BiKhoa": user.get("BiKhoa", False),
                }
            )
        return {
            "total_accounts": len(accounts),
            "total_sessions": 3,
            "total_alerts": 6,
            "alerts_by_level": {1: 1, 2: 2, 3: 3},
            "accounts": accounts,
        }

    def set_account_locked(self, user_id, locked, current_admin_id):
        if user_id == current_admin_id and locked:
            raise AdminActionError("Không thể khóa tài khoản Admin hiện tại.")
        if user_id not in self.users.users:
            raise AdminActionError("Không tìm thấy tài khoản.")
        self.users.users[user_id]["BiKhoa"] = locked


def _authenticated_app(pipeline_factory=FakePipeline):
    users = FakeUserService()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key-only",
            "MONITOR_PIPELINE_FACTORY": pipeline_factory,
            "USER_SERVICE": users,
            "SESSION_SERVICE": FakeSessionService(),
            "ALERT_SERVICE": FakeAlertService(),
            "ADMIN_SERVICE": FakeAdminService(users),
        }
    )
    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "driver", "password": "any"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return app, client


def _authenticated_admin_app():
    users = FakeUserService()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key-only",
            "MONITOR_PIPELINE_FACTORY": FakePipeline,
            "USER_SERVICE": users,
            "SESSION_SERVICE": FakeSessionService(),
            "ALERT_SERVICE": FakeAlertService(),
            "ADMIN_SERVICE": FakeAdminService(users),
        }
    )
    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "admin", "password": "any"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return app, client


def test_admin_dashboard_forbidden_to_driver_and_available_to_admin():
    app, driver = _authenticated_app()
    assert driver.get("/admin").status_code == 403

    app, admin = _authenticated_admin_app()
    response = admin.get("/admin")

    assert response.status_code == 200
    assert "Tổng tài khoản".encode() in response.data
    assert "Cảnh báo mức 3".encode() in response.data
    assert "Quản trị".encode() in response.data


def test_locking_account_blocks_future_login_and_invalidates_existing_session():
    app, admin = _authenticated_admin_app()
    driver = app.test_client()
    assert driver.post(
        "/login", data={"username": "driver", "password": "any"}
    ).status_code == 302

    response = admin.post("/admin/accounts/1/lock")

    assert response.status_code == 302
    assert driver.get("/history").status_code == 302
    assert (
        driver.post("/login", data={"username": "driver", "password": "any"}).status_code
        == 403
    )


def test_admin_cannot_lock_own_account():
    _app, admin = _authenticated_admin_app()

    response = admin.post("/admin/accounts/3/lock", follow_redirects=True)

    assert response.status_code == 200
    assert "Không thể khóa tài khoản Admin hiện tại".encode() in response.data


def test_monitor_shows_privacy_notice_without_starting_pipeline():
    app, client = _authenticated_app()

    response = client.get("/monitor")
    status = client.get("/api/status").get_json()

    assert response.status_code == 200
    assert "Video không được lưu".encode() in response.data
    assert status["session_started"] is False
    assert status["running"] is False


def test_monitor_api_starts_stops_and_acknowledges():
    app, client = _authenticated_app()

    assert client.post("/api/start").status_code == 400
    assert client.post("/api/start", json={"consent": True}).status_code == 202
    assert client.post("/api/ack").status_code == 200
    response = client.post("/api/stop")

    assert response.status_code == 200
    assert response.get_json()["running"] is False


def test_monitor_api_rejects_another_authenticated_user():
    app, owner_client = _authenticated_app()
    other_client = app.test_client()
    login_response = other_client.post(
        "/login",
        data={"username": "other", "password": "any"},
    )
    assert login_response.status_code == 302
    assert owner_client.post(
        "/api/start", json={"consent": True}
    ).status_code == 202

    assert other_client.get("/api/status").status_code == 403
    assert other_client.post("/api/stop").status_code == 403
    assert other_client.post("/api/ack").status_code == 403
    assert other_client.get("/video_feed").status_code == 403


def test_video_feed_streams_jpeg_with_requested_overlay():
    class StreamingPipeline(FakePipeline):
        def __init__(self):
            super().__init__()
            self.status.update(session_started=True, running=True)
            self.overlay_requested = None

        def frame_snapshot(self):
            return 1, object(), None

        def encode_frame(self, overlay=False):
            self.overlay_requested = overlay
            self.status["running"] = False
            return b"jpeg-data"

    app, client = _authenticated_app(StreamingPipeline)
    pipeline = app.extensions["drowsyguard_pipeline"]
    assert client.post("/api/start", json={"consent": True}).status_code == 202

    response = client.get("/video_feed?overlay=1")

    assert response.status_code == 200
    assert response.mimetype == "multipart/x-mixed-replace"
    assert b"Content-Type: image/jpeg" in response.data
    assert b"jpeg-data" in response.data
    assert pipeline.overlay_requested is True

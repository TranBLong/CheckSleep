import os
import secrets

import click
from threading import Lock

from flask import Flask, jsonify, render_template, request
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

from core.pipeline import DieuKhienGiamSat
from db.connection import DatabaseError
from services.alert_service import AlertService
from services.admin_service import AdminService
from services.session_service import SessionService
from services.user_service import UserService


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    if test_config:
        app.config.update(test_config)

    users = app.config.get("USER_SERVICE") or UserService()
    sessions = app.config.get("SESSION_SERVICE") or SessionService()
    alerts = app.config.get("ALERT_SERVICE") or AlertService()
    admins = app.config.get("ADMIN_SERVICE") or AdminService()
    app.extensions["drowsyguard_user_service"] = users
    app.extensions["drowsyguard_session_service"] = sessions
    app.extensions["drowsyguard_alert_service"] = alerts
    app.extensions["drowsyguard_admin_service"] = admins

    login_manager = LoginManager()

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user = users.get_by_id(int(user_id))
        except ValueError:
            return None
        if user is None or user.get("BiKhoa", False):
            return None
        from app.auth import UserAccount

        return UserAccount(user)

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import jsonify, redirect, request, url_for

        if request.path.startswith("/api/") or request.path == "/video_feed":
            return jsonify(error="Vui lòng đăng nhập để tiếp tục."), 401
        return redirect(url_for("auth.login", next=request.url))

    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    def persist_alert(session_id, event):
        alerts.record_alert(session_id=session_id, **event)

    def finish_session(session_id, summary):
        try:
            sessions.end_session(
                session_id,
                state=summary["state"],
                calibration=summary["calibration"],
            )
        finally:
            with owner["lock"]:
                if owner["session_id"] == session_id:
                    owner["active"] = False

    owner = {
        "lock": Lock(),
        "user_id": None,
        "session_id": None,
        "active": False,
    }
    app.extensions["drowsyguard_monitor_owner"] = owner
    pipeline_factory = app.config.get("MONITOR_PIPELINE_FACTORY")
    if pipeline_factory is None:
        pipeline = DieuKhienGiamSat(
            on_alert=persist_alert,
            on_session_end=finish_session,
        )
    else:
        pipeline = pipeline_factory()
    app.extensions["drowsyguard_pipeline"] = pipeline

    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.history import history_bp
    from app.monitor import monitor_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(monitor_bp)

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.errorhandler(DatabaseError)
    def database_error(_error):
        message = "Lỗi cơ sở dữ liệu. Kiểm tra SQL Server/cấu hình rồi thử lại."
        if request.path.startswith("/api/"):
            return jsonify(error=message), 503
        return render_template("database_error.html", message=message), 503

    @app.cli.command("seed-admin")
    def seed_admin():
        """Create the initial Admin account from ADMIN_USER/ADMIN_PASSWORD."""
        username = os.getenv("ADMIN_USER")
        password = os.getenv("ADMIN_PASSWORD")
        if not username or not password:
            raise click.ClickException(
                "Hãy cấu hình ADMIN_USER và ADMIN_PASSWORD trong .env."
            )
        if len(password) < 12:
            raise click.ClickException(
                "ADMIN_PASSWORD cần có ít nhất 12 ký tự."
            )
        try:
            users.seed_admin(username, generate_password_hash(password))
        except (DatabaseError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Đã bảo đảm tài khoản Admin '{username}' tồn tại.")

    return app

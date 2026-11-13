from flask import Blueprint, current_app, render_template
from flask_login import current_user, login_required

from db.connection import DatabaseError

history_bp = Blueprint("history", __name__)


def _sessions():
    return current_app.extensions["drowsyguard_session_service"]


def _alerts():
    return current_app.extensions["drowsyguard_alert_service"]


@history_bp.get("/history")
@login_required
def history():
    try:
        sessions = _sessions().list_for_user(int(current_user.id))
    except DatabaseError:
        return (
            render_template(
                "history.html",
                sessions=[],
                error="Không tải được lịch sử từ cơ sở dữ liệu. Hãy thử tải lại.",
            ),
            503,
        )
    return render_template("history.html", sessions=sessions, error=None)


@history_bp.get("/history/<int:session_id>")
@login_required
def history_detail(session_id: int):
    try:
        session = _sessions().get_for_user(
            session_id,
            int(current_user.id),
        )
    except DatabaseError:
        return (
            render_template(
                "history_detail.html",
                session=None,
                error="Không tải được phiên từ cơ sở dữ liệu. Hãy thử lại.",
            ),
            503,
        )
    if session is None:
        return (
            render_template(
                "history_detail.html",
                session=None,
                error="Không tìm thấy phiên giám sát.",
            ),
            404,
        )
    try:
        alerts = _alerts().list_for_user_session(
            session_id,
            int(current_user.id),
        )
    except DatabaseError:
        return (
            render_template(
                "history_detail.html",
                session=session,
                alerts=[],
                error="Không tải được cảnh báo. Hãy thử lại.",
            ),
            503,
        )
    return render_template(
        "history_detail.html",
        session=session,
        alerts=alerts,
        error=None,
    )

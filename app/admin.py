from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    url_for,
)
from flask_login import current_user, login_required

from db.connection import DatabaseError
from services.admin_service import AdminActionError

admin_bp = Blueprint("admin", __name__)


def _admins():
    return current_app.extensions["drowsyguard_admin_service"]


@admin_bp.before_request
@login_required
def require_admin():
    if current_user.role != "Admin":
        abort(403)


@admin_bp.get("/admin")
def dashboard():
    try:
        dashboard_data = _admins().get_dashboard()
    except DatabaseError:
        return (
            render_template(
                "admin.html",
                dashboard=None,
                error="Không tải được thống kê. Hãy kiểm tra cơ sở dữ liệu rồi thử lại.",
            ),
            503,
        )
    return render_template("admin.html", dashboard=dashboard_data, error=None)


@admin_bp.post("/admin/accounts/<int:user_id>/<action>")
def change_account_lock(user_id: int, action: str):
    if action not in {"lock", "unlock"}:
        abort(404)
    try:
        _admins().set_account_locked(
            user_id,
            locked=action == "lock",
            current_admin_id=int(current_user.id),
        )
    except AdminActionError as exc:
        flash(str(exc), "error")
    except DatabaseError:
        flash("Không thể cập nhật tài khoản do lỗi cơ sở dữ liệu.", "error")
    else:
        flash(
            "Đã khóa tài khoản." if action == "lock" else "Đã mở khóa tài khoản.",
            "success",
        )
    return redirect(url_for("admin.dashboard"))

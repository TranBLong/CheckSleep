from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import UserMixin, current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from db.connection import DatabaseError

auth_bp = Blueprint("auth", __name__)


class UserAccount(UserMixin):
    def __init__(self, record: dict):
        self.id = str(record["MaND"])
        self.username = record["TenDangNhap"]
        self.full_name = record["HoTen"]
        self.role = record["VaiTro"]
        self._is_active = not record.get("BiKhoa", False)

    @property
    def is_active(self):
        return self._is_active


def _users():
    return current_app.extensions["drowsyguard_user_service"]


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("monitor.monitor"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            account = _users().get_by_username(username)
        except DatabaseError:
            flash(
                "Không kết nối được cơ sở dữ liệu. Hãy kiểm tra cấu hình và thử lại.",
                "error",
            )
            return render_template("login.html"), 503
        if account is None or not check_password_hash(account["MatKhau"], password):
            flash("Tên đăng nhập hoặc mật khẩu không đúng.", "error")
            return render_template("login.html"), 401
        if account.get("BiKhoa", False):
            flash("Tài khoản đã bị khóa. Hãy liên hệ quản trị viên.", "error")
            return render_template("login.html"), 403
        login_user(UserAccount(account))
        destination = request.args.get("next", "")
        if destination.startswith("/") and not destination.startswith("//"):
            return redirect(destination)
        return redirect(url_for("monitor.monitor"))
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("monitor.monitor"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip() or None
        password = request.form.get("password", "")
        if not username or not full_name or len(password) < 8:
            flash(
                "Nhập tên đăng nhập, họ tên và mật khẩu tối thiểu 8 ký tự.",
                "error",
            )
            return render_template("register.html"), 400
        try:
            if _users().get_by_username(username) is not None:
                flash("Tên đăng nhập đã được sử dụng.", "error")
                return render_template("register.html"), 409
            _users().create_driver(
                username,
                generate_password_hash(password),
                full_name,
                phone,
            )
        except DatabaseError:
            flash(
                "Không thể tạo tài khoản do lỗi cơ sở dữ liệu. Hãy thử lại.",
                "error",
            )
            return render_template("register.html"), 503
        flash("Đăng ký thành công. Hãy đăng nhập để tiếp tục.", "success")
        return redirect(url_for("auth.login"))
    return render_template("register.html")


@auth_bp.get("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("auth.login"))

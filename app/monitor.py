from flask import Blueprint, Response, current_app, jsonify, request
from flask_login import current_user, login_required
from time import sleep

from config import CALIBRATION_DURATION_SECONDS
from db.connection import DatabaseError

monitor_bp = Blueprint("monitor", __name__)


def _pipeline():
    return current_app.extensions["drowsyguard_pipeline"]


def _sessions():
    return current_app.extensions["drowsyguard_session_service"]


def _owner():
    return current_app.extensions["drowsyguard_monitor_owner"]


def _is_session_owner(require_active=False):
    owner = _owner()
    with owner["lock"]:
        return (
            owner["user_id"] == int(current_user.id)
            and (not require_active or owner["active"])
        )


@monitor_bp.get("/monitor")
@login_required
def monitor():
    from flask import render_template

    return render_template("monitor.html")


@monitor_bp.post("/api/start")
@login_required
def start_monitor():
    consent = request.get_json(silent=True)
    if not isinstance(consent, dict) or consent.get("consent") is not True:
        return (
            jsonify(
                error="Để bật camera, vui lòng xác nhận thông báo quyền riêng tư."
            ),
            400,
        )
    owner = _owner()
    with owner["lock"]:
        if owner["active"]:
            return jsonify(error="Một phiên giám sát khác đang chạy."), 409
        owner["user_id"] = int(current_user.id)
        owner["session_id"] = None
        owner["active"] = True
    try:
        session_id = _sessions().start_session(int(current_user.id))
    except DatabaseError:
        with owner["lock"]:
            owner["user_id"] = None
            owner["session_id"] = None
            owner["active"] = False
        return jsonify(error="Không thể tạo phiên trong cơ sở dữ liệu."), 503
    with owner["lock"]:
        owner["session_id"] = session_id
    try:
        started = _pipeline().start(session_id=session_id)
    except RuntimeError as exc:
        with owner["lock"]:
            owner["user_id"] = None
            owner["session_id"] = None
            owner["active"] = False
        _sessions().end_session(session_id, state="UNKNOWN")
        return jsonify(error=f"Không thể khởi động pipeline: {exc}"), 500
    if not started:
        with owner["lock"]:
            owner["user_id"] = None
            owner["session_id"] = None
            owner["active"] = False
        _sessions().end_session(session_id, state="UNKNOWN")
        return jsonify(error="Một phiên giám sát khác đang chạy."), 409
    return jsonify(_pipeline().snapshot()), 202


@monitor_bp.post("/api/stop")
@login_required
def stop_monitor():
    if not _is_session_owner(require_active=True):
        return jsonify(error="Bạn không sở hữu phiên giám sát hiện tại."), 403
    stopped = _pipeline().stop()
    status = _pipeline().snapshot()
    status["stopped"] = stopped
    return jsonify(status), 200 if stopped else 202


@monitor_bp.get("/api/status")
@login_required
def monitor_status():
    owner = _owner()
    with owner["lock"]:
        active_user_id = owner["user_id"]
        is_active = owner["active"]
    if is_active and active_user_id != int(current_user.id):
        return jsonify(error="Phiên giám sát thuộc tài khoản khác."), 403
    if active_user_id is None or (
        not is_active and active_user_id != int(current_user.id)
    ):
        return jsonify(
            session_started=False,
            running=False,
            state="UNKNOWN",
            state_label="Không xác định",
            alert_level=None,
            alert_sound_enabled=False,
            alert_acknowledged=False,
            alert_sequence=0,
            ear=None,
            mar=None,
            perclos=None,
            pitch=None,
            fps=0.0,
            calibrating=False,
            calibration_remaining=CALIBRATION_DURATION_SECONDS,
            calibration=None,
            partial_data=False,
            error=None,
            message="Chưa có phiên giám sát.",
        )
    return jsonify(_pipeline().snapshot())


@monitor_bp.post("/api/ack")
@login_required
def acknowledge_alert():
    if not _is_session_owner(require_active=True):
        return jsonify(error="Bạn không sở hữu phiên giám sát hiện tại."), 403
    return jsonify(_pipeline().acknowledge())


@monitor_bp.get("/video_feed")
@login_required
def video_feed():
    if not _is_session_owner(require_active=True):
        return jsonify(error="Bạn không sở hữu phiên giám sát hiện tại."), 403
    overlay = request.args.get("overlay", "0") == "1"
    pipeline = _pipeline()

    def frames():
        last_frame_id = -1
        while True:
            status = pipeline.snapshot()
            frame_id, frame, _ = pipeline.frame_snapshot()
            if frame is not None and frame_id != last_frame_id:
                image = pipeline.encode_frame(overlay=overlay)
                if image is not None:
                    last_frame_id = frame_id
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + image
                        + b"\r\n"
                    )
            elif not status["running"]:
                break
            sleep(0.02)

    return Response(
        frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

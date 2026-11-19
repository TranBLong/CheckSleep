"""Ngưỡng khởi điểm của DrowsyGuard; cần hiệu chỉnh bằng thực nghiệm."""

from pathlib import Path

NORMAL_BLINK_MIN_DURATION_MS = 100
NORMAL_BLINK_MAX_DURATION_MS = 400

LONG_BLINK_MIN_DURATION_MS = 500
LONG_BLINK_MAX_DURATION_MS = 2_000
LONG_BLINK_FATIGUED_COUNT_MIN = 1
LONG_BLINK_FATIGUED_COUNT_MAX = 2
LONG_BLINK_DROWSY_COUNT_MIN = 3
LONG_BLINK_COUNT_WINDOW_SECONDS = 60

EYES_CLOSED_ASLEEP_DURATION_SECONDS = 2

PERCLOS_WINDOW_SECONDS = 60
PERCLOS_FATIGUED_THRESHOLD_PERCENT = 10
PERCLOS_DROWSY_THRESHOLD_PERCENT = 15
# Cửa sổ tối thiểu trước khi tin PERCLOS; cần hiệu chỉnh bằng thực nghiệm.
PERCLOS_MIN_WINDOW_SECONDS = 15

YAWN_MAR_BASELINE_MULTIPLIER = 1.4
YAWN_MIN_DURATION_SECONDS = 2
YAWN_FATIGUED_COUNT_MIN = 2
YAWN_FATIGUED_WINDOW_SECONDS = 5 * 60
YAWN_DROWSY_COUNT_MIN = 3
YAWN_DROWSY_WINDOW_SECONDS = 10 * 60
YAWN_DROWSY_REQUIRES_OTHER_SIGN = True

HEAD_NOD_PITCH_DROP_DEGREES = 15
HEAD_NOD_MIN_DURATION_SECONDS = 1
HEAD_NOD_DROWSY_COUNT_MIN = 2
HEAD_NOD_COUNT_WINDOW_SECONDS = 60
HEAD_BOW_ASLEEP_DURATION_SECONDS = 2

# Điểm mệt mỏi 0–100; giá trị khởi điểm, cần hiệu chỉnh bằng thực nghiệm.
FATIGUE_SCORE_WEIGHTS = {
    "perclos": 0.40,
    "long_blink": 0.25,
    "yawn": 0.20,
    "head_nod": 0.15,
}
FATIGUE_SCORE_SMOOTHING_ALPHA = 0.3  # làm mượt mũ; giá trị khởi điểm, cần hiệu chỉnh
# Mức tham chiếu (0 → 0, mức này → 1); lấy từ ngưỡng đã có, không lặp số cứng.
FATIGUE_SCORE_PERCLOS_REF_PERCENT = PERCLOS_DROWSY_THRESHOLD_PERCENT
FATIGUE_SCORE_LONG_BLINK_REF_COUNT = LONG_BLINK_DROWSY_COUNT_MIN
FATIGUE_SCORE_YAWN_REF_COUNT = YAWN_DROWSY_COUNT_MIN
FATIGUE_SCORE_HEAD_NOD_REF_COUNT = HEAD_NOD_DROWSY_COUNT_MIN
FATIGUE_SCORE_ASLEEP_FLOOR = 90.0  # sàn khi ASLEEP; giá trị khởi điểm, cần hiệu chỉnh

EYES_CLOSED_EAR_BASELINE_RATIO = 0.75
CALIBRATION_DURATION_SECONDS = 5
CALIBRATION_MIN_VALID_FRAMES = 30
# Khoảng EAR0 hợp lệ khởi điểm; cần hiệu chỉnh bằng thực nghiệm.
CALIBRATION_EAR0_MIN = 0.2
CALIBRATION_EAR0_MAX = 0.4
METRICS_SMOOTHING_FRAME_COUNT = 15
STATE_DEESCALATION_NORMAL_DURATION_SECONDS = 30
FACE_TRACKING_LOSS_UNKNOWN_SECONDS = 3
ALERT_REPEAT_COOLDOWN_SECONDS = 10
ALERT_ACKNOWLEDGEMENT_SNOOZE_SECONDS = 10
DEFAULT_ALERT_TYPE = "audio"
DEFAULT_SAVE_EVIDENCE = False
DEFAULT_DRIVER_CONFIG = {
    "NguongEAR": EYES_CLOSED_EAR_BASELINE_RATIO,
    "NguongMAR": YAWN_MAR_BASELINE_MULTIPLIER,
    "NguongPERCLOS": PERCLOS_FATIGUED_THRESHOLD_PERCENT,
    "NguongGatPitch": HEAD_NOD_PITCH_DROP_DEGREES,
    "SoKhungHinhLienTiep": METRICS_SMOOTHING_FRAME_COUNT,
    "ThoiGianHaMuc": STATE_DEESCALATION_NORMAL_DURATION_SECONDS,
    "LoaiCanhBao": DEFAULT_ALERT_TYPE,
    "LuuHinhMinhHoa": DEFAULT_SAVE_EVIDENCE,
}

CAMERA_INDEX = 0
DEMO_CONSOLE_INTERVAL_SECONDS = 1.0
# Tự dừng phiên nếu /api/status không được gọi (tab đóng, mất mạng).
CLIENT_HEARTBEAT_TIMEOUT_SECONDS = 15.0
# Khoảng ghi số liệu phiên (giây); không ghi từng khung hình.
METRIC_LOG_INTERVAL_SECONDS = 1.0
METRIC_LOG_BATCH_SIZE = 5
FACE_DETECTION_MODEL_SELECTION = 0
FACE_DETECTION_MIN_CONFIDENCE = 0.5
FACE_MESH_MAX_NUM_FACES = 5
FACE_MESH_MIN_DETECTION_CONFIDENCE = 0.5
FACE_MESH_MIN_TRACKING_CONFIDENCE = 0.5

# Webcam laptop thường mặt ở giữa khung. Khi lắp camera trong xe, thu hẹp
# về nửa ghế lái, ví dụ (0.0, 0.0, 0.5, 1.0) hoặc ROI thực tế sau hiệu chỉnh.
DRIVER_SEAT_ROI = (0.0, 0.0, 1.0, 1.0)
FACE_NMS_IOU_THRESHOLD = 0.45
DRIVER_TRACKING_IOU_THRESHOLD = 0.3
DRIVER_SELECTION_CENTER_WEIGHT = 0.6
DRIVER_SELECTION_SIZE_WEIGHT = 0.4

QUALITY_MIN_BRIGHTNESS = 50.0
QUALITY_MIN_LAPLACIAN_VARIANCE = 100.0
QUALITY_CLAHE_ENABLED = False
QUALITY_CLAHE_CLIP_LIMIT = 3.0
QUALITY_CLAHE_TILE_GRID_SIZE = (8, 8)
FEATURE_MIN_BRIGHTNESS = 25.0
FEATURE_MIN_LAPLACIAN_VARIANCE = 4.0
FEATURE_ROI_PADDING_RATIO = 1.5

CLASSIFIER_MODE = "baseline"
CNN_EYE_CLOSED_THRESHOLD = 0.5
CNN_MOUTH_YAWN_THRESHOLD = 0.5
# Padding crop mắt gần với ảnh MRL (cắt sát); miệng giữ 1.5 như lúc train.
CNN_EYE_CROP_PADDING_RATIO = 0.4
EYE_TFLITE_MODEL_PATH = Path(__file__).resolve().parent / "models" / "eye_classifier.tflite"
MOUTH_TFLITE_MODEL_PATH = Path(__file__).resolve().parent / "models" / "mouth_classifier.tflite"
CNN_USE_MOUTH_MODEL = False  # Model miệng mức 2; bật khi đã có mouth_classifier.tflite

# --- Mô hình chuỗi thời gian (GRU/1D-CNN), so sánh với luật ---
SEQ_WINDOW_SECONDS = 30
SEQ_STRIDE_SECONDS = 5
SEQ_SAMPLE_HZ = 1.0
# Tỷ lệ mẫu thiếu tối đa trong cửa sổ; vượt → bỏ cửa sổ.
SEQ_MAX_MISSING_RATIO = 0.35
# Nhãn chiếm ≥ tỷ lệ này mới gán; không đủ → bỏ cửa sổ.
SEQ_MAJORITY_MIN_RATIO = 0.5
SEQ_FEATURES = (
    "ear_norm",
    "mar_norm",
    "pitch_delta",
    "perclos",
    "diem_met_moi",
    "ear_missing",
    "mar_missing",
    "pitch_missing",
    "perclos_missing",
    "diem_met_moi_missing",
)
SEQ_LABELS = ("tinh_tao", "met_moi", "buon_ngu", "ngu_gat")
# UNKNOWN bị loại khỏi nhãn huấn luyện.
SEQ_STATE_TO_LABEL = {
    "ALERT": "tinh_tao",
    "FATIGUED": "met_moi",
    "DROWSY": "buon_ngu",
    "ASLEEP": "ngu_gat",
}

"""Live webcam preview for face landmarks, EAR, and MAR; no recording."""

from pathlib import Path
from time import monotonic

import cv2

from config import (
    CAMERA_FLIP_HORIZONTAL,
    CAMERA_INDEX,
    CNN_EYE_CROP_PADDING_RATIO,
    DEMO_CONSOLE_INTERVAL_SECONDS,
)
from core.camera import QuanLyCamera
from core.classifier import extract_eye_crops
from core.face import FaceLandmarkDetector
from core.metrics import (
    INNER_MOUTH_LANDMARK_INDICES,
    LEFT_EYE_LANDMARK_INDICES,
    RIGHT_EYE_LANDMARK_INDICES,
)

LANDMARK_GROUPS = (
    LEFT_EYE_LANDMARK_INDICES,
    RIGHT_EYE_LANDMARK_INDICES,
    INNER_MOUTH_LANDMARK_INDICES,
)

# Bật/tắt hiển thị toàn bộ điểm khuôn mặt (giống Flask)
SHOW_FULL_FACE = True
SHOW_EYE_MOUTH = True  # bật/tắt đường xanh + chấm đỏ mắt/miệng


def _save_eye_crops(frame, landmarks, out_dir: Path, index: int) -> None:
    """Save local eye crops for visual inspection; files stay on this machine."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for eye_index, crop in enumerate(
        extract_eye_crops(
            frame, landmarks, padding_ratio=CNN_EYE_CROP_PADDING_RATIO
        )
    ):
        cv2.imwrite(str(out_dir / f"eye_{index:04d}_{eye_index}.png"), crop)


def _draw_landmark_groups(
    frame,
    landmarks,
    show_full_face: bool = True,
    show_eye_mouth: bool = True,
) -> None:
    """Vẽ landmarks: full face + (tuỳ chọn) mắt/miệng nổi bật."""
    height, width = frame.shape[:2]
    points = [
        (round(x * width), round(y * height))
        for x, y, *_ in landmarks
    ]

    # 1. Toàn bộ điểm Face Mesh
    if show_full_face:
        for point in points:
            cv2.circle(frame, point, 1, (0, 255, 255), -1)

    # 2. Mắt + miệng (đường xanh + chấm đỏ)
    if show_eye_mouth:
        for indices in LANDMARK_GROUPS:
            group = [
                (
                    round(landmarks[i][0] * width),
                    round(landmarks[i][1] * height),
                )
                for i in indices
            ]
            for start, end in zip(group, group[1:] + group[:1]):
                cv2.line(frame, start, end, (0, 255, 0), 1)
            for p in group:
                cv2.circle(frame, p, 2, (0, 0, 255), -1)


def main() -> None:
    global SHOW_FULL_FACE, SHOW_EYE_MOUTH
    last_console_output = 0.0
    try:
        with QuanLyCamera(CAMERA_INDEX) as camera:
            with FaceLandmarkDetector() as detector:
                while True:
                    frame = camera.read()
                    if frame is None:
                        continue
                    if CAMERA_FLIP_HORIZONTAL:
                        frame = cv2.flip(frame, 1)
                    result = detector.process(frame)
                    clean_frame = frame.copy()
                    if result.landmarks is not None:
                        _draw_landmark_groups(
                            frame,
                            result.landmarks,
                            show_full_face=SHOW_FULL_FACE,
                            show_eye_mouth=SHOW_EYE_MOUTH,
                        )
                        if result.ear is not None and result.mar is not None:
                            status = f"EAR: {result.ear:.3f}  MAR: {result.mar:.3f}"
                        else:
                            status = "Du lieu mot phan (thieu sang?)"
                    else:
                        status = "Khong phat hien khuon mat"

                    now = monotonic()
                    if now - last_console_output >= DEMO_CONSOLE_INTERVAL_SECONDS:
                        if (
                            result.has_face
                            and result.ear is not None
                            and result.mar is not None
                        ):
                            confidence_str = (
                                f"{result.confidence:.2f}"
                                if result.confidence is not None
                                else "N/A"
                            )
                            print(
                                f"EAR={result.ear:.3f} MAR={result.mar:.3f} "
                                f"confidence={confidence_str}"
                            )
                        else:
                            print(status)
                        last_console_output = now

                    cv2.putText(
                        frame,
                        status,
                        (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 0),
                        2,
                    )
                    cv2.imshow(
                        "DrowsyGuard - landmark demo (L full-face, E eye/mouth, S crop, Q thoat)",
                        frame,
                    )
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("s"), ord("S")) and result.landmarks is not None:
                        _save_eye_crops(
                            clean_frame,
                            result.landmarks,
                            Path("instance/debug_eye_crops"),
                            int(now * 1000) % 10000,
                        )
                    if key in (ord("l"), ord("L")):
                        SHOW_FULL_FACE = not SHOW_FULL_FACE
                        print(f"Full-face landmarks: {'ON' if SHOW_FULL_FACE else 'OFF'}")
                    if key in (ord("e"), ord("E")):
                        SHOW_EYE_MOUTH = not SHOW_EYE_MOUTH
                        print(f"Eye/Mouth outlines: {'ON' if SHOW_EYE_MOUTH else 'OFF'}")
                    if key in (ord("q"), ord("Q"), 27):
                        break
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

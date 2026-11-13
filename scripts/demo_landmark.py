"""Live webcam preview for face landmarks, EAR, and MAR; no recording."""

from time import monotonic

import cv2

from config import CAMERA_INDEX, DEMO_CONSOLE_INTERVAL_SECONDS
from core.camera import QuanLyCamera
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


def _draw_landmark_groups(frame, landmarks) -> None:
    height, width = frame.shape[:2]
    for indices in LANDMARK_GROUPS:
        points = [
            (
                round(landmarks[index][0] * width),
                round(landmarks[index][1] * height),
            )
            for index in indices
        ]
        for start, end in zip(points, points[1:] + points[:1]):
            cv2.line(frame, start, end, (0, 255, 0), 2)
        for point in points:
            cv2.circle(frame, point, 3, (0, 0, 255), -1)


def main() -> None:
    last_console_output = 0.0
    try:
        with QuanLyCamera(CAMERA_INDEX) as camera:
            with FaceLandmarkDetector() as detector:
                while True:
                    frame = camera.read()
                    result = detector.process(frame)
                    if result.landmarks is not None:
                        _draw_landmark_groups(frame, result.landmarks)
                        status = f"EAR: {result.ear:.3f}  MAR: {result.mar:.3f}"
                    else:
                        status = "Khong phat hien khuon mat"

                    now = monotonic()
                    if now - last_console_output >= DEMO_CONSOLE_INTERVAL_SECONDS:
                        if result.has_face:
                            print(
                                f"EAR={result.ear:.3f} MAR={result.mar:.3f} "
                                f"confidence={result.confidence}"
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
                    cv2.imshow("DrowsyGuard - landmark demo (Q de thoat)", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

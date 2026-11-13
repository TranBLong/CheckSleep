"""Local webcam capture; frames remain in memory and are never saved."""

from typing import Optional

import cv2

from config import CAMERA_INDEX


class CameraError(Exception):
    """Base exception for camera capture errors."""


class CameraUnavailableError(CameraError):
    """Raised when OpenCV cannot open the requested camera."""


class CameraNotOpenError(CameraError):
    """Raised when reading from a camera that has not been opened."""


class CameraDisconnectedError(CameraError):
    """Raised when an opened camera stops returning frames."""


class QuanLyCamera:
    """OpenCV camera lifecycle wrapper (project class: QuanLyCamera)."""

    def __init__(self, camera_index: int = CAMERA_INDEX) -> None:
        self.camera_index = camera_index
        self._capture: Optional[cv2.VideoCapture] = None

    def open(self) -> None:
        """Open the configured camera or raise an actionable error."""
        if self._capture is not None:
            if self._capture.isOpened():
                return
            self.close()

        try:
            capture = cv2.VideoCapture(self.camera_index)
        except cv2.error as exc:
            raise CameraUnavailableError(
                f"Không mở được camera index {self.camera_index}: {exc}"
            ) from exc
        if not capture.isOpened():
            capture.release()
            raise CameraUnavailableError(
                f"Không mở được camera index {self.camera_index}. "
                "Hãy kiểm tra camera đã kết nối, quyền truy cập và ứng dụng khác "
                "có đang sử dụng camera hay không."
            )
        self._capture = capture

    def read(self):
        """Return the next BGR frame or raise if the camera is unavailable."""
        if self._capture is None:
            raise CameraNotOpenError("Camera chưa được mở.")
        if not self._capture.isOpened():
            self.close()
            raise CameraDisconnectedError(
                "Camera đã mất kết nối hoặc không còn mở."
            )

        try:
            success, frame = self._capture.read()
        except cv2.error as exc:
            self.close()
            raise CameraDisconnectedError(f"Không đọc được camera: {exc}") from exc
        if not success or frame is None:
            self.close()
            raise CameraDisconnectedError(
                "Camera đã mất kết nối hoặc không còn trả về khung hình."
            )
        return frame

    def close(self) -> None:
        """Release the camera; safe to call more than once."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> "QuanLyCamera":
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

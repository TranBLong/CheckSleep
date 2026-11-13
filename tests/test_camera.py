from unittest.mock import Mock, patch

import pytest

from core.camera import (
    CameraDisconnectedError,
    CameraNotOpenError,
    CameraUnavailableError,
    QuanLyCamera,
)


@patch("core.camera.cv2.VideoCapture")
def test_open_and_read_frame(mock_video_capture):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.read.return_value = (True, object())
    mock_video_capture.return_value = capture
    camera = QuanLyCamera(camera_index=2)

    camera.open()
    frame = camera.read()

    assert frame is not None
    mock_video_capture.assert_called_once_with(2)
    camera.close()
    capture.release.assert_called_once()


@patch("core.camera.cv2.VideoCapture")
def test_open_failure_releases_capture_and_reports_unavailable(mock_video_capture):
    capture = Mock()
    capture.isOpened.return_value = False
    mock_video_capture.return_value = capture

    with pytest.raises(CameraUnavailableError, match="Không mở được camera"):
        QuanLyCamera().open()

    capture.release.assert_called_once()


def test_read_without_opening_reports_error():
    with pytest.raises(CameraNotOpenError, match="chưa được mở"):
        QuanLyCamera().read()


@patch("core.camera.cv2.VideoCapture")
def test_failed_read_releases_camera_and_reports_disconnect(mock_video_capture):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.read.return_value = (False, None)
    mock_video_capture.return_value = capture
    camera = QuanLyCamera()
    camera.open()

    with pytest.raises(CameraDisconnectedError, match="mất kết nối"):
        camera.read()

    capture.release.assert_called_once()
    with pytest.raises(CameraNotOpenError):
        camera.read()


@patch("core.camera.cv2.VideoCapture")
def test_camera_closed_after_open_is_reported_as_disconnected(mock_video_capture):
    capture = Mock()
    capture.isOpened.side_effect = [True, False]
    mock_video_capture.return_value = capture
    camera = QuanLyCamera()
    camera.open()

    with pytest.raises(CameraDisconnectedError):
        camera.read()

    capture.release.assert_called_once()

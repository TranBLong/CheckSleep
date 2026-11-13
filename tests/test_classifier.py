import numpy as np
import pytest

from core.classifier import (
    MoHinhPhatHien,
    extract_eye_crops,
    extract_mouth_crop,
)


class FakeInterpreter:
    def __init__(self, _model_path, probability):
        self.probability = probability
        self.input = None
        self.closed = False

    def allocate_tensors(self):
        pass

    def get_input_details(self):
        return [
            {
                "shape": np.array((1, 8, 8, 3)),
                "dtype": np.float32,
                "index": 1,
            }
        ]

    def get_output_details(self):
        return [
            {
                "shape": np.array((1, 1)),
                "dtype": np.float32,
                "index": 2,
            }
        ]

    def set_tensor(self, _index, value):
        self.input = value

    def invoke(self):
        pass

    def get_tensor(self, _index):
        return np.array([[self.probability]], dtype=np.float32)

    def close(self):
        self.closed = True


def test_tflite_classifier_returns_probabilities_for_both_eyes_and_mouth(tmp_path):
    eye_path = tmp_path / "eye.tflite"
    mouth_path = tmp_path / "mouth.tflite"
    eye_path.touch()
    mouth_path.touch()
    created = []

    def interpreter_factory(model_path):
        interpreter = FakeInterpreter(
            model_path,
            0.2 if model_path == str(eye_path) else 0.8,
        )
        created.append(interpreter)
        return interpreter

    classifier = MoHinhPhatHien(
        eye_path,
        mouth_path,
        interpreter_factory=interpreter_factory,
    )
    eye = np.full((16, 16, 3), 127, dtype=np.uint8)
    mouth = np.full((16, 16, 3), 64, dtype=np.uint8)

    result = classifier.predict((eye, eye), mouth)

    assert result.eye_closed_probability == pytest.approx(0.2)
    assert result.mouth_yawn_probability == pytest.approx(0.8)
    assert created[0].input.shape == (1, 8, 8, 3)
    assert classifier.predict(None, None).eye_closed_probability is None
    classifier.close()
    assert all(interpreter.closed for interpreter in created)


def test_tflite_classifier_reports_missing_model(tmp_path):
    with pytest.raises(FileNotFoundError, match="Không tìm thấy mô hình"):
        MoHinhPhatHien(tmp_path / "missing-eye.tflite", tmp_path / "mouth.tflite")


def test_landmark_crop_helpers_return_eye_and_mouth_regions():
    landmarks = [(0.5, 0.5, 0.0)] * 478
    landmarks[362] = (0.3, 0.4, 0.0)
    landmarks[385] = (0.35, 0.35, 0.0)
    landmarks[387] = (0.4, 0.35, 0.0)
    landmarks[263] = (0.45, 0.4, 0.0)
    landmarks[373] = (0.4, 0.45, 0.0)
    landmarks[380] = (0.35, 0.45, 0.0)
    landmarks[33] = (0.5, 0.4, 0.0)
    landmarks[160] = (0.55, 0.35, 0.0)
    landmarks[158] = (0.6, 0.35, 0.0)
    landmarks[133] = (0.65, 0.4, 0.0)
    landmarks[153] = (0.6, 0.45, 0.0)
    landmarks[144] = (0.55, 0.45, 0.0)
    for index, point in zip(
        (78, 81, 13, 311, 308, 402, 14, 178),
        (
            (0.35, 0.6, 0.0),
            (0.4, 0.58, 0.0),
            (0.5, 0.57, 0.0),
            (0.6, 0.58, 0.0),
            (0.65, 0.6, 0.0),
            (0.6, 0.62, 0.0),
            (0.5, 0.63, 0.0),
            (0.4, 0.62, 0.0),
        ),
    ):
        landmarks[index] = point
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    eyes = extract_eye_crops(frame, landmarks)
    mouth = extract_mouth_crop(frame, landmarks)

    assert len(eyes) == 2
    assert all(crop.ndim == 3 and crop.size for crop in eyes)
    assert mouth is not None
    assert mouth.ndim == 3

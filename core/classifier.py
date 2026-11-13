"""TensorFlow Lite inference for eye-closure and yawn probabilities."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from config import EYE_TFLITE_MODEL_PATH, MOUTH_TFLITE_MODEL_PATH
from core.metrics import (
    INNER_MOUTH_LANDMARK_INDICES,
    LEFT_EYE_LANDMARK_INDICES,
    RIGHT_EYE_LANDMARK_INDICES,
)
from core.types import Landmark


@dataclass(frozen=True)
class KetQuaMoHinh:
    eye_closed_probability: float | None
    mouth_yawn_probability: float | None


class MoHinhPhatHien:
    """Run local TFLite models (class: MoHinhPhatHien)."""

    def __init__(
        self,
        eye_model_path: str | Path = EYE_TFLITE_MODEL_PATH,
        mouth_model_path: str | Path = MOUTH_TFLITE_MODEL_PATH,
        *,
        interpreter_factory=None,
    ) -> None:
        self._eye_interpreter = self._load_interpreter(
            eye_model_path, "eye", interpreter_factory
        )
        self._mouth_interpreter = self._load_interpreter(
            mouth_model_path, "mouth", interpreter_factory
        )

    @staticmethod
    def _load_interpreter(path, model_name: str, interpreter_factory):
        model_path = Path(path)
        if not model_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy mô hình TFLite: {model_path}")
        if interpreter_factory is None:
            try:
                from tensorflow.lite import Interpreter
            except ImportError as exc:
                raise RuntimeError(
                    "CNN yêu cầu TensorFlow để nạp mô hình TFLite. "
                    "Cài dependency tensorflow hoặc chọn CLASSIFIER_MODE='baseline'."
                ) from exc
            interpreter_factory = Interpreter

        try:
            interpreter = interpreter_factory(model_path=str(model_path))
            interpreter.allocate_tensors()
        except Exception as exc:
            raise RuntimeError(
                f"Không nạp được mô hình TFLite {model_name}: {exc}"
            ) from exc

        inputs = interpreter.get_input_details()
        outputs = interpreter.get_output_details()
        if len(inputs) != 1 or len(outputs) != 1:
            raise ValueError(
                f"Mô hình TFLite {model_name} phải có đúng một input và một output."
            )
        shape = tuple(int(value) for value in inputs[0]["shape"])
        if len(shape) != 4 or shape[0] != 1 or shape[3] != 3:
            raise ValueError(
                f"Input {model_name} phải có dạng (1, cao, rộng, 3), nhận {shape}."
            )
        return interpreter

    def predict(
        self,
        eye_crops: np.ndarray | Sequence[np.ndarray] | None,
        mouth_crop: np.ndarray | None,
    ) -> KetQuaMoHinh:
        """Return P(eye closed) and P(yawn); missing crops remain unavailable."""
        eye_probability = None
        if eye_crops is not None:
            crops = (
                [eye_crops]
                if isinstance(eye_crops, np.ndarray)
                else list(eye_crops)
            )
            if crops:
                eye_probability = float(
                    np.mean(
                        [
                            self._predict_one(self._eye_interpreter, crop)
                            for crop in crops
                        ]
                    )
                )
        mouth_probability = (
            self._predict_one(self._mouth_interpreter, mouth_crop)
            if mouth_crop is not None
            else None
        )
        return KetQuaMoHinh(eye_probability, mouth_probability)

    @staticmethod
    def _predict_one(interpreter: Any, image: np.ndarray) -> float:
        inputs = interpreter.get_input_details()
        outputs = interpreter.get_output_details()
        input_details = inputs[0]
        height, width = int(input_details["shape"][1]), int(input_details["shape"][2])
        image = _prepare_image(image, width, height)
        dtype = input_details["dtype"]
        if np.issubdtype(dtype, np.integer):
            scale, zero_point = input_details.get("quantization", (0.0, 0))
            if scale <= 0:
                raise ValueError("Mô hình TFLite lượng tử hóa thiếu quantization scale.")
            image = np.clip(
                np.round(image / scale + zero_point),
                np.iinfo(dtype).min,
                np.iinfo(dtype).max,
            ).astype(dtype)
        else:
            image = image.astype(dtype)
        interpreter.set_tensor(input_details["index"], image[np.newaxis, ...])
        interpreter.invoke()
        output_details = outputs[0]
        prediction = interpreter.get_tensor(output_details["index"])
        output_dtype = output_details["dtype"]
        if np.issubdtype(output_dtype, np.integer):
            scale, zero_point = output_details.get("quantization", (0.0, 0))
            if scale <= 0:
                raise ValueError("Mô hình TFLite lượng tử hóa thiếu output scale.")
            prediction = (prediction.astype(np.float32) - zero_point) * scale
        prediction = np.asarray(prediction, dtype=np.float32).reshape(-1)
        if prediction.size != 1 or not np.isfinite(prediction[0]):
            raise ValueError("Mô hình TFLite phải trả một xác suất hữu hạn.")
        if not 0 <= prediction[0] <= 1:
            raise ValueError("Output TFLite phải là xác suất trong khoảng [0, 1].")
        return float(prediction[0])

    def close(self) -> None:
        for interpreter in (self._eye_interpreter, self._mouth_interpreter):
            close = getattr(interpreter, "close", None)
            if close is not None:
                close()


def extract_eye_crops(
    frame: np.ndarray, landmarks: Sequence[Landmark]
) -> tuple[np.ndarray, ...]:
    """Crop both eye regions for independent inference."""
    crops = []
    for indices in (LEFT_EYE_LANDMARK_INDICES, RIGHT_EYE_LANDMARK_INDICES):
        crop = crop_landmark_region(frame, landmarks, indices)
        if crop is not None:
            crops.append(crop)
    return tuple(crops)


def extract_mouth_crop(
    frame: np.ndarray, landmarks: Sequence[Landmark]
) -> np.ndarray | None:
    """Crop the inner-mouth region for yawn inference."""
    return crop_landmark_region(frame, landmarks, INNER_MOUTH_LANDMARK_INDICES)


def crop_landmark_region(
    frame: np.ndarray,
    landmarks: Sequence[Landmark],
    indices: Sequence[int],
    padding_ratio: float = 1.5,
) -> np.ndarray | None:
    """Return a square crop around normalized landmark coordinates."""
    if frame.ndim not in (2, 3) or frame.size == 0:
        raise ValueError("frame must be a non-empty image.")
    if not indices or any(index < 0 or index >= len(landmarks) for index in indices):
        return None

    height, width = frame.shape[:2]
    points = [(landmarks[index][0] * width, landmarks[index][1] * height) for index in indices]
    left = min(point[0] for point in points)
    right = max(point[0] for point in points)
    top = min(point[1] for point in points)
    bottom = max(point[1] for point in points)
    region_size = max(right - left, bottom - top)
    if region_size <= 0:
        return None

    side = max(2, int(region_size * (1 + 2 * padding_ratio)))
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    crop_left = max(0, int(center_x - side / 2))
    crop_top = max(0, int(center_y - side / 2))
    crop_right = min(width, crop_left + side)
    crop_bottom = min(height, crop_top + side)
    if crop_right - crop_left < 2 or crop_bottom - crop_top < 2:
        return None
    return frame[crop_top:crop_bottom, crop_left:crop_right].copy()


def _prepare_image(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("CNN input must be a non-empty NumPy image.")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.ndim == 3 and image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    else:
        raise ValueError("CNN input must be grayscale or BGR.")
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32)

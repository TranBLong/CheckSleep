"""Frame and facial-region quality checks for reliable in-memory analysis."""

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import cv2
import numpy as np

from config import (
    FEATURE_MIN_BRIGHTNESS,
    FEATURE_MIN_LAPLACIAN_VARIANCE,
    FEATURE_ROI_PADDING_RATIO,
    QUALITY_CLAHE_CLIP_LIMIT,
    QUALITY_CLAHE_ENABLED,
    QUALITY_CLAHE_TILE_GRID_SIZE,
    QUALITY_MIN_BRIGHTNESS,
    QUALITY_MIN_LAPLACIAN_VARIANCE,
)
from core.types import Landmark


@dataclass(frozen=True)
class FrameQuality:
    frame: np.ndarray
    brightness_mean: float
    laplacian_variance: float
    accepted: bool
    reason: str | None
    enhanced: bool = False


def assess_frame_quality(
    frame: np.ndarray,
    *,
    min_brightness: float = QUALITY_MIN_BRIGHTNESS,
    min_laplacian_variance: float = QUALITY_MIN_LAPLACIAN_VARIANCE,
    clahe_enabled: bool = QUALITY_CLAHE_ENABLED,
) -> FrameQuality:
    """Measure brightness and blur, optionally applying CLAHE to dim frames."""
    _validate_threshold(min_brightness, "min_brightness")
    _validate_threshold(min_laplacian_variance, "min_laplacian_variance")
    if not isinstance(clahe_enabled, bool):
        raise ValueError("clahe_enabled must be bool.")
    gray = _to_gray(frame)
    processed = frame
    brightness = float(np.mean(gray))
    enhanced = False

    if brightness < min_brightness and clahe_enabled:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        lightness, chroma_a, chroma_b = cv2.split(lab)
        clahe = cv2.createCLAHE(
            clipLimit=QUALITY_CLAHE_CLIP_LIMIT,
            tileGridSize=QUALITY_CLAHE_TILE_GRID_SIZE,
        )
        enhanced_lightness = clahe.apply(lightness)
        processed = cv2.cvtColor(
            cv2.merge((enhanced_lightness, chroma_a, chroma_b)),
            cv2.COLOR_LAB2BGR,
        )
        gray = _to_gray(processed)
        brightness = float(np.mean(gray))
        enhanced = True

    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    reasons = []
    if brightness < min_brightness:
        reasons.append("Quá tối")
    if laplacian_variance < min_laplacian_variance:
        reasons.append("ảnh bị mờ")
    return FrameQuality(
        frame=processed,
        brightness_mean=brightness,
        laplacian_variance=laplacian_variance,
        accepted=not reasons,
        reason=" và ".join(reasons) if reasons else None,
        enhanced=enhanced,
    )


def feature_region_is_usable(
    frame: np.ndarray,
    landmarks: Sequence[Landmark],
    indices: Sequence[int],
    *,
    min_brightness: float = FEATURE_MIN_BRIGHTNESS,
    min_laplacian_variance: float = FEATURE_MIN_LAPLACIAN_VARIANCE,
    padding_ratio: float = FEATURE_ROI_PADDING_RATIO,
) -> bool:
    """Check local texture and illumination around one facial feature."""
    _validate_threshold(min_brightness, "min_brightness")
    _validate_threshold(min_laplacian_variance, "min_laplacian_variance")
    if not isfinite(padding_ratio) or padding_ratio < 0:
        raise ValueError("padding_ratio must be finite and non-negative.")
    if not indices or any(index < 0 or index >= len(landmarks) for index in indices):
        raise ValueError("indices must refer to available landmarks.")

    height, width = frame.shape[:2]
    points = [(landmarks[index][0] * width, landmarks[index][1] * height) for index in indices]
    left = min(point[0] for point in points)
    right = max(point[0] for point in points)
    top = min(point[1] for point in points)
    bottom = max(point[1] for point in points)
    region_width = right - left
    region_height = bottom - top
    if region_width <= 0 or region_height <= 0:
        return False

    left = max(0, int(left - region_width * padding_ratio))
    right = min(width, int(right + region_width * padding_ratio) + 1)
    top = max(0, int(top - region_height * padding_ratio))
    bottom = min(height, int(bottom + region_height * padding_ratio) + 1)
    if right - left < 2 or bottom - top < 2:
        return False

    gray = _to_gray(frame)
    crop = gray[top:bottom, left:right]
    return (
        float(np.mean(crop)) >= min_brightness
        and float(cv2.Laplacian(crop, cv2.CV_64F).var())
        >= min_laplacian_variance
    )


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if not isinstance(frame, np.ndarray) or frame.size == 0:
        raise ValueError("frame must be a non-empty NumPy array.")
    if frame.dtype != np.uint8:
        raise ValueError("frame must use uint8 pixels.")
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    raise ValueError("frame must be a grayscale or BGR image.")


def _validate_threshold(value: float, name: str) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative.")

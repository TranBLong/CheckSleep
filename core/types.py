"""Shared result types for the DrowsyGuard processing pipeline."""

from dataclasses import dataclass
from enum import Enum

Landmark = tuple[float, float, float]


class TrangThai(str, Enum):
    UNKNOWN = "UNKNOWN"
    ALERT = "ALERT"
    FATIGUED = "FATIGUED"
    DROWSY = "DROWSY"
    ASLEEP = "ASLEEP"


@dataclass(frozen=True)
class KetQuaPhatHien:
    """Detection result with normalized Face Mesh landmarks when available."""

    has_face: bool
    ear: float | None = None
    mar: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    roll: float | None = None
    confidence: float | None = None
    landmarks: tuple[Landmark, ...] | None = None
    face_candidates: tuple["FaceCandidate", ...] = ()
    partial_data: bool = False
    partial_reason: str | None = None


@dataclass(frozen=True)
class FaceCandidate:
    """One face detection and its normalized bounding box."""

    bounding_box: tuple[float, float, float, float]
    result: KetQuaPhatHien

import numpy as np

from core.quality import assess_frame_quality, feature_region_is_usable


def _checkerboard(low=0, high=255):
    pattern = np.indices((64, 64)).sum(axis=0) % 2
    gray = np.where(pattern, high, low).astype(np.uint8)
    return np.repeat(gray[:, :, None], 3, axis=2)


def test_assess_frame_quality_rejects_dark_and_blurry_frames():
    dark = assess_frame_quality(np.zeros((64, 64, 3), dtype=np.uint8))
    blurry = assess_frame_quality(np.full((64, 64, 3), 127, dtype=np.uint8))

    assert not dark.accepted
    assert dark.reason == "Quá tối và ảnh bị mờ"
    assert not blurry.accepted
    assert blurry.reason == "ảnh bị mờ"


def test_assess_frame_quality_can_use_clahe_for_dim_frames():
    dim = _checkerboard(low=20, high=50)

    result = assess_frame_quality(
        dim,
        min_brightness=40,
        min_laplacian_variance=0,
        clahe_enabled=True,
    )

    assert result.enhanced
    assert result.brightness_mean > float(np.mean(dim))
    assert result.accepted


def test_feature_region_quality_distinguishes_texture_from_uniform_occlusion():
    landmarks = tuple(
        (x / 64, y / 64, 0.0)
        for x, y in ((20, 20), (30, 20), (30, 25), (20, 25))
    )
    indices = (0, 1, 2, 3)

    assert feature_region_is_usable(
        _checkerboard(),
        landmarks,
        indices,
        min_brightness=0,
        min_laplacian_variance=1,
    )
    assert not feature_region_is_usable(
        np.full((64, 64, 3), 127, dtype=np.uint8),
        landmarks,
        indices,
        min_brightness=0,
        min_laplacian_variance=1,
    )

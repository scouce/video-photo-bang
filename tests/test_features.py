import numpy as np

from video_dsp.features import (
    compute_edge_density,
    compute_luminance_stats,
    compute_normalized_histogram,
    compute_tenengrad,
    compute_variance_laplacian,
    to_luminance,
)


def _flat(value: int = 128, size: int = 64) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def _stripes() -> np.ndarray:
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:, ::4] = 255
    return image


def test_luminance_is_normalized():
    gray = to_luminance(_flat(255))
    assert gray.dtype == np.float32
    assert 0.0 <= float(gray.min()) <= float(gray.max()) <= 1.0
    assert abs(float(gray.mean()) - 1.0) < 1e-6


def test_flat_image_has_low_sharpness():
    gray = to_luminance(_flat())
    assert compute_variance_laplacian(gray) < 1e-6
    assert compute_tenengrad(gray) < 1e-6


def test_edges_increase_sharpness():
    flat = to_luminance(_flat())
    stripes = to_luminance(_stripes())
    assert compute_tenengrad(stripes) > compute_tenengrad(flat)
    assert compute_variance_laplacian(stripes) > compute_variance_laplacian(flat)


def test_edge_density_zero_for_flat_image():
    gray = to_luminance(_flat())
    assert compute_edge_density(gray) == 0.0


def test_histogram_sums_to_one():
    gray = to_luminance(_stripes())
    histogram = compute_normalized_histogram(gray, bins=32)
    assert histogram.shape == (32,)
    assert abs(float(histogram.sum()) - 1.0) < 1e-9


def test_black_and_white_clipping():
    black = to_luminance(_flat(0))
    white = to_luminance(_flat(255))
    black_stats = compute_luminance_stats(black)
    white_stats = compute_luminance_stats(white)
    assert black_stats["black_clip"] == 1.0
    assert black_stats["white_clip"] == 0.0
    assert white_stats["white_clip"] == 1.0
    assert white_stats["black_clip"] == 0.0


def test_resize_for_analysis_never_upscales():
    from video_dsp.config import load_config
    from video_dsp.features import resize_for_analysis

    config = load_config({"analysis_resize": {"enabled": True, "max_dimension": 1280}})
    small = _flat(size=64)
    assert resize_for_analysis(small, config).shape == small.shape


def test_histogram_entropy_bounds():
    from video_dsp.features import compute_histogram_entropy

    flat = np.full(16, 1.0 / 16.0)
    single = np.zeros(16)
    single[0] = 1.0
    assert compute_histogram_entropy(flat) == 1.0
    assert compute_histogram_entropy(single) == 0.0


def test_local_contrast_is_zero_on_flat_and_positive_on_stripes():
    from video_dsp.features import compute_local_contrast

    flat = to_luminance(_flat())
    stripes = to_luminance(_stripes())
    assert compute_local_contrast(flat) == 0.0
    assert compute_local_contrast(stripes) > 0.0


def test_color_stats_neutral_grey_has_no_cast():
    from video_dsp.features import compute_color_stats

    stats = compute_color_stats(_flat(128))
    assert stats["saturation_mean"] == 0.0
    assert stats["colorfulness"] == 0.0
    assert stats["channel_cast"] == 0.0


def test_color_stats_detects_a_red_dominant():
    from video_dsp.features import compute_color_stats

    red = np.zeros((64, 64, 3), dtype=np.uint8)
    red[:, :, 2] = 200
    stats = compute_color_stats(red)
    assert stats["saturation_mean"] == 1.0
    assert stats["channel_cast"] > 0.5
    assert stats["colorfulness"] > 0.0


def test_motion_thumbnail_is_small_and_uint8():
    from video_dsp.features import motion_thumbnail

    big = np.zeros((480, 640, 3), dtype=np.uint8)
    thumb = motion_thumbnail(big, max_dimension=96)
    assert thumb.dtype == np.uint8
    assert max(thumb.shape[:2]) == 96


def test_compute_frame_metrics_covers_the_catalog():
    from video_dsp.config import load_config
    from video_dsp.features import compute_frame_metrics
    from video_dsp.metrics_spec import FIELD_CATALOG

    metrics = compute_frame_metrics(_stripes(), load_config())
    per_shot_only = {
        "duration_seconds",
        "clip_total",
        "midtone_dev",
        "dynamic_range",
        "instability",
        "motion_per_second",
        "translation_consistency",
        "jitter_px",
        "pan_speed_px_s",
        "phase_response",
    }
    for key in FIELD_CATALOG:
        if key in per_shot_only:
            continue
        assert key in metrics, key
    for key, value in metrics.items():
        if key == "histogram":
            continue
        assert np.isfinite(value), key

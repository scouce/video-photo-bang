"""Tests for the normalization engine: bounds, provenance and explicit fallbacks."""

import pytest

from video_dsp.config import load_config
from video_dsp.normalization import (
    apply_transform,
    build_normalization,
    combined_score,
    dimension_scores,
    normalize_value,
    percentile_bounds,
)


def _shot(value: float, **extra: float) -> dict:
    metrics = {
        "variance_laplacian": value,
        "tenengrad": value * 10.0,
        "clip_total": 0.0,
        "midtone_dev": 0.1,
        "std": value / 1000.0,
        "dynamic_range": value / 1000.0,
        "translation_consistency": 0.8,
        "jitter_px": 0.5,
        "instability": 0.05,
        "pan_speed_px_s": 10.0,
        "motion_per_second": 0.2,
        "colorfulness": 0.2,
        "saturation_mean": 0.3,
        "channel_cast": 0.02,
        "entropy": 0.7,
        "local_contrast": 0.05,
        "duration_seconds": 4.0,
        "black_clip": 0.0,
        "white_clip": 0.0,
        "translation_usable": 1.0,
        "stability_source": "translation",
    }
    metrics.update(extra)
    return {"shot_id": f"shot_{value}", "metrics": metrics}


def test_apply_transform_log1p():
    assert apply_transform(0.0, "log1p") == 0.0
    assert apply_transform(9.0, "log1p") == pytest.approx(2.302585, rel=1e-5)
    assert apply_transform(9.0, "identity") == 9.0


def test_percentile_bounds_linear():
    low, high, median = percentile_bounds([0, 1, 2, 3, 4], 0.0, 100.0)
    assert (low, high, median) == (0.0, 4.0, 2.0)


def test_percentile_normalization_records_its_source():
    config = load_config()
    shots = [_shot(value) for value in range(10, 210, 20)]
    table, warnings = build_normalization(shots, config)
    entry = table["sharpness"]["components"]["vol"]
    assert entry["method"] == "percentile"
    assert entry["source"] == "per_video_p5_p95"
    assert entry["low"] < entry["high"]
    assert entry["shots_used"] == len(shots)
    assert not any("sharpness.vol" in warning for warning in warnings)


def test_normalize_value_higher_better_bounds():
    entry = {"mode": "higher_better", "transform": "identity", "low": 0.0, "high": 10.0}
    assert normalize_value(-5.0, entry) == 0.0
    assert normalize_value(5.0, entry) == 0.5
    assert normalize_value(50.0, entry) == 1.0


def test_normalize_value_lower_better_bounds():
    entry = {"mode": "lower_better", "transform": "identity", "low": 0.0, "high": 10.0}
    assert normalize_value(0.0, entry) == 1.0
    assert normalize_value(10.0, entry) == 0.0
    assert normalize_value(5.0, entry) == 0.5


def test_normalize_value_band_is_one_inside_and_decays_outside():
    entry = {
        "mode": "band",
        "transform": "identity",
        "low": 3.0,
        "high": 5.0,
        "falloff": 1.0,
    }
    assert normalize_value(4.0, entry) == 1.0
    assert normalize_value(2.0, entry) == 0.0
    assert normalize_value(6.0, entry) == 0.0
    assert 0.0 < normalize_value(2.5, entry) < 1.0


def test_degenerate_spread_falls_back_to_absolute_and_records_it():
    config = load_config()
    shots = [_shot(100.0) for _ in range(10)]
    table, warnings = build_normalization(shots, config)
    entry = table["sharpness"]["components"]["vol"]
    assert entry["method"] == "absolute"
    assert entry["source"] == "config_absolute"
    assert entry["fallback_reason"].startswith("degenerate_spread")
    assert any("normalization_fallback:sharpness.vol" in warning for warning in warnings)


def test_too_few_shots_falls_back_to_absolute():
    config = load_config()
    shots = [_shot(value) for value in (10.0, 40.0, 90.0)]
    table, warnings = build_normalization(shots, config)
    entry = table["sharpness"]["components"]["vol"]
    assert entry["method"] == "absolute"
    assert entry["fallback_reason"].startswith("too_few_shots")
    assert warnings


def test_absolute_method_uses_config_ranges_verbatim():
    config = load_config(preset="balanced_v1")
    shots = [_shot(value) for value in range(10, 210, 20)]
    table, _ = build_normalization(shots, config)
    entry = table["sharpness"]["components"]["vol"]
    assert entry["method"] == "absolute"
    assert entry["absolute_range_raw"] == {"low": 20.0, "high": 400.0}


def test_exposure_components_are_always_absolute():
    config = load_config()
    shots = [_shot(value) for value in range(10, 210, 20)]
    table, _ = build_normalization(shots, config)
    for component in table["exposure"]["components"].values():
        assert component["method"] == "absolute"


def test_dimension_scores_stay_bounded_and_ordered():
    config = load_config()
    shots = [_shot(value) for value in range(10, 210, 20)]
    table, _ = build_normalization(shots, config)
    low, _, _ = dimension_scores(shots[0]["metrics"], table)
    high, _, _ = dimension_scores(shots[-1]["metrics"], table)
    for value in high.values():
        assert 0.0 <= value <= 1.0
    assert high["sharpness"] > low["sharpness"]
    assert high["contrast"] > low["contrast"]


def test_stability_uses_instability_fallback_when_translation_unusable():
    config = load_config()
    shots = [_shot(value) for value in range(10, 210, 20)]
    table, _ = build_normalization(shots, config)
    metrics = dict(shots[0]["metrics"])
    metrics["translation_usable"] = 0.0
    metrics["instability"] = 0.0
    dimensions, components, _ = dimension_scores(metrics, table)
    assert components["stability"]["__source"] == "instability_fallback"
    assert "instability" in components["stability"]
    assert dimensions["stability"] == 1.0


def test_combined_score_renormalizes_zero_weight_dimensions():
    dimensions = {
        "sharpness": 1.0,
        "exposure": 0.0,
        "contrast": 0.0,
        "stability": 0.0,
        "motion": 0.0,
        "color": 0.0,
        "texture": 0.0,
        "duration": 0.0,
    }
    weights = {
        "sharpness": 0.0,
        "exposure": 0.0,
        "contrast": 0.0,
        "stability": 0.0,
        "motion": 0.0,
        "color": 0.0,
        "texture": 0.0,
        "duration": 0.0,
    }
    weights["sharpness"] = 1.0
    total, effective = combined_score(dimensions, weights)
    assert total == 1.0
    assert effective["sharpness"] == 1.0
    assert effective["motion"] == 0.0


def test_combined_score_rejects_all_zero_weights():
    dimensions = {key: 0.0 for key in ("sharpness", "exposure")}
    with pytest.raises(ValueError):
        combined_score(dimensions, {"sharpness": 0.0, "exposure": 0.0})


def test_missing_metric_is_reported_not_silently_zeroed():
    config = load_config()
    shots = [_shot(value) for value in range(10, 210, 20)]
    table, _ = build_normalization(shots, config)
    metrics = dict(shots[0]["metrics"])
    del metrics["entropy"]
    _, components, warnings = dimension_scores(metrics, table)
    assert any("metric_missing:texture.entropy" in warning for warning in warnings)
    assert "entropy" not in components["texture"]

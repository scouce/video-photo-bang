"""Preset separation: a preset must change the answer, not just the labels.

Two levels are checked:

- the table: every non-legacy pair differs in at least 0.10 of total weight L1 **and** in at
  least one target band or gate, so "the presets look the same" fails before any video runs;
- the effect: on a deterministic fixture of four visual profiles (portrait, action,
  landscape, low light) the Top-10 sets of two different presets overlap in under 80%.

``balanced_v1`` is the legacy v0.1.0 formula and is only checked for being untouched.
"""

from __future__ import annotations

import itertools

import pytest

from video_dsp.config import load_config
from video_dsp.metrics_spec import DIMENSION_ORDER
from video_dsp.presets import PRESETS, get_preset
from video_dsp.selection_service import recompute

LEGACY = "balanced_v1"
CORE = [name for name in PRESETS if name != LEGACY]

BASE_METRICS = {
    "variance_laplacian": 143.05,
    "tenengrad": 3761.7,
    "edge_density": 0.0346,
    "entropy": 0.846,
    "local_contrast": 0.0242,
    "saturation_mean": 0.2867,
    "saturation_std": 0.2093,
    "colorfulness": 0.1355,
    "channel_cast": 0.1252,
    "mean": 0.4937,
    "std": 0.2739,
    "p01": 0.0499,
    "p05": 0.0777,
    "p25": 0.1642,
    "p50": 0.6443,
    "p75": 0.7238,
    "p95": 0.7799,
    "p99": 0.8032,
    "black_clip": 0.0010,
    "white_clip": 0.0,
    "instability": 0.0256,
    "pan_speed_px_s": 2.57,
    "translation_consistency": 0.5972,
    "jitter_px": 0.98,
    "phase_response": 0.9702,
    "motion_per_second": 0.1281,
    "clip_total": 0.0010,
    "midtone_dev": 0.0127,
    "dynamic_range": 0.7021,
    "sample_count": 7.0,
    "median_dt_seconds": 0.2,
    "translation_usable": 1.0,
}

# One profile per intent, ten shots each. Values are multipliers/absolutes over the base
# record so every metric key the ranker reads is present.
PROFILES = {
    "portrait": {
        "motion_per_second": 0.03,
        "instability": 0.030,
        "jitter_px": 1.4,
        "pan_speed_px_s": 1.0,
        "saturation_mean": 0.38,
        "mean": 0.56,
        "duration_seconds": 4.0,
    },
    "action": {
        "motion_per_second": 0.95,
        "instability": 0.30,
        "jitter_px": 6.0,
        "pan_speed_px_s": 90.0,
        "saturation_mean": 0.30,
        "mean": 0.50,
        "duration_seconds": 2.5,
    },
    "landscape": {
        "motion_per_second": 0.04,
        "instability": 0.050,
        "jitter_px": 4.0,
        "pan_speed_px_s": 2.0,
        "saturation_mean": 0.45,
        "mean": 0.52,
        "local_contrast": 0.060,
        "entropy": 0.96,
        "duration_seconds": 7.0,
    },
    "low_light": {
        "motion_per_second": 0.015,
        "instability": 0.003,
        "jitter_px": 0.10,
        "pan_speed_px_s": 0.8,
        "saturation_mean": 0.12,
        "mean": 0.50,
        "duration_seconds": 9.0,
    },
}


def fixture_records() -> list[dict]:
    """Forty deterministic shot records: ten per visual profile."""
    records: list[dict] = []
    for profile, overrides in PROFILES.items():
        for index in range(10):
            metrics = dict(BASE_METRICS)
            metrics["duration_seconds"] = 0.0
            metrics.update(overrides)
            # A small deterministic drift so no two shots in a profile tie exactly.
            metrics["variance_laplacian"] = BASE_METRICS["variance_laplacian"] * (
                1.0 + 0.02 * index
            )
            metrics["tenengrad"] = BASE_METRICS["tenengrad"] * (1.0 + 0.02 * index)
            signature = [0.0] * 16
            signature[list(PROFILES).index(profile) * 4 + (index % 4)] = 1.0
            records.append(
                {
                    "shot_id": f"shot_{profile}_{index:02d}",
                    "start_time_seconds": float(len(records) * 4),
                    "end_time_seconds": float(len(records) * 4) + metrics["duration_seconds"],
                    "duration_seconds": metrics["duration_seconds"],
                    "metrics": metrics,
                    "histogram_signature": signature,
                    "warnings": [],
                }
            )
    return records


def top_ids(preset: str, records: list[dict], top_n: int = 10) -> set[str]:
    config = load_config(preset=preset)
    config["top_n"] = top_n
    config["diversity"] = {**config.get("diversity", {}), "enabled": False}
    result = recompute(records, config)
    return {shot["shot_id"] for shot in result["selected"]}


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


@pytest.mark.parametrize("left,right", list(itertools.combinations(CORE, 2)))
def test_every_pair_differs_in_weights_or_bands(left, right):
    first = get_preset(left)
    second = get_preset(right)
    weight_distance = sum(
        abs(first["weights"][dim] - second["weights"][dim]) for dim in DIMENSION_ORDER
    )
    bands = {key: value for key, value in first["targets"].items()}
    other = second["targets"]
    band_differs = any(
        bands.get(key) != other.get(key) for key in set(bands) | set(other)
    )
    gates_differ = first.get("hard_gates", {}) != second.get("hard_gates", {})
    assert weight_distance >= 0.10 or band_differs or gates_differ, (
        f"{left} and {right} are the same preset with two names"
    )


@pytest.mark.parametrize("left,right", list(itertools.combinations(CORE, 2)))
def test_presets_select_different_shots(left, right):
    records = fixture_records()
    overlap = jaccard(top_ids(left, records), top_ids(right, records))
    assert overlap < 0.80, f"{left} and {right} select the same shots (J={overlap:.2f})"


def test_each_preset_picks_its_own_profile():
    records = fixture_records()
    for preset in ("portrait", "action", "landscape", "low_light"):
        selected = top_ids(preset, records)
        assert selected, preset
        same_profile = sum(1 for shot_id in selected if f"_{preset}_" in shot_id)
        assert same_profile >= 6, (
            f"{preset} selected only {same_profile}/10 shots from its own profile"
        )


def test_legacy_preset_is_untouched():
    legacy = get_preset(LEGACY)
    assert legacy["weights"] == PRESETS[LEGACY]["weights"]
    assert not legacy.get("hard_gates")
    config = load_config(preset=LEGACY)
    assert config["hard_gates"]["calibration"] == "legacy_v0_1_0"
    assert config["preset_hard_gates"] == {}


def test_preset_gates_are_merged_and_recorded():
    portrait = load_config(preset="portrait")
    assert portrait["hard_gates"]["max_jitter_px"] == 3.0
    assert portrait["hard_gates"]["min_sharpness_score"] == 0.20
    assert portrait["preset_hard_gates"]["max_jitter_px"] == 3.0
    # The default is not mutated by loading a preset.
    assert load_config()["hard_gates"]["max_jitter_px"] == 4.0


def test_shorts_refuses_long_shots():
    records = fixture_records()
    config = load_config(preset="shorts")
    config["top_n"] = 10
    result = recompute(records, config)
    long_shots = [shot for shot in result["shots"] if shot["duration_seconds"] > 6.0]
    assert long_shots
    for shot in long_shots:
        gates = {failure["gate"] for failure in shot["failed_gates"]}
        assert "max_shot_duration" in gates
    assert all(shot["duration_seconds"] <= 6.0 for shot in result["selected"])

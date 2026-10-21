"""Central configuration for the MOV/MP4/AVI shot technical selector.

All thresholds are explicitly marked as ``initial_uncalibrated`` until a calibrated
corpus is available (see ``MEMORY.md``). The config is serialized into every output
document together with its hash so that any result can be reproduced.

Presets (``presets.py``) supply the dimension weights, target bands, normalization
method and quality floor. ``load_config`` applies a preset first and then the caller
overrides, so a partial override never loses the rest of the preset.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .metrics_spec import DIMENSION_ORDER
from .presets import DEFAULT_PRESET, get_preset

SCHEMA_VERSION = "0.2.0-calibration"
PIPELINE_NAME = "shot_technical_selector"
PIPELINE_VERSION = "0.2.0"
CALIBRATION_LABEL = "initial_uncalibrated"

SUPPORTED_EXTENSIONS: tuple[str, ...] = (".mov", ".mp4", ".m4v", ".avi", ".mkv")

_DEFAULT_PRESET = get_preset(DEFAULT_PRESET)

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "analysis_fps": 5.0,
    "top_n": 10,
    "min_resolution": {"width": 320, "height": 240},
    "supported_extensions": list(SUPPORTED_EXTENSIONS),
    "analysis_resize": {
        "enabled": True,
        "max_dimension": 1280,
        "interpolation": "area",
        "note": "documented measurement resolution, not enhancement; recorded for audit",
    },
    "histogram_bins": 64,
    "canny": {"low": 100, "high": 200},
    "clip_low": 0.02,
    "clip_high": 0.98,
    "shot_detection": {
        "weights": {"histogram": 0.65, "gradient": 0.20, "edge": 0.15},
        "mad_multiplier": 3.0,
        "min_gap_seconds": 0.4,
        "peak_prominence_ratio": 2.0,
        "peak_prominence_radius": 5,
        "peak_prominence_guard": 1,
        "peak_prominence_note": (
            "A peak must exceed the median distance of its neighbourhood by this factor; "
            "0 disables the filter. Local maxima inside sustained motion are rejected."
        ),
        "merge_similarity": 1.0,
        "merge_similarity_note": (
            "Bhattacharyya threshold for merging adjacent shots; 1.0 disables merging"
        ),
    },
    "motion": {
        "thumb_max_dimension": 96,
        "min_phase_response": 0.05,
        "note": "phase correlation is measured on a small luminance thumbnail",
    },
    "preset": DEFAULT_PRESET,
    "preset_label": _DEFAULT_PRESET["label_es"],
    "score_weights": dict(_DEFAULT_PRESET["weights"]),
    "targets": {key: dict(value) for key, value in _DEFAULT_PRESET["targets"].items()},
    "quality_floor": dict(_DEFAULT_PRESET["quality_floor"]),
    "diversity": {
        "enabled": True,
        "weight": 0.25,
        "metric": "bhattacharyya_histogram",
        "note": "MMR: lambda*score - (1-lambda)*max_similarity_to_selected",
    },
    "normalization": {
        "method": _DEFAULT_PRESET["normalization_method"],
        "low_percentile": 5.0,
        "high_percentile": 95.0,
        "min_shots": 6,
        "min_relative_spread": 0.02,
    },
    "ranges": {
        "variance_laplacian": {"low": 20.0, "high": 400.0},
        "tenengrad": {"low": 500.0, "high": 8000.0},
        "luminance_std": {"low": 0.05, "high": 0.35},
        "dynamic_range": {"low": 0.10, "high": 0.75},
        "instability": {"low": 0.0, "high": 0.35},
        "translation_consistency": {"low": 0.0, "high": 1.0},
        "jitter_px": {"low": 0.0, "high": 3.0},
        "colorfulness": {"low": 0.0, "high": 0.45},
        "channel_cast": {"low": 0.0, "high": 0.15},
        "entropy": {"low": 0.30, "high": 0.95},
        "local_contrast": {"low": 0.010, "high": 0.100},
        "clip_total": {"low": 0.0, "high": 0.10},
        "midtone_dev": {"low": 0.0, "high": 0.80},
    },
    "hard_gates": {
        "min_shot_duration_s": 1.0,
        "max_shot_duration_s": 15.0,
        "min_shot_duration_note": (
            "Shots shorter than this are merged into the previous shot before scoring; "
            "a sub-second fragment is a detection artifact, not a usable shot."
        ),
        "max_black_clip": 0.10,
        "max_white_clip": 0.10,
        "min_sharpness_score": 0.15,
        "max_instability": 0.40,
        "max_jitter_px": 4.0,
        "calibration": CALIBRATION_LABEL,
    },
    "boundary_montage": {
        "enabled": True,
        "offsets_seconds": [-0.4, -0.2, 0.0, 0.2, 0.4],
        "thumb_width": 320,
        "max_boundaries": 0,
        "note": "0 = all boundaries; frames come from the source at full quality, downscaled",
    },
    "artifacts": {
        "samples_csv": True,
        "shots_csv": True,
        "ui_json": True,
        "deterministic_gzip": True,
    },
}


def load_config(
    overrides: dict[str, Any] | None = None, preset: str | None = None
) -> dict[str, Any]:
    """Return a deep copy of the default config, optionally merged with overrides.

    ``preset`` is applied before ``overrides`` so a partial override keeps the rest of
    the preset intact. An override that changes ``score_weights`` without changing
    ``preset`` is preserved (the caller is then responsible for the weights summing to
    one; the ranking renormalizes anyway and records the effective weights).
    """
    config: dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))
    if preset is not None and preset != config["preset"]:
        _apply_preset(config, preset)
    if overrides:
        _deep_merge(config, overrides)
    _validate_config(config)
    return config


def _apply_preset(config: dict[str, Any], preset: str) -> None:
    bundle = get_preset(preset)
    config["preset"] = bundle["name"]
    config["preset_label"] = bundle["label_es"]
    config["score_weights"] = bundle["weights"]
    config["targets"] = bundle["targets"]
    config["quality_floor"] = bundle["quality_floor"]
    config["normalization"]["method"] = bundle["normalization_method"]
    config["hard_gates"]["calibration"] = bundle["calibration"]


def _validate_config(config: dict[str, Any]) -> None:
    weights = config.get("score_weights", {})
    missing = [name for name in DIMENSION_ORDER if name not in weights]
    if missing:
        raise ValueError(f"score_weights missing dimensions: {missing}")
    total = sum(float(value) for value in weights.values())
    if total <= 0:
        raise ValueError("score_weights must sum to a positive number")
    # Record the effective (renormalized) weights so the audit never guesses.
    config["score_weights_effective"] = {
        name: float(weights[name]) / total for name in DIMENSION_ORDER
    }
    method = config["normalization"]["method"]
    if method not in {"absolute", "per_video_percentile"}:
        raise ValueError(f"unknown normalization method: {method}")


def config_hash(config: dict[str, Any]) -> str:
    """Stable SHA-256 over the canonical JSON representation of the config."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def short_hash(value: str, length: int = 8) -> str:
    """Shorten a ``sha256:...`` string for use in directory names."""
    digest = value.split(":", 1)[-1]
    return digest[:length]


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Public in-place deep merge helper; returns ``base``."""
    _deep_merge(base, overrides)
    return base


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value

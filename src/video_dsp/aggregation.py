"""Aggregate per-frame metrics into shot-level metrics."""

from __future__ import annotations

import math

import numpy as np

# Explicit aggregation strategy per metric (see constitution, principle 5).
AGGREGATION: dict[str, str] = {
    "variance_laplacian": "median",
    "tenengrad": "median",
    "edge_density": "mean",
    "entropy": "median",
    "local_contrast": "median",
    "saturation_mean": "median",
    "saturation_std": "median",
    "colorfulness": "median",
    "channel_cast": "median",
    "mean": "median",
    "std": "median",
    "p01": "median",
    "p05": "median",
    "p25": "median",
    "p50": "median",
    "p75": "median",
    "p95": "median",
    "p99": "median",
    "black_clip": "mean",
    "white_clip": "mean",
}

MOTION_AGGREGATION: dict[str, str] = {
    "instability": "mean of internal combined distances",
    "motion_per_second": "mean combined distance / median dt",
    "pan_speed_px_s": "median translation magnitude / median dt",
    "translation_consistency": "vector coherence |sum(v)| / sum(|v|)",
    "jitter_px": "std of translation deltas",
    "phase_response": "median",
}


def _internal_distances(
    shot: list[dict], distances: list
) -> list:
    start_index = shot[0]["frame_index"]
    end_index = shot[-1]["frame_index"]
    return [
        distance
        for distance in distances
        if start_index < distance.right_index <= end_index
    ]


def _median_dt(shot: list[dict]) -> float:
    if len(shot) < 2:
        return 0.0
    timestamps = np.array(
        [sample["timestamp_seconds"] for sample in shot], dtype=np.float64
    )
    return float(np.median(np.diff(timestamps)))


def _translation_stats(
    internal: list, dt: float
) -> tuple[float, float, float, float, float]:
    """Return pan speed, coherence, jitter, phase response and motion per second."""
    if not internal:
        return 0.0, 1.0, 0.0, 0.0, 0.0

    vectors = np.array(
        [[d.translation_x, d.translation_y] for d in internal], dtype=np.float64
    )
    magnitudes = np.linalg.norm(vectors, axis=1)
    total_magnitude = float(magnitudes.sum())
    if total_magnitude <= 1e-9:
        coherence = 1.0
    else:
        coherence = float(np.linalg.norm(vectors.sum(axis=0)) / total_magnitude)
    coherence = float(np.clip(coherence, 0.0, 1.0))

    if len(vectors) >= 2:
        deltas = np.diff(vectors, axis=0)
        jitter = float(
            math.sqrt(float(np.mean(np.sum(deltas * deltas, axis=1))))
        )
    else:
        jitter = 0.0

    responses = np.array([d.phase_response for d in internal], dtype=np.float64)
    phase_response = float(np.median(responses))
    mean_combined = float(np.mean([d.combined for d in internal]))
    inverse_dt = 1.0 / dt if dt > 0 else 0.0
    pan_speed = float(np.median(magnitudes)) * inverse_dt
    motion_per_second = mean_combined * inverse_dt
    return pan_speed, coherence, jitter, phase_response, motion_per_second


def aggregate_shot_metrics(
    shot: list[dict],
    distances: list,
    min_phase_response: float = 0.05,
) -> dict:
    """Aggregate frame metrics for one shot and compute motion statistics.

    ``instability`` keeps the v0.1.0 definition (mean combined distance) so legacy
    comparisons stay valid. The translation-derived metrics are additional evidence and
    never replace it silently: ``stability_source`` records which one is used.
    """
    first = shot[0]["metrics"]
    aggregated: dict[str, float] = {}
    for key, strategy in AGGREGATION.items():
        if key not in first:
            continue
        values = np.array([s["metrics"][key] for s in shot], dtype=np.float64)
        aggregated[key] = float(np.mean(values) if strategy == "mean" else np.median(values))

    internal = _internal_distances(shot, distances)
    dt = _median_dt(shot)
    if internal:
        aggregated["instability"] = float(
            np.mean([distance.combined for distance in internal])
        )
    else:
        aggregated["instability"] = 0.0

    pan_speed, coherence, jitter, phase_response, motion_per_second = _translation_stats(
        internal, dt
    )
    aggregated["pan_speed_px_s"] = pan_speed
    aggregated["translation_consistency"] = coherence
    aggregated["jitter_px"] = jitter
    aggregated["phase_response"] = phase_response
    aggregated["motion_per_second"] = motion_per_second

    aggregated["clip_total"] = float(
        min(1.0, aggregated.get("black_clip", 0.0) + aggregated.get("white_clip", 0.0))
    )
    mean_luminance = aggregated.get("mean", 0.5)
    aggregated["midtone_dev"] = float(min(1.0, abs(mean_luminance - 0.5) * 2.0))
    aggregated["dynamic_range"] = float(
        max(0.0, aggregated.get("p95", 0.0) - aggregated.get("p05", 0.0))
    )

    aggregated["sample_count"] = float(len(shot))
    aggregated["median_dt_seconds"] = float(dt)

    translation_usable = (
        phase_response >= min_phase_response and len(internal) >= 2
    )
    aggregated["translation_usable"] = 1.0 if translation_usable else 0.0
    aggregated["stability_source"] = (
        "translation" if translation_usable else "instability_fallback"
    )
    return aggregated


def aggregation_strategy() -> dict[str, str]:
    """Expose the aggregation strategy for the audit JSON."""
    return dict(AGGREGATION)


def motion_aggregation_strategy() -> dict[str, str]:
    """Expose the motion aggregation strategy for the audit JSON."""
    return dict(MOTION_AGGREGATION)

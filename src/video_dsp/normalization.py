"""Component normalization with an explicit, auditable provenance per entry.

Two methods are supported:

``per_video_percentile`` (default)
    Bounds come from the p5/p95 of the shot values of *this* video, after the declared
    transform. This adapts to exposure, codec and content without any learned model.
    When there are too few shots or the spread is degenerate, the method falls back to
    the config ranges and *records the fallback*, never silently.

``absolute``
    Bounds come from ``config["ranges"]``. This reproduces the v0.1.0 behaviour and makes
    ``balanced_v1`` a genuine legacy preset.

Target bands are always absolute: they express a preference ("this much motion"), not a
property of the distribution, so a percentile would be meaningless.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .metrics_spec import DIMENSION_ORDER, DIMENSIONS, FIELD_CATALOG


def apply_transform(value: float, transform: str) -> float:
    """Apply the declared monotonic transform used before normalization."""
    if transform == "log1p":
        return float(math.log1p(max(float(value), 0.0)))
    return float(value)


def inverse_transform(value: float, transform: str) -> float:
    if transform == "log1p":
        return float(math.expm1(float(value)))
    return float(value)


def percentile_bounds(
    values: list[float], low_percentile: float, high_percentile: float
) -> tuple[float, float, float]:
    """Return ``(low, high, median)`` using linear-interpolated percentiles."""
    array = np.asarray(values, dtype=np.float64)
    low, median, high = np.percentile(
        array, [low_percentile, 50.0, high_percentile]
    )
    return float(low), float(high), float(median)


def _absent(reason: str) -> dict[str, Any]:
    return {"normalized": 0.0, "reason": reason, "available": False}


def build_normalization(
    shots: list[dict], config: dict
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build the normalization table for every dimension component.

    ``shots`` is the list of shot records, each with a ``metrics`` dict. The table is
    independent of the preference weights, so the UI can re-weight without recomputing
    the bounds.
    """
    settings = config["normalization"]
    method = settings["method"]
    low_percentile = float(settings["low_percentile"])
    high_percentile = float(settings["high_percentile"])
    min_shots = int(settings["min_shots"])
    min_relative_spread = float(settings["min_relative_spread"])
    ranges = config["ranges"]
    targets = config["targets"]

    table: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for dimension in DIMENSION_ORDER:
        spec = DIMENSIONS[dimension]
        entry: dict[str, Any] = {
            "label_es": spec["label_es"],
            "description_es": spec["description_es"],
            "components": {},
            "fallback_components": {},
        }
        for group_key, components in (
            ("components", spec["components"]),
            ("fallback_components", spec["fallback_components"]),
        ):
            for component in components:
                record = _component_entry(
                    component=component,
                    dimension=dimension,
                    shots=shots,
                    method=method,
                    ranges=ranges,
                    targets=targets,
                    low_percentile=low_percentile,
                    high_percentile=high_percentile,
                    min_shots=min_shots,
                    min_relative_spread=min_relative_spread,
                )
                entry[group_key][component["id"]] = record
                if record.get("fallback_reason"):
                    warnings.append(
                        f"normalization_fallback:{dimension}.{component['id']}"
                        f" ({record['fallback_reason']})"
                    )
        table[dimension] = entry
    return table, _dedupe(warnings)


def _component_entry(
    *,
    component: dict[str, Any],
    dimension: str,
    shots: list[dict],
    method: str,
    ranges: dict[str, dict[str, float]],
    targets: dict[str, dict[str, float]],
    low_percentile: float,
    high_percentile: float,
    min_shots: int,
    min_relative_spread: float,
) -> dict[str, Any]:
    metric = component["metric"]
    transform = component.get("transform", "identity")
    mode = component["mode"]
    catalog = FIELD_CATALOG.get(metric, {})

    base: dict[str, Any] = {
        "metric": metric,
        "label_es": catalog.get("label_es", metric),
        "unit_es": catalog.get("unit_es", ""),
        "description_es": catalog.get("description_es", ""),
        "aggregation": catalog.get("aggregation", ""),
        "mode": mode,
        "transform": transform,
        "weight": float(component["weight"]),
        "calibration": "initial_uncalibrated",
    }

    if mode == "band":
        band = targets.get(component["band_key"])
        if band is None:
            raise KeyError(f"missing target band for {component['band_key']}")
        base.update(
            {
                "method": "absolute_band",
                "low": float(band["low"]),
                "high": float(band["high"]),
                "falloff": float(band.get("falloff", 0.0)),
                "source": "target_band",
            }
        )
        if base["falloff"] <= 0:
            raise ValueError(f"target band {component['band_key']} needs a positive falloff")
        return base

    range_key = component["range_key"]
    absolute = ranges[range_key]
    values = [
        float(shot["metrics"][metric])
        for shot in shots
        if metric in shot.get("metrics", {})
    ]

    use_absolute = method == "absolute" or bool(component.get("force_absolute"))
    fallback_reason: str | None = None
    source = "config_absolute"

    if not use_absolute:
        if len(values) < min_shots:
            fallback_reason = f"too_few_shots ({len(values)} < {min_shots})"
        else:
            transformed = np.asarray(
                [apply_transform(value, transform) for value in values],
                dtype=np.float64,
            )
            low, high, median = percentile_bounds(
                transformed.tolist(), low_percentile, high_percentile
            )
            spread = high - low
            scale = max(abs(median), 1e-6)
            if spread <= 1e-9 or spread < min_relative_spread * scale:
                fallback_reason = (
                    f"degenerate_spread (p{low_percentile:g}={low:.4f}, "
                    f"p{high_percentile:g}={high:.4f})"
                )
            else:
                base.update(
                    {
                        "method": "percentile",
                        "low": low,
                        "high": high,
                        "source": "per_video_p5_p95",
                        "shots_used": len(values),
                        "median": median,
                    }
                )
                return base

    low = apply_transform(absolute["low"], transform)
    high = apply_transform(absolute["high"], transform)
    base.update(
        {
            "method": "absolute",
            "low": low,
            "high": high,
            "source": source,
            "fallback_reason": fallback_reason,
            "absolute_range_raw": {
                "low": float(absolute["low"]),
                "high": float(absolute["high"]),
            },
            "shots_used": len(values),
        }
    )
    return base


def normalize_value(value: float, entry: dict[str, Any]) -> float:
    """Normalize one metric value with the bounds recorded in ``entry``."""
    if value is None:
        raise ValueError("cannot normalize a missing value")
    mode = entry["mode"]
    transformed = apply_transform(value, entry.get("transform", "identity"))

    if mode == "band":
        low = float(entry["low"])
        high = float(entry["high"])
        falloff = float(entry["falloff"])
        if low <= transformed <= high:
            return 1.0
        if transformed < low:
            return float(np.clip(1.0 - (low - transformed) / falloff, 0.0, 1.0))
        return float(np.clip(1.0 - (transformed - high) / falloff, 0.0, 1.0))

    low = float(entry["low"])
    high = float(entry["high"])
    if high <= low:
        return 1.0 if transformed >= high else 0.0
    if mode == "higher_better":
        return float(np.clip((transformed - low) / (high - low), 0.0, 1.0))
    if mode == "lower_better":
        return float(np.clip((high - transformed) / (high - low), 0.0, 1.0))
    raise ValueError(f"unknown normalization mode: {mode}")


def dimension_scores(
    metrics: dict[str, Any], table: dict[str, dict[str, Any]]
) -> tuple[dict[str, float], dict[str, dict[str, float]], list[str]]:
    """Score all dimensions for one shot.

    Returns ``(dimension_scores, component_scores, warnings)``. Missing metrics are not
    hidden: the component is dropped, the dimension renormalizes over what is available,
    and a warning names the missing metric.
    """
    dimensions: dict[str, float] = {}
    components_out: dict[str, dict[str, float]] = {}
    warnings: list[str] = []

    for dimension in DIMENSION_ORDER:
        entry = table[dimension]
        use_fallback = (
            dimension == "stability"
            and float(metrics.get("translation_usable", 0.0)) < 0.5
            and bool(entry.get("fallback_components"))
        )
        group = entry["fallback_components"] if use_fallback else entry["components"]
        weighted = 0.0
        weight_total = 0.0
        scored: dict[str, float] = {}
        for component_id, component in group.items():
            metric = component["metric"]
            if metric not in metrics:
                warnings.append(f"metric_missing:{dimension}.{component_id} ({metric})")
                continue
            value = normalize_value(float(metrics[metric]), component)
            scored[component_id] = value
            weighted += float(component["weight"]) * value
            weight_total += float(component["weight"])
        if weight_total <= 0:
            dimensions[dimension] = 0.0
            warnings.append(f"dimension_unscorable:{dimension}")
        else:
            dimensions[dimension] = float(weighted / weight_total)
        components_out[dimension] = scored
        if dimension == "stability":
            components_out[dimension]["__source"] = (
                "instability_fallback" if use_fallback else "translation"
            )
    return dimensions, components_out, warnings


def combined_score(
    dimensions: dict[str, float], weights: dict[str, float]
) -> tuple[float, dict[str, float]]:
    """Weighted blend of dimensions, renormalized over the active weights.

    A dimension with zero weight is excluded from the sum but still reported, so the UI
    can show it without letting it affect the total.
    """
    effective = {
        name: float(weights.get(name, 0.0)) for name in DIMENSION_ORDER
    }
    total_weight = sum(value for value in effective.values() if value > 0)
    if total_weight <= 0:
        raise ValueError("at least one dimension weight must be positive")
    normalized_weights = {
        name: (value / total_weight if value > 0 else 0.0)
        for name, value in effective.items()
    }
    score = sum(
        normalized_weights[name] * dimensions[name] for name in DIMENSION_ORDER
    )
    return float(score), normalized_weights


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

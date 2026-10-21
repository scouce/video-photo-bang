"""Pure selection service: shot records -> dimensions, gates, floor and top-N.

This module has no file or video dependencies. It is the single source of truth used by
the CLI, the Streamlit client and the tests, so a re-weighting in the UI and a CLI run
with the same config produce byte-identical numbers.

Pipeline:

1. ``build_shot_records`` turns shot sample lists into flat, JSON-ready records with a
   histogram signature for diversity.
2. ``rank`` normalizes components (per video or absolute), blends dimensions with the
   active weights, applies gates and the quality floor, then selects the top-N with a
   maximal-marginal-relevance rule that penalizes near-duplicates.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .aggregation import aggregate_shot_metrics
from .metrics_spec import DIMENSION_ORDER
from .normalization import build_normalization, combined_score, dimension_scores
from .shot_detection import bhattacharyya_similarity, shot_histogram_signature

STATUS_SELECTED = "selected"
STATUS_PASSING_UNSELECTED = "passing_unselected"
STATUS_REJECTED_GATE = "rejected_gate"
STATUS_REJECTED_FLOOR = "rejected_floor"

EXCLUDED_METRIC_KEYS = {"histogram", "motion_gray"}


def build_shot_records(
    shots: list[list[dict]], distances: list, config: dict
) -> list[dict]:
    """Build flat shot records from the sample lists produced by the detector."""
    records: list[dict] = []
    min_phase_response = float(config.get("motion", {}).get("min_phase_response", 0.05))
    for position, shot in enumerate(shots, start=1):
        aggregated = aggregate_shot_metrics(shot, distances, min_phase_response)
        duration = float(shot[-1]["timestamp_seconds"] - shot[0]["timestamp_seconds"])
        aggregated["duration_seconds"] = duration
        signature = shot_histogram_signature(shot)
        metrics = {
            key: float(value)
            for key, value in aggregated.items()
            if key not in EXCLUDED_METRIC_KEYS and isinstance(value, (int, float))
        }
        representative = max(
            shot, key=lambda sample: sample["metrics"]["variance_laplacian"]
        )
        records.append(
            {
                "shot_id": f"shot_{position:04d}",
                "start_time_seconds": float(shot[0]["timestamp_seconds"]),
                "end_time_seconds": float(shot[-1]["timestamp_seconds"]),
                "duration_seconds": duration,
                "sample_count": len(shot),
                "first_frame_index": int(shot[0]["frame_index"]),
                "last_frame_index": int(shot[-1]["frame_index"]),
                "selected_frame_index": int(representative["frame_index"]),
                "selected_frame_timestamp": float(representative["timestamp_seconds"]),
                "selected_frame_rule": "max_variance_laplacian",
                "metrics": metrics,
                "histogram_signature": [float(value) for value in signature],
                "warnings": [],
            }
        )
    return records


def resolve_preferences(config: dict) -> dict[str, Any]:
    """Extract the subset of config that affects ranking, with effective weights.

    The weights are always recomputed from ``score_weights`` so that a caller which
    edits them after ``load_config`` (the UI does exactly that on every slider move)
    gets the weights it just set, not the ones baked in at load time.
    """
    raw = config["score_weights"]
    total = sum(float(raw[name]) for name in DIMENSION_ORDER)
    if total <= 0:
        raise ValueError("at least one dimension weight must be positive")
    weights = {name: float(raw[name]) / total for name in DIMENSION_ORDER}
    return {
        "preset": config.get("preset", "custom"),
        "score_weights": {name: float(weights[name]) for name in DIMENSION_ORDER},
        "hard_gates": dict(config["hard_gates"]),
        "quality_floor": dict(config.get("quality_floor", {"enabled": False})),
        "diversity": dict(config.get("diversity", {"enabled": False})),
        "top_n": int(config.get("top_n", 10)),
        "normalization_method": config["normalization"]["method"],
    }


def evaluate_gates(
    metrics: dict[str, float],
    dimensions: dict[str, float],
    gates: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply every hard gate and return the failures, each with value and threshold."""
    failures: list[dict[str, Any]] = []

    def fail(gate: str, value: float, threshold: float, interpretation: str) -> None:
        failures.append(
            {
                "gate": gate,
                "value": float(value),
                "threshold": float(threshold),
                "interpretation": interpretation,
            }
        )

    duration = float(metrics["duration_seconds"])
    if "min_shot_duration_s" in gates and duration < gates["min_shot_duration_s"]:
        fail(
            "min_shot_duration",
            duration,
            gates["min_shot_duration_s"],
            "Shot too short for selection.",
        )
    if "max_shot_duration_s" in gates and duration > gates["max_shot_duration_s"]:
        fail(
            "max_shot_duration",
            duration,
            gates["max_shot_duration_s"],
            "Shot too long for selection.",
        )
    if "max_black_clip" in gates and metrics["black_clip"] > gates["max_black_clip"]:
        fail(
            "max_black_clip",
            metrics["black_clip"],
            gates["max_black_clip"],
            "Too many crushed-black pixels.",
        )
    if "max_white_clip" in gates and metrics["white_clip"] > gates["max_white_clip"]:
        fail(
            "max_white_clip",
            metrics["white_clip"],
            gates["max_white_clip"],
            "Too many blown-highlight pixels.",
        )
    if (
        "min_sharpness_score" in gates
        and dimensions["sharpness"] < gates["min_sharpness_score"]
    ):
        fail(
            "min_sharpness_score",
            dimensions["sharpness"],
            gates["min_sharpness_score"],
            "Shot is not sharp enough on the combined sharpness measure.",
        )
    if "max_instability" in gates and metrics["instability"] > gates["max_instability"]:
        fail(
            "max_instability",
            metrics["instability"],
            gates["max_instability"],
            "Shot changes too much internally (motion or flicker).",
        )
    if "max_jitter_px" in gates and metrics.get("jitter_px", 0.0) > gates["max_jitter_px"]:
        fail(
            "max_jitter_px",
            metrics["jitter_px"],
            gates["max_jitter_px"],
            "Inter-frame translation is too erratic (handheld shake).",
        )
    return failures


def _similarity_matrix(shots: list[dict]) -> np.ndarray:
    count = len(shots)
    matrix = np.eye(count, dtype=np.float64)
    signatures = [
        np.asarray(shot["histogram_signature"], dtype=np.float64) for shot in shots
    ]
    for left in range(count):
        for right in range(left + 1, count):
            similarity = bhattacharyya_similarity(signatures[left], signatures[right])
            matrix[left, right] = similarity
            matrix[right, left] = similarity
    return matrix


def mmr_select(
    candidates: list[dict],
    top_n: int,
    diversity_weight: float,
    similarity: np.ndarray,
    index_of: dict[str, int],
) -> tuple[list[dict], list[dict]]:
    """Maximal marginal relevance selection with a deterministic tie-break.

    Returns ``(selected, trace)``. ``trace`` records the penalty applied at each step so
    the UI can explain why a higher-scoring shot was skipped.
    """
    if top_n <= 0 or not candidates:
        return [], []
    weight = float(np.clip(diversity_weight, 0.0, 1.0))
    relevance_weight = 1.0 - weight

    remaining = list(candidates)
    selected: list[dict] = []
    trace: list[dict] = []

    while remaining and len(selected) < top_n:
        best_shot: dict | None = None
        best_key: tuple[float, float, str] | None = None
        best_similarity = 0.0
        for shot in remaining:
            if selected:
                position = index_of[shot["shot_id"]]
                similarity_value = max(
                    float(similarity[position, index_of[chosen["shot_id"]]])
                    for chosen in selected
                )
            else:
                similarity_value = 0.0
            objective = (
                relevance_weight * float(shot["total_score"])
                - weight * similarity_value
            )
            key = (-objective, float(shot["start_time_seconds"]), shot["shot_id"])
            if best_key is None or key < best_key:
                best_key = key
                best_shot = shot
                best_similarity = similarity_value
        assert best_shot is not None
        objective = (
            relevance_weight * float(best_shot["total_score"])
            - weight * best_similarity
        )
        trace.append(
            {
                "shot_id": best_shot["shot_id"],
                "mmr_objective": float(objective),
                "similarity_to_selected": float(best_similarity),
                "total_score": float(best_shot["total_score"]),
            }
        )
        selected.append(best_shot)
        remaining.remove(best_shot)
    return selected, trace


def rank(
    shot_records: list[dict],
    config: dict,
    normalization: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score, gate, floor and select. Pure: same inputs -> same output."""
    preferences = resolve_preferences(config)
    warnings: list[str] = []
    if normalization is None:
        table, normalization_warnings = build_normalization(shot_records, config)
        warnings.extend(normalization_warnings)
    else:
        table = normalization

    scored: list[dict] = []
    for record in shot_records:
        dimensions, components, dimension_warnings = dimension_scores(
            record["metrics"], table
        )
        total, effective_weights = combined_score(dimensions, preferences["score_weights"])
        failures = evaluate_gates(
            record["metrics"], dimensions, preferences["hard_gates"]
        )
        warnings.extend(
            f"{record['shot_id']}: {warning}" for warning in dimension_warnings
        )
        scored.append(
            {
                **record,
                "dimension_scores": dimensions,
                "component_scores": components,
                "total_score": total,
                "score_weights_effective": effective_weights,
                "failed_gates": failures,
                "gate_passed": not failures,
                "stability_source": record["metrics"].get(
                    "stability_source", "translation"
                ),
                # Reset every derived field: a record that came from an earlier ranking
                # still carries its old rank, and leaving it would make a re-weight look
                # like it kept a shot that it actually dropped.
                "rank": None,
                "plain_rank": None,
                "mmr_objective": None,
                "similarity_to_selected": None,
            }
        )

    floor = preferences["quality_floor"]
    floor_enabled = bool(floor.get("enabled", False))
    floor_value = float(floor.get("min_total_score", 0.0))

    passing: list[dict] = []
    for shot in scored:
        if shot["failed_gates"]:
            shot["status"] = STATUS_REJECTED_GATE
            shot["selection_reason"] = "failed_gates"
        elif floor_enabled and shot["total_score"] < floor_value:
            shot["status"] = STATUS_REJECTED_FLOOR
            shot["selection_reason"] = "below_quality_floor"
        else:
            shot["status"] = STATUS_PASSING_UNSELECTED
            shot["selection_reason"] = "eligible"
            passing.append(shot)

    diversity = preferences["diversity"]
    diversity_enabled = bool(diversity.get("enabled", True))
    diversity_weight = float(diversity.get("weight", 0.0)) if diversity_enabled else 0.0

    ranked_passing = sorted(
        passing,
        key=lambda shot: (-shot["total_score"], shot["start_time_seconds"]),
    )
    index_of = {shot["shot_id"]: index for index, shot in enumerate(ranked_passing)}
    similarity = _similarity_matrix(ranked_passing) if ranked_passing else np.zeros((0, 0))

    selected, trace = mmr_select(
        ranked_passing,
        preferences["top_n"],
        diversity_weight,
        similarity,
        index_of,
    )
    trace_by_id = {item["shot_id"]: item for item in trace}

    for position, shot in enumerate(selected, start=1):
        shot["rank"] = position
        shot["status"] = STATUS_SELECTED
        shot["selection_reason"] = "selected"
        detail = trace_by_id.get(shot["shot_id"], {})
        shot["mmr_objective"] = detail.get("mmr_objective")
        shot["similarity_to_selected"] = detail.get("similarity_to_selected")

    plain_top = ranked_passing[: preferences["top_n"]]
    for position, shot in enumerate(plain_top, start=1):
        shot["plain_rank"] = position
    selected_ids = {shot["shot_id"] for shot in selected}
    displaced = [
        shot
        for shot in plain_top
        if shot["shot_id"] not in selected_ids
    ]

    summary = {
        "total_shots": len(scored),
        "passed_gates": sum(1 for shot in scored if shot["gate_passed"]),
        "selected": len(selected),
        "passing_unselected": sum(
            1 for shot in scored if shot["status"] == STATUS_PASSING_UNSELECTED
        ),
        "rejected_gate": sum(
            1 for shot in scored if shot["status"] == STATUS_REJECTED_GATE
        ),
        "rejected_floor": sum(
            1 for shot in scored if shot["status"] == STATUS_REJECTED_FLOOR
        ),
        "diversity_enabled": diversity_enabled,
        "diversity_weight": diversity_weight,
        "top_n": preferences["top_n"],
        "preset": preferences["preset"],
        "quality_floor": {"enabled": floor_enabled, "min_total_score": floor_value},
        "displaced_by_diversity": [shot["shot_id"] for shot in displaced],
        "top_score": max((shot["total_score"] for shot in selected), default=0.0),
        "warnings": _dedupe(warnings),
    }

    return {
        "shots": scored,
        "selected": selected,
        "displaced_by_diversity": displaced,
        "normalization": table,
        "score_weights_effective": preferences["score_weights"],
        "preferences": preferences,
        "summary": summary,
        "warnings": summary["warnings"],
    }


def recompute(
    shot_records: list[dict], config: dict
) -> dict[str, Any]:
    """Convenience wrapper that rebuilds the normalization table from scratch."""
    table, warnings = build_normalization(shot_records, config)
    result = rank(shot_records, config, normalization=table)
    result["warnings"] = _dedupe(list(result["warnings"]) + warnings)
    result["summary"]["warnings"] = result["warnings"]
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

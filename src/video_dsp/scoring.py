"""Legacy v0.1.0 scoring path. **Not used by the pipeline.**

The live scoring path is :mod:`video_dsp.selection_service` (eight dimensions, per-video
normalization, gates, quality floor, MMR). This module is kept only so the exact v0.1.0
four-dimension absolute formula stays readable while ``balanced_v1`` is still supported for
reproducibility. Do not import it from the CLI or the client; changing it changes nothing
in any output.

Removal is tracked in ``handoff/next_iterations.md``.
"""

from __future__ import annotations

import numpy as np

from .aggregation import aggregate_shot_metrics


def normalize_higher_better(value: float, low: float, high: float) -> float:
    """Map a metric where higher is better onto ``[0, 1]``."""
    if high <= low:
        return 1.0 if value >= high else 0.0
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def normalize_lower_better(value: float, low: float, high: float) -> float:
    """Map a metric where lower is better onto ``[0, 1]``."""
    if high <= low:
        return 1.0 if value <= low else 0.0
    return float(np.clip((high - value) / (high - low), 0.0, 1.0))


def compute_category_scores(
    aggregated: dict, config: dict
) -> tuple[dict[str, float], dict[str, float]]:
    """Compute category scores and the normalized metrics they derive from."""
    ranges = config["ranges"]
    normalized = {
        "variance_laplacian": normalize_higher_better(
            aggregated["variance_laplacian"], **ranges["variance_laplacian"]
        ),
        "tenengrad": normalize_higher_better(
            aggregated["tenengrad"], **ranges["tenengrad"]
        ),
        "luminance_std": normalize_higher_better(
            aggregated["std"], **ranges["luminance_std"]
        ),
        "stability": normalize_lower_better(
            aggregated["instability"], **ranges["instability"]
        ),
        "mean_luminance": float(aggregated["mean"]),
        "black_clip": float(aggregated["black_clip"]),
        "white_clip": float(aggregated["white_clip"]),
    }

    sharpness = 0.5 * normalized["variance_laplacian"] + 0.5 * normalized["tenengrad"]
    clip_total = min(1.0, aggregated["black_clip"] + aggregated["white_clip"])
    midtone = 1.0 - min(1.0, abs(aggregated["mean"] - 0.5) * 2.0)
    exposure = 0.5 * (1.0 - clip_total) + 0.5 * midtone
    contrast = normalized["luminance_std"]
    stability = normalized["stability"]

    category_scores = {
        "sharpness": float(sharpness),
        "exposure": float(exposure),
        "contrast": float(contrast),
        "stability": float(stability),
    }
    return category_scores, normalized


def weighted_total(category_scores: dict[str, float], weights: dict[str, float]) -> float:
    return float(sum(weights[key] * category_scores[key] for key in weights))


def apply_hard_gates(
    aggregated: dict, category_scores: dict[str, float], gates: dict
) -> tuple[bool, list[dict]]:
    """Return ``(passed, failed_gates)`` for one shot."""
    failed: list[dict] = []

    def fail(gate: str, value: float, threshold: float, interpretation: str) -> None:
        failed.append(
            {
                "gate": gate,
                "value": float(value),
                "threshold": float(threshold),
                "interpretation": interpretation,
            }
        )

    duration = aggregated["duration_seconds"]
    if duration < gates["min_shot_duration_s"]:
        fail(
            "min_shot_duration",
            duration,
            gates["min_shot_duration_s"],
            "Shot too short for MVP selection.",
        )
    if duration > gates["max_shot_duration_s"]:
        fail(
            "max_shot_duration",
            duration,
            gates["max_shot_duration_s"],
            "Shot too long for MVP selection.",
        )
    if aggregated["black_clip"] > gates["max_black_clip"]:
        fail(
            "max_black_clip",
            aggregated["black_clip"],
            gates["max_black_clip"],
            "Too many crushed-black pixels.",
        )
    if aggregated["white_clip"] > gates["max_white_clip"]:
        fail(
            "max_white_clip",
            aggregated["white_clip"],
            gates["max_white_clip"],
            "Too many blown-highlight pixels.",
        )
    if category_scores["sharpness"] < gates["min_sharpness_score"]:
        fail(
            "min_sharpness_score",
            category_scores["sharpness"],
            gates["min_sharpness_score"],
            "Shot is not sharp enough on the combined sharpness measure.",
        )
    if aggregated["instability"] > gates["max_instability"]:
        fail(
            "max_instability",
            aggregated["instability"],
            gates["max_instability"],
            "Shot changes too much internally (motion or flicker).",
        )
    return not failed, failed


def choose_representative_frame(shot: list[dict]) -> dict:
    """Pick the sharpest sampled frame as the representative frame."""
    return max(shot, key=lambda sample: sample["metrics"]["variance_laplacian"])


def score_shot(
    shot: list[dict], distances: list, config: dict, shot_id: str
) -> dict:
    """Build a fully auditable scored-shot record."""
    aggregated = aggregate_shot_metrics(shot, distances)
    duration = float(shot[-1]["timestamp_seconds"] - shot[0]["timestamp_seconds"])
    aggregated["duration_seconds"] = duration

    category_scores, normalized = compute_category_scores(aggregated, config)
    total = weighted_total(category_scores, config["score_weights"])
    passed, failed_gates = apply_hard_gates(
        aggregated, category_scores, config["hard_gates"]
    )
    representative = choose_representative_frame(shot)

    return {
        "shot_id": shot_id,
        "start_time_seconds": float(shot[0]["timestamp_seconds"]),
        "end_time_seconds": float(shot[-1]["timestamp_seconds"]),
        "duration_seconds": duration,
        "sample_count": len(shot),
        "gate_passed": passed,
        "failed_gates": failed_gates,
        "total_score": total if passed else 0.0,
        "category_scores": category_scores,
        "metrics_raw": {
            key: value
            for key, value in aggregated.items()
            if key not in {"duration_seconds"}
        },
        "metrics_normalized": normalized,
        "selected_frame_timestamp": float(representative["timestamp_seconds"]),
        "selected_frame_index": int(representative["frame_index"]),
        "selected_frame_metrics": {
            key: value
            for key, value in representative["metrics"].items()
            if key != "histogram"
        },
        "warnings": [],
        "reasoning": _build_reasoning(passed, category_scores, failed_gates),
    }


def _build_reasoning(
    passed: bool, category_scores: dict[str, float], failed_gates: list[dict]
) -> str:
    if not passed:
        reasons = "; ".join(gate["interpretation"] for gate in failed_gates)
        return f"Rejected: {reasons}"
    return (
        "Passed gates. Category scores — "
        f"sharpness={category_scores['sharpness']:.3f}, "
        f"exposure={category_scores['exposure']:.3f}, "
        f"contrast={category_scores['contrast']:.3f}, "
        f"stability={category_scores['stability']:.3f}."
    )


def rank_shots(scored_shots: list[dict], top_n: int) -> list[dict]:
    """Rank passing shots by score desc, then start time asc; attach ``rank``."""
    passing = [shot for shot in scored_shots if shot["gate_passed"]]
    ordered = sorted(
        passing, key=lambda shot: (-shot["total_score"], shot["start_time_seconds"])
    )
    selected = ordered[: max(0, top_n)]
    for position, shot in enumerate(selected, start=1):
        shot["rank"] = position
    return selected

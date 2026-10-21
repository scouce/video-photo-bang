"""Evaluation of a selection against human labels.

The goal is not to train anything. It is to answer four questions with numbers:

1. Do the shots we select match the shots a human keeps? (precision / recall / NDCG)
2. Which gate is rejecting shots a human would keep? (false rejects per gate)
3. Which dimension actually separates "good" from "bad" for this video? (separation)
4. Do the weights order two shots the same way a human does? (pairwise accuracy)
"""

from __future__ import annotations

import math
from typing import Any

from .labels import coverage, shot_labels
from .metrics_spec import DIMENSION_ORDER

NEGATIVE_VERDICTS = {"reject"}


def _is_positive(entry: dict[str, Any] | None) -> bool:
    return bool(entry) and entry.get("verdict") == "keep"


def _is_negative(entry: dict[str, Any] | None) -> bool:
    return bool(entry) and entry.get("verdict") in NEGATIVE_VERDICTS


def ndcg_at_k(relevances: list[float], k: int) -> float | None:
    """Normalized discounted cumulative gain with exponential gain."""
    if k <= 0 or not relevances:
        return None
    actual = relevances[:k]
    dcg = sum(
        (2**relevance - 1) / math.log2(index + 2)
        for index, relevance in enumerate(actual)
    )
    ideal = sorted(relevances, reverse=True)[:k]
    idcg = sum(
        (2**relevance - 1) / math.log2(index + 2)
        for index, relevance in enumerate(ideal)
    )
    if idcg <= 0:
        return None
    return float(dcg / idcg)


def _confusion(
    shots: list[dict[str, Any]], labels_by_id: dict[str, dict[str, Any]]
) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for shot in shots:
        entry = labels_by_id.get(shot["shot_id"])
        if entry is None:
            continue
        row = matrix.setdefault(shot["status"], {"keep": 0, "reject": 0, "unsure": 0})
        verdict = entry.get("verdict", "unsure")
        row[verdict] = row.get(verdict, 0) + 1
    return matrix


def _gate_diagnostics(
    shots: list[dict[str, Any]], labels_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    diagnostics: dict[str, dict[str, Any]] = {}
    for shot in shots:
        entry = labels_by_id.get(shot["shot_id"])
        if entry is None:
            continue
        for failure in shot.get("failed_gates", []):
            gate = failure["gate"]
            record = diagnostics.setdefault(
                gate,
                {
                    "gate": gate,
                    "labeled_shots_failing": 0,
                    "false_rejects": 0,
                    "true_rejects": 0,
                    "threshold": failure.get("threshold"),
                },
            )
            record["labeled_shots_failing"] += 1
            if _is_positive(entry):
                record["false_rejects"] += 1
            elif _is_negative(entry):
                record["true_rejects"] += 1
    return sorted(
        diagnostics.values(), key=lambda item: (-item["false_rejects"], item["gate"])
    )


def _dimension_separation(
    shots: list[dict[str, Any]], labels_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    keeps = [
        shot["dimension_scores"]
        for shot in shots
        if _is_positive(labels_by_id.get(shot["shot_id"]))
    ]
    rejects = [
        shot["dimension_scores"]
        for shot in shots
        if _is_negative(labels_by_id.get(shot["shot_id"]))
    ]
    separation: list[dict[str, Any]] = []
    for dimension in DIMENSION_ORDER:
        keep_mean = (
            sum(scores[dimension] for scores in keeps) / len(keeps) if keeps else None
        )
        reject_mean = (
            sum(scores[dimension] for scores in rejects) / len(rejects)
            if rejects
            else None
        )
        gap = (
            keep_mean - reject_mean
            if keep_mean is not None and reject_mean is not None
            else None
        )
        separation.append(
            {
                "dimension": dimension,
                "mean_keep": keep_mean,
                "mean_reject": reject_mean,
                "gap": gap,
                "separates": bool(gap is not None and gap > 0.05),
            }
        )
    return sorted(
        separation,
        key=lambda item: (-(item["gap"] if item["gap"] is not None else -9.0)),
    )


def _pairwise_accuracy(
    pairs: list[dict[str, Any]], score_by_id: dict[str, float]
) -> dict[str, Any]:
    compared = 0
    correct = 0
    ties = 0
    for pair in pairs:
        a_score = score_by_id.get(pair["a"])
        b_score = score_by_id.get(pair["b"])
        if a_score is None or b_score is None:
            continue
        winner = pair["winner"]
        if winner == "tie":
            ties += 1
            continue
        compared += 1
        predicted = "a" if a_score > b_score else "b"
        if a_score == b_score:
            predicted = "tie"
        if predicted == winner:
            correct += 1
    return {
        "pairs_compared": compared,
        "pairs_correct": correct,
        "pairs_tied": ties,
        "accuracy": (correct / compared) if compared else None,
    }


def evaluate(
    shots: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    labels: dict[str, Any],
    top_n: int,
) -> dict[str, Any]:
    """Return the evaluation document. Safe to call with empty labels."""
    labels_by_id = shot_labels(labels)
    review = coverage(labels, [shot["shot_id"] for shot in shots])

    labeled_shots = [
        shot for shot in shots if shot["shot_id"] in labels_by_id
    ]
    if not labeled_shots:
        return {
            "status": "insufficient_labels",
            "coverage": review,
            "warnings": [
                "no_shot_labels: annotate at least the top-N and the rejected shots "
                "before the evaluation is meaningful"
            ],
            "metrics": {},
        }

    keeps = [shot for shot in labeled_shots if _is_positive(labels_by_id[shot["shot_id"]])]
    selected_ids = {shot["shot_id"] for shot in selected}
    selected_keeps = [
        shot
        for shot in selected
        if shot["shot_id"] in selected_ids
        and _is_positive(labels_by_id.get(shot["shot_id"]))
    ]

    precision = (len(selected_keeps) / len(selected)) if selected else None
    recall = (len(selected_keeps) / len(keeps)) if keeps else None
    f1 = (
        (2 * precision * recall / (precision + recall))
        if precision and recall and (precision + recall) > 0
        else None
    )

    ordered_relevance = []
    for shot in selected:
        entry = labels_by_id.get(shot["shot_id"])
        if entry is None:
            continue
        ordered_relevance.append(1.0 if _is_positive(entry) else 0.0)
    ndcg = ndcg_at_k(ordered_relevance, top_n)

    score_by_id = {shot["shot_id"]: shot["total_score"] for shot in shots}

    return {
        "status": "ok",
        "coverage": review,
        "metrics": {
            "precision_at_n": precision,
            "recall_keep": recall,
            "f1_keep": f1,
            "ndcg_at_n": ndcg,
            "selected_labeled": len(selected_keeps),
            "keeps_labeled": len(keeps),
            "labeled_shots": len(labeled_shots),
        },
        "confusion": _confusion(shots, labels_by_id),
        "gate_diagnostics": _gate_diagnostics(shots, labels_by_id),
        "dimension_separation": _dimension_separation(shots, labels_by_id),
        "pairwise": _pairwise_accuracy(labels.get("pairs", []), score_by_id),
        "warnings": _evaluation_warnings(review, len(keeps)),
    }


def _evaluation_warnings(review: dict[str, Any], keeps: int) -> list[str]:
    warnings: list[str] = []
    if review["fraction"] < 0.5:
        warnings.append(
            f"low_label_coverage ({review['fraction']:.2f}): metrics are indicative only"
        )
    if keeps == 0:
        warnings.append("no_keep_labels: precision and recall are undefined")
    if review["pairs"] < 10:
        warnings.append(
            f"few_pairwise_labels ({review['pairs']}): weight validation is weak"
        )
    return warnings

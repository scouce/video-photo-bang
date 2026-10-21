"""Tests for the annotation store and the label evaluation."""

import json

import pytest

from video_dsp.evaluation import evaluate, ndcg_at_k
from video_dsp.labels import (
    LABELS_SCHEMA_VERSION,
    LabelsError,
    coverage,
    empty_labels,
    load_labels,
    record_boundary_label,
    record_pair_label,
    record_shot_label,
    save_labels,
    validate_labels,
)


def valid_labels() -> dict:
    labels = empty_labels(annotator="D.A.")
    record_shot_label(labels, shot_id="shot_0001", verdict="keep")
    record_shot_label(
        labels, shot_id="shot_0002", verdict="reject", reason="blur"
    )
    return labels


def test_empty_labels_are_valid():
    labels = empty_labels()
    assert labels["schema_version"] == LABELS_SCHEMA_VERSION
    assert validate_labels(labels) == []


def test_invalid_verdict_is_rejected():
    labels = empty_labels()
    labels["shots"].append({"shot_id": "shot_0001", "verdict": "maybe"})
    errors = validate_labels(labels)
    assert any("invalid verdict" in error for error in errors)


def test_invalid_reason_is_rejected():
    labels = empty_labels()
    labels["shots"].append(
        {"shot_id": "shot_0001", "verdict": "reject", "reason": "ugly"}
    )
    errors = validate_labels(labels)
    assert any("invalid reason" in error for error in errors)


def test_duplicate_shot_labels_are_rejected():
    labels = empty_labels()
    labels["shots"].append({"shot_id": "shot_0001", "verdict": "keep"})
    labels["shots"].append({"shot_id": "shot_0001", "verdict": "reject"})
    errors = validate_labels(labels)
    assert any("duplicate shot label" in error for error in errors)


def test_record_shot_label_upserts():
    labels = valid_labels()
    record_shot_label(labels, shot_id="shot_0002", verdict="keep")
    entries = [entry for entry in labels["shots"] if entry["shot_id"] == "shot_0002"]
    assert len(entries) == 1
    assert entries[0]["verdict"] == "keep"


def test_record_invalid_reason_raises():
    labels = empty_labels()
    with pytest.raises(LabelsError):
        record_shot_label(
            labels, shot_id="shot_0001", verdict="reject", reason="not_a_reason"
        )


def test_boundary_and_pair_labels():
    labels = empty_labels()
    record_boundary_label(
        labels, boundary_id="boundary_0001", verdict="false_positive"
    )
    record_pair_label(labels, a="shot_0001", b="shot_0002", winner="a")
    assert validate_labels(labels) == []
    assert labels["boundaries"][0]["verdict"] == "false_positive"
    assert labels["pairs"][0]["winner"] == "a"


def test_save_and_load_roundtrip(tmp_path):
    labels = valid_labels()
    path = tmp_path / "labels.json"
    save_labels(labels, path)
    loaded = load_labels(path)
    assert loaded["shots"] == labels["shots"]
    assert json.loads(path.read_text(encoding="utf-8"))["annotator"] == "D.A."


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(LabelsError):
        load_labels(path)


def test_coverage_counts_labeled_shots():
    labels = valid_labels()
    report = coverage(labels, ["shot_0001", "shot_0002", "shot_0003"])
    assert report["shots_labeled"] == 2
    assert report["fraction"] == pytest.approx(2 / 3)
    assert report["missing"] == ["shot_0003"]


def _shot(shot_id, status, total, sharpness, failed=None):
    return {
        "shot_id": shot_id,
        "status": status,
        "total_score": total,
        "failed_gates": failed or [],
        "dimension_scores": {
            "sharpness": sharpness,
            "exposure": 0.8,
            "contrast": 0.7,
            "stability": 0.7,
            "motion": 0.6,
            "color": 0.6,
            "texture": 0.6,
            "duration": 0.6,
        },
    }


def test_ndcg_is_one_for_a_perfect_ordering():
    assert ndcg_at_k([1.0, 0.0, 0.0], 3) == pytest.approx(1.0)


def test_ndcg_penalizes_a_displaced_relevant_shot():
    assert ndcg_at_k([0.0, 1.0, 0.0], 3) < ndcg_at_k([1.0, 0.0, 0.0], 3)


def test_evaluation_without_labels_reports_insufficient():
    shots = [_shot("shot_0001", "selected", 0.9, 0.9)]
    result = evaluate(shots, shots, empty_labels(), top_n=1)
    assert result["status"] == "insufficient_labels"
    assert result["warnings"]


def test_evaluation_precision_recall_and_ndcg():
    shots = [
        _shot("shot_0001", "selected", 0.9, 0.9),
        _shot("shot_0002", "selected", 0.8, 0.5),
        _shot("shot_0003", "passing_unselected", 0.7, 0.8),
    ]
    labels = empty_labels()
    record_shot_label(labels, shot_id="shot_0001", verdict="keep")
    record_shot_label(labels, shot_id="shot_0002", verdict="reject", reason="blur")
    record_shot_label(labels, shot_id="shot_0003", verdict="keep")
    result = evaluate(shots, shots[:2], labels, top_n=2)
    assert result["status"] == "ok"
    assert result["metrics"]["precision_at_n"] == pytest.approx(0.5)
    assert result["metrics"]["recall_keep"] == pytest.approx(0.5)
    assert 0.0 < result["metrics"]["ndcg_at_n"] <= 1.0


def test_evaluation_reports_gate_false_rejects():
    failure = {
        "gate": "min_sharpness_score",
        "value": 0.1,
        "threshold": 0.15,
        "interpretation": "too soft",
    }
    shots = [
        _shot("shot_0001", "rejected_gate", 0.0, 0.1, failed=[failure]),
        _shot("shot_0002", "rejected_gate", 0.0, 0.1, failed=[failure]),
    ]
    labels = empty_labels()
    record_shot_label(labels, shot_id="shot_0001", verdict="keep")
    record_shot_label(labels, shot_id="shot_0002", verdict="reject", reason="blur")
    result = evaluate(shots, [], labels, top_n=2)
    diagnostics = {item["gate"]: item for item in result["gate_diagnostics"]}
    assert diagnostics["min_sharpness_score"]["false_rejects"] == 1
    assert diagnostics["min_sharpness_score"]["true_rejects"] == 1


def test_evaluation_reports_dimension_separation():
    shots = [
        _shot("shot_0001", "selected", 0.9, 0.9),
        _shot("shot_0002", "rejected_gate", 0.0, 0.1),
    ]
    labels = empty_labels()
    record_shot_label(labels, shot_id="shot_0001", verdict="keep")
    record_shot_label(labels, shot_id="shot_0002", verdict="reject", reason="blur")
    result = evaluate(shots, shots[:1], labels, top_n=1)
    sharpness = next(
        item for item in result["dimension_separation"] if item["dimension"] == "sharpness"
    )
    assert sharpness["gap"] == pytest.approx(0.8)
    assert sharpness["separates"] is True


def test_evaluation_pairwise_accuracy():
    shots = [
        _shot("shot_0001", "selected", 0.9, 0.9),
        _shot("shot_0002", "selected", 0.4, 0.4),
    ]
    labels = empty_labels()
    record_shot_label(labels, shot_id="shot_0001", verdict="keep")
    record_shot_label(labels, shot_id="shot_0002", verdict="reject", reason="blur")
    record_pair_label(labels, a="shot_0001", b="shot_0002", winner="a")
    record_pair_label(labels, a="shot_0002", b="shot_0001", winner="a")
    result = evaluate(shots, shots, labels, top_n=2)
    pairwise = result["pairwise"]
    assert pairwise["pairs_compared"] == 2
    assert pairwise["pairs_correct"] == 1
    assert pairwise["accuracy"] == pytest.approx(0.5)

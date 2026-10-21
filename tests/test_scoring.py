import pytest

from video_dsp.config import load_config
from video_dsp.scoring import (
    apply_hard_gates,
    compute_category_scores,
    normalize_higher_better,
    normalize_lower_better,
    rank_shots,
    weighted_total,
)


def _aggregated(**overrides):
    base = {
        "variance_laplacian": 400.0,
        "tenengrad": 4000.0,
        "edge_density": 0.1,
        "mean": 0.5,
        "std": 0.2,
        "black_clip": 0.0,
        "white_clip": 0.0,
        "instability": 0.1,
        "duration_seconds": 2.0,
        "sample_count": 10.0,
    }
    base.update(overrides)
    return base


def test_normalize_higher_better_bounds():
    assert normalize_higher_better(0.0, 0.0, 1.0) == 0.0
    assert normalize_higher_better(0.5, 0.0, 1.0) == 0.5
    assert normalize_higher_better(2.0, 0.0, 1.0) == 1.0


def test_normalize_lower_better_bounds():
    assert normalize_lower_better(0.0, 0.0, 1.0) == 1.0
    assert normalize_lower_better(1.0, 0.0, 1.0) == 0.0
    assert normalize_lower_better(-1.0, 0.0, 1.0) == 1.0


def test_category_scores_are_bounded():
    config = load_config()
    categories, normalized = compute_category_scores(_aggregated(), config)
    for value in categories.values():
        assert 0.0 <= value <= 1.0
    for value in normalized.values():
        assert value >= 0.0


def test_gates_pass_for_good_shot():
    config = load_config()
    aggregated = _aggregated()
    categories, _ = compute_category_scores(aggregated, config)
    passed, failed = apply_hard_gates(aggregated, categories, config["hard_gates"])
    assert passed
    assert failed == []


def test_gates_fail_for_black_clipping():
    config = load_config()
    aggregated = _aggregated(black_clip=0.5)
    categories, _ = compute_category_scores(aggregated, config)
    passed, failed = apply_hard_gates(aggregated, categories, config["hard_gates"])
    assert not passed
    assert any(gate["gate"] == "max_black_clip" for gate in failed)


def test_gates_fail_for_short_shot():
    config = load_config()
    aggregated = _aggregated(duration_seconds=0.1)
    categories, _ = compute_category_scores(aggregated, config)
    passed, failed = apply_hard_gates(aggregated, categories, config["hard_gates"])
    assert not passed
    assert any(gate["gate"] == "min_shot_duration" for gate in failed)


def test_stability_is_high_for_low_instability():
    config = load_config()
    stable, stable_normalized = compute_category_scores(
        _aggregated(instability=0.0), config
    )
    unstable, unstable_normalized = compute_category_scores(
        _aggregated(instability=0.35), config
    )
    assert stable["stability"] > unstable["stability"]
    assert stable_normalized["stability"] > unstable_normalized["stability"]


def test_weighted_total():
    scores = {"sharpness": 1.0, "exposure": 1.0, "contrast": 1.0, "stability": 1.0}
    weights = {
        "sharpness": 0.40,
        "exposure": 0.25,
        "contrast": 0.20,
        "stability": 0.15,
    }
    assert weighted_total(scores, weights) == pytest.approx(1.0)


def test_rank_shots_is_deterministic_by_score_then_start():
    shots = [
        {"shot_id": "a", "gate_passed": True, "total_score": 0.5, "start_time_seconds": 2.0},
        {"shot_id": "b", "gate_passed": True, "total_score": 0.9, "start_time_seconds": 5.0},
        {"shot_id": "c", "gate_passed": True, "total_score": 0.5, "start_time_seconds": 1.0},
        {"shot_id": "d", "gate_passed": False, "total_score": 0.0, "start_time_seconds": 0.0},
    ]
    ranked = rank_shots(shots, top_n=10)
    assert [shot["shot_id"] for shot in ranked] == ["b", "c", "a"]
    assert [shot["rank"] for shot in ranked] == [1, 2, 3]


def test_rank_shots_respects_top_n():
    shots = [
        {
            "shot_id": str(index),
            "gate_passed": True,
            "total_score": index / 10.0,
            "start_time_seconds": float(index),
        }
        for index in range(5)
    ]
    ranked = rank_shots(shots, top_n=2)
    assert len(ranked) == 2

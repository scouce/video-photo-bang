"""Tests for the pure selection service: gates, floor, diversity and determinism."""

import numpy as np
import pytest

from video_dsp.config import load_config
from video_dsp.selection_service import (
    STATUS_PASSING_UNSELECTED,
    STATUS_REJECTED_FLOOR,
    STATUS_REJECTED_GATE,
    STATUS_SELECTED,
    mmr_select,
    rank,
    recompute,
)

DIMENSIONS = (
    "sharpness",
    "exposure",
    "contrast",
    "stability",
    "motion",
    "color",
    "texture",
    "duration",
)


def make_record(
    shot_id: str,
    start: float = 0.0,
    duration: float = 4.0,
    *,
    sharpness: float = 100.0,
    colorfulness: float = 0.2,
    black_clip: float = 0.0,
    white_clip: float = 0.0,
    instability: float = 0.05,
    jitter: float = 0.5,
    histogram: list[float] | None = None,
) -> dict:
    metrics = {
        "variance_laplacian": sharpness,
        "tenengrad": sharpness * 10.0,
        "std": 0.20,
        "dynamic_range": 0.50,
        "clip_total": black_clip + white_clip,
        "midtone_dev": 0.10,
        "translation_consistency": 0.85,
        "jitter_px": jitter,
        "instability": instability,
        "pan_speed_px_s": 12.0,
        "motion_per_second": 0.20,
        "colorfulness": colorfulness,
        "saturation_mean": 0.35,
        "channel_cast": 0.02,
        "entropy": 0.70,
        "local_contrast": 0.05,
        "duration_seconds": duration,
        "black_clip": black_clip,
        "white_clip": white_clip,
        "translation_usable": 1.0,
        "stability_source": "translation",
    }
    signature = histogram if histogram is not None else [1.0 / 16.0] * 16
    return {
        "shot_id": shot_id,
        "start_time_seconds": start,
        "end_time_seconds": start + duration,
        "duration_seconds": duration,
        "sample_count": 20,
        "first_frame_index": int(start * 5),
        "last_frame_index": int((start + duration) * 5),
        "selected_frame_index": int(start * 5),
        "selected_frame_timestamp": start,
        "metrics": metrics,
        "histogram_signature": signature,
        "warnings": [],
    }


def varied_records(count: int = 10) -> list[dict]:
    return [
        make_record(
            f"shot_{index:04d}",
            start=index * 5.0,
            sharpness=20.0 + index * 30.0,
            colorfulness=0.05 + index * 0.03,
        )
        for index in range(count)
    ]


def test_rank_returns_every_dimension():
    records = varied_records()
    result = rank(records, load_config())
    assert len(result["shots"]) == len(records)
    for shot in result["shots"]:
        assert set(shot["dimension_scores"]) == set(DIMENSIONS)
        assert 0.0 <= shot["total_score"] <= 1.0


def test_rank_selects_top_n_and_orders_by_score():
    records = varied_records()
    config = load_config()
    config["top_n"] = 3
    result = rank(records, config)
    assert len(result["selected"]) == 3
    scores = [shot["total_score"] for shot in result["selected"]]
    assert scores == sorted(scores, reverse=True)
    assert [shot["rank"] for shot in result["selected"]] == [1, 2, 3]
    assert all(shot["status"] == STATUS_SELECTED for shot in result["selected"])


def test_rank_is_deterministic():
    records = varied_records()
    config = load_config()
    first = rank(records, config)
    second = rank(records, config)
    assert [shot["shot_id"] for shot in first["selected"]] == [
        shot["shot_id"] for shot in second["selected"]
    ]
    assert [shot["total_score"] for shot in first["selected"]] == [
        shot["total_score"] for shot in second["selected"]
    ]


def test_gate_rejects_black_clipped_shot():
    records = varied_records() + [
        make_record("shot_black", start=99.0, sharpness=400.0, black_clip=0.9)
    ]
    result = rank(records, load_config())
    black = next(shot for shot in result["shots"] if shot["shot_id"] == "shot_black")
    assert black["status"] == STATUS_REJECTED_GATE
    assert black["gate_passed"] is False
    assert any(failure["gate"] == "max_black_clip" for failure in black["failed_gates"])
    assert black["total_score"] > 0.0  # the raw score is still reported
    assert "shot_black" not in {shot["shot_id"] for shot in result["selected"]}


def test_quality_floor_rejects_low_total_scores():
    records = varied_records()
    config = load_config()
    config["quality_floor"] = {"enabled": True, "min_total_score": 0.95}
    config["top_n"] = 10
    result = rank(records, config)
    floors = [shot for shot in result["shots"] if shot["status"] == STATUS_REJECTED_FLOOR]
    assert floors
    assert all(shot["total_score"] < 0.95 for shot in floors)


def test_passing_unselected_is_distinct_from_gate_rejection():
    records = varied_records()
    config = load_config()
    config["top_n"] = 2
    config["quality_floor"] = {"enabled": False, "min_total_score": 0.0}
    config["hard_gates"]["min_sharpness_score"] = -1.0
    result = rank(records, config)
    unselected = [
        shot for shot in result["shots"] if shot["status"] == STATUS_PASSING_UNSELECTED
    ]
    assert len(unselected) == len(records) - 2
    assert all(shot["gate_passed"] for shot in unselected)
    assert result["summary"]["passing_unselected"] == len(unselected)


def permissive_config() -> dict:
    config = load_config()
    config["hard_gates"].update(
        {
            "min_sharpness_score": -1.0,
            "max_black_clip": 1.0,
            "max_white_clip": 1.0,
            "max_instability": 10.0,
            "max_jitter_px": 1000.0,
            "min_shot_duration_s": 0.0,
            "max_shot_duration_s": 1000.0,
        }
    )
    config["quality_floor"] = {"enabled": False, "min_total_score": 0.0}
    return config


def test_changing_weights_changes_the_ranking():
    sharp_only = make_record("shot_sharp", sharpness=400.0, colorfulness=0.01)
    colorful = make_record("shot_color", sharpness=25.0, colorfulness=0.60)
    records = [sharp_only, colorful]

    sharp_config = permissive_config()
    sharp_config["score_weights"] = {name: 0.0 for name in DIMENSIONS}
    sharp_config["score_weights"]["sharpness"] = 1.0
    sharp_result = recompute(records, sharp_config)
    assert sharp_result["selected"][0]["shot_id"] == "shot_sharp"

    color_config = permissive_config()
    color_config["score_weights"] = {name: 0.0 for name in DIMENSIONS}
    color_config["score_weights"]["color"] = 1.0
    color_result = recompute(records, color_config)
    assert color_result["selected"][0]["shot_id"] == "shot_color"


def test_mmr_prefers_diverse_clusters():
    count = 9
    scores = [0.90, 0.88, 0.86, 0.50, 0.48, 0.46, 0.40, 0.38, 0.36]
    groups = [0, 0, 0, 1, 1, 1, 2, 2, 2]
    candidates = [
        {
            "shot_id": f"s{index}",
            "total_score": scores[index],
            "start_time_seconds": float(index),
        }
        for index in range(count)
    ]
    similarity = np.full((count, count), 0.10)
    for left in range(count):
        similarity[left, left] = 1.0
        for right in range(count):
            if left != right and groups[left] == groups[right]:
                similarity[left, right] = 0.95
    index_of = {f"s{index}": index for index in range(count)}

    selected, trace = mmr_select(candidates, 3, 0.5, similarity, index_of)
    assert [shot["shot_id"] for shot in selected] == ["s0", "s3", "s6"]
    assert len(trace) == 3

    plain, _ = mmr_select(candidates, 3, 0.0, similarity, index_of)
    assert [shot["shot_id"] for shot in plain] == ["s0", "s1", "s2"]


def test_mmr_selection_is_deterministic_with_score_ties():
    candidates = [
        {"shot_id": "b", "total_score": 0.5, "start_time_seconds": 4.0},
        {"shot_id": "a", "total_score": 0.5, "start_time_seconds": 2.0},
        {"shot_id": "c", "total_score": 0.5, "start_time_seconds": 9.0},
    ]
    similarity = np.eye(3)
    index_of = {"a": 0, "b": 1, "c": 2}
    selected, _ = mmr_select(candidates, 2, 0.0, similarity, index_of)
    assert [shot["shot_id"] for shot in selected] == ["a", "b"]


def test_rank_reports_displaced_by_diversity():
    records = varied_records(12)
    config = load_config()
    config["top_n"] = 3
    config["diversity"] = {"enabled": True, "weight": 0.0}
    result = rank(records, config)
    assert result["displaced_by_diversity"] == []


def test_rank_clears_stale_ranks_from_a_previous_run():
    records = varied_records(6)
    for position, record in enumerate(records, start=1):
        record["rank"] = position
        record["plain_rank"] = position
        record["status"] = STATUS_SELECTED
    config = permissive_config()
    config["top_n"] = 2
    result = rank(records, config)
    for shot in result["shots"]:
        if shot["status"] == STATUS_SELECTED:
            assert shot["rank"] in (1, 2)
        else:
            assert shot["rank"] is None
            assert shot["plain_rank"] in (None, 1, 2)


def test_unknown_weight_dimension_is_rejected_by_config():
    config = load_config()
    del config["score_weights"]["motion"]
    with pytest.raises(ValueError, match="missing dimensions"):
        from video_dsp.config import _validate_config

        _validate_config(config)

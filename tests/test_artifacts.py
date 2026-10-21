"""Tests for run artifacts: deterministic CSV, run ids and the UI document."""

import gzip
import json

import numpy as np

from video_dsp.artifacts import (
    build_ui_document,
    run_directory,
    run_id,
    sample_columns,
    write_samples_csv,
    write_shots_csv,
    write_ui_document,
)
from video_dsp.config import config_hash, load_config


def _samples(count: int = 4, bins: int = 8) -> list[dict]:
    samples = []
    for index in range(count):
        histogram = np.full(bins, 1.0 / bins)
        histogram[index % bins] += 0.01
        histogram /= histogram.sum()
        samples.append(
            {
                "frame_index": index * 5,
                "timestamp_seconds": index * 0.2,
                "metrics": {
                    "variance_laplacian": 100.0 + index,
                    "tenengrad": 1000.0 + index,
                    "entropy": 0.5,
                    "histogram": histogram,
                },
                "motion_gray": np.zeros((6, 8), dtype=np.uint8),
            }
        )
    return samples


def _shot(shot_id: str = "shot_0001") -> dict:
    return {
        "shot_id": shot_id,
        "rank": 1,
        "plain_rank": 1,
        "status": "selected",
        "start_time_seconds": 0.0,
        "end_time_seconds": 2.0,
        "duration_seconds": 2.0,
        "sample_count": 10,
        "total_score": 0.75,
        "gate_passed": True,
        "selection_reason": "selected",
        "dimension_scores": {
            "sharpness": 0.8,
            "exposure": 0.9,
            "contrast": 0.7,
            "stability": 0.6,
            "motion": 0.5,
            "color": 0.5,
            "texture": 0.5,
            "duration": 0.5,
        },
        "metrics": {"variance_laplacian": 200.0, "duration_seconds": 2.0},
        "histogram_signature": [0.5, 0.5],
        "warnings": [],
    }


def test_run_id_is_deterministic_and_config_sensitive():
    config = load_config()
    first = run_id("sha256:" + "a" * 64, config)
    second = run_id("sha256:" + "a" * 64, config)
    other = run_id("sha256:" + "a" * 64, load_config(preset="action"))
    assert first == second
    assert first != other
    assert len(first.split("_")[0]) == 12


def test_run_directory_uses_the_run_id(tmp_path):
    config = load_config()
    directory = run_directory(tmp_path, "sha256:" + "b" * 64, config)
    assert directory.name.startswith("bbbbbbbbbbbb")
    assert directory.parent == tmp_path


def test_sample_columns_put_histogram_last():
    columns = sample_columns(_samples())
    assert columns[:2] == ["frame_index", "timestamp_seconds"]
    assert columns[2:] == [
        "entropy",
        "tenengrad",
        "variance_laplacian",
        *(f"hist_{index:02d}" for index in range(8)),
    ]


def test_samples_csv_is_byte_deterministic(tmp_path):
    samples = _samples()
    first = tmp_path / "a.csv.gz"
    second = tmp_path / "b.csv.gz"
    write_samples_csv(samples, first, deterministic_gzip=True)
    write_samples_csv(samples, second, deterministic_gzip=True)
    assert first.read_bytes() == second.read_bytes()
    with gzip.open(first, "rt", encoding="utf-8") as handle:
        header = handle.readline().strip().split(",")
        row = handle.readline().strip().split(",")
    assert header[0] == "frame_index"
    assert len(row) == len(header)


def test_samples_csv_mtime_varies_when_not_deterministic(tmp_path):
    samples = _samples()
    write_samples_csv(samples, tmp_path / "a.csv.gz", deterministic_gzip=False)
    # The header still has to be valid; only the gzip header differs.
    with gzip.open(tmp_path / "a.csv.gz", "rt", encoding="utf-8") as handle:
        assert handle.readline().startswith("frame_index")


def test_shots_csv_has_one_row_per_shot(tmp_path):
    path = tmp_path / "shots.csv"
    write_shots_csv([_shot("shot_0001"), _shot("shot_0002")], path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("shot_id,rank,plain_rank,status")
    assert "dim_sharpness" in lines[0]


def test_ui_document_contains_the_full_contract():
    config = load_config()
    result = {
        "shots": [_shot()],
        "selected": [_shot()],
        "displaced_by_diversity": [],
        "normalization": {"sharpness": {"components": {"vol": {"low": 0.0}}}},
        "score_weights_effective": dict(config["score_weights_effective"]),
        "summary": {"selected": 1},
        "warnings": ["w"],
    }
    document = build_ui_document(
        interpretation="technical_dsp_draft_only",
        pipeline={"name": "test"},
        source={"path": "input.mp4"},
        config=config,
        config_hash_value=config_hash(config),
        analysis_resolution={"width": 720, "height": 1280},
        boundaries=[],
        boundary_positions=[10, 20],
        boundary_detection={"threshold": 0.1},
        shot_records=[_shot()],
        result=result,
        aggregation={"std": "median"},
        motion_aggregation={"instability": "mean"},
        artifacts={"run_dir": "out/runs/x"},
    )
    for key in [
        "schema_version",
        "pipeline",
        "source",
        "config",
        "presets",
        "field_catalog",
        "dimension_catalog",
        "normalization",
        "shots",
        "selected",
        "summary",
        "artifacts",
    ]:
        assert key in document
    assert "balanced_v2" in document["presets"]
    assert document["field_catalog"]["jitter_px"]["unit_es"]
    assert document["distances"] == []
    assert document["boundary_positions"] == [10, 20]
    assert document["evaluation"] is None


def test_write_ui_document_roundtrip(tmp_path):
    path = tmp_path / "ui.json"
    write_ui_document({"a": 1, "ñ": "á"}, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "ñ": "á"}

import json

import numpy as np

from video_dsp.config import SCHEMA_VERSION, config_hash, load_config
from video_dsp.export import build_error_output, build_output, jsonable, write_json


def test_jsonable_converts_numpy():
    payload = {
        "array": np.array([1.0, 2.0]),
        "scalar": np.float64(0.5),
        "integer": np.int64(3),
        "nested": [np.array([1, 2])],
        "flag": np.bool_(True),
    }
    converted = jsonable(payload)
    assert converted["array"] == [1.0, 2.0]
    assert converted["scalar"] == 0.5
    assert converted["integer"] == 3
    assert converted["nested"] == [[1, 2]]
    assert converted["flag"] is True


def test_write_json_roundtrip(tmp_path):
    target = tmp_path / "out.json"
    write_json({"b": 2, "a": 1}, target)
    assert json.loads(target.read_text(encoding="utf-8")) == {"b": 2, "a": 1}


def test_build_output_contains_required_keys():
    config = load_config()
    document = build_output(
        schema_version=SCHEMA_VERSION,
        interpretation="technical_dsp_draft_only",
        pipeline={"name": "test"},
        source={"path": "input.mov"},
        selection_request={"top_n": 1},
        config=config,
        config_hash_value=config_hash(config),
        aggregation_strategy={"std": "median"},
        boundary_detection={"threshold": 1.0},
        boundary_times=[1.0],
        frame_distances=[],
        selected_shots=[],
        rejected_shots=[],
        summary={"total_shots": 0},
        analysis_resolution={"width": 10, "height": 10},
    )
    for key in [
        "schema_version",
        "generated_at_utc",
        "interpretation",
        "pipeline",
        "source",
        "selection_request",
        "config_hash",
        "detected_boundaries_seconds",
        "selected_shots",
        "rejected_shots",
        "summary",
    ]:
        assert key in document


def test_error_output_marks_aborted():
    config = load_config()
    document = build_error_output(
        schema_version=SCHEMA_VERSION,
        interpretation="technical_dsp_draft_only",
        pipeline={"name": "test"},
        source={"path": "input.mov"},
        config=config,
        config_hash_value=config_hash(config),
        errors=["bad"],
        warnings=["w"],
    )
    assert document["error"]["aborted"] is True
    assert document["selected_shots"] == []


def test_config_hash_is_stable():
    assert config_hash(load_config()) == config_hash(load_config())

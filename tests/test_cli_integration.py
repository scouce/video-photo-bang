import json
from pathlib import Path

import pytest

from video_dsp.cli import main

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "synthetic_test.mov"


@pytest.mark.skipif(not SAMPLE.exists(), reason="synthetic sample not available")
def test_cli_end_to_end(tmp_path):
    out = tmp_path / "selection.json"
    thumbs = tmp_path / "thumbs"
    run_dir = tmp_path / "run"

    code = main(
        [
            str(SAMPLE),
            "--out",
            str(out),
            "--thumbnails",
            str(thumbs),
            "--run-dir",
            str(run_dir),
        ]
    )

    assert code == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["schema_version"]
    assert document["interpretation"] == "technical_dsp_draft_only"
    assert len(document["source"]["file_hash_sha256"]) == 64
    assert document["summary"]["samples_analyzed"] > 0
    assert document["detected_boundaries_seconds"]
    assert document["selected_shots"]
    for shot in document["selected_shots"]:
        assert shot["gate_passed"] is True
        assert shot["status"] == "selected"
        assert shot["metrics"]
        assert shot["dimension_scores"]
        assert set(shot["dimension_scores"]) == {
            "sharpness",
            "exposure",
            "contrast",
            "stability",
            "motion",
            "color",
            "texture",
            "duration",
        }
        assert shot["selected_frame_timestamp"] >= 0
        assert Path(shot["selected_frame_image_path"]).exists()
    for shot in document["rejected_shots"]:
        assert shot["gate_passed"] is False
        assert shot["failed_gates"]
        assert shot["selection_reason"] in {"failed_gates", "below_quality_floor"}

    # Run artifacts: the UI must be able to re-rank without touching the video again.
    ui = json.loads((run_dir / "ui.json").read_text(encoding="utf-8"))
    assert ui["shots"]
    assert ui["field_catalog"]["variance_laplacian"]["unit_es"]
    assert ui["normalization"]["sharpness"]["components"]["vol"]["source"] in {
        "per_video_p5_p95",
        "config_absolute",
        "target_band",
    }
    assert (run_dir / "samples.csv.gz").exists()
    assert (run_dir / "shots.csv").exists()

    # Every recommended or discarded shot gets a small preview for the simple gallery.
    preview_shots = [
        shot
        for shot in ui["shots"]
        if shot["status"] in {"selected", "rejected_gate", "rejected_floor"}
    ]
    assert preview_shots
    assert ui["artifacts"]["shot_thumbs_dir"]
    for shot in preview_shots:
        thumb = Path(shot["thumb_path"])
        assert thumb.exists()
        assert thumb.suffix == ".jpg"
        assert shot["thumb_width"] <= 480 and shot["thumb_height"] <= 480
    for shot in ui["shots"]:
        if shot["status"] == "passing_unselected":
            assert "thumb_path" not in shot


@pytest.mark.skipif(not SAMPLE.exists(), reason="synthetic sample not available")
def test_cli_legacy_preset_uses_absolute_normalization(tmp_path):
    out = tmp_path / "legacy.json"
    code = main(
        [
            str(SAMPLE),
            "--out",
            str(out),
            "--preset",
            "balanced_v1",
            "--run-dir",
            str(tmp_path / "run"),
            "--no-montage",
        ]
    )
    assert code == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["selection_request"]["preset"] == "balanced_v1"
    for dimension in document["normalization"].values():
        for component in dimension["components"].values():
            if component["mode"] == "band":
                continue
            assert component["method"] == "absolute"

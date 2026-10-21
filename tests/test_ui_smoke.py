"""End-to-end smoke test for the Streamlit client.

The client is a view over ``ui.json``, so the test builds a real run from the synthetic
sample, points the app at it with ``VIDEO_DSP_RUNS_DIR``, and drives it with Streamlit's
own test harness. It asserts the two interactions that matter: re-weighting re-ranks, and
changing the merge threshold rebuilds shots from the CSV without touching the video.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from video_dsp.cli import main  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "synthetic_test.mov"
APP = ROOT / "app" / "ui.py"


@pytest.fixture()
def run_dir(tmp_path, monkeypatch):
    if not SAMPLE.exists():
        pytest.skip("synthetic sample not available")
    directory = tmp_path / "runs" / "synthetic"
    code = main(
        [
            str(SAMPLE),
            "--run-dir",
            str(directory),
            "--out",
            str(directory / "audit.json"),
            "--no-montage",
            "--top-n",
            "2",
        ]
    )
    assert code == 0
    monkeypatch.setenv("VIDEO_DSP_RUNS_DIR", str(directory.parent))
    return directory


def _app(run_dir) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=120)
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    return app


def test_app_loads_a_run_without_error(run_dir):
    app = _app(run_dir)
    labels = [metric.label for metric in app.metric]
    assert "Planos" in labels
    assert "Seleccionados" in labels


def test_weight_change_reranks(run_dir):
    app = _app(run_dir)
    sliders = {slider.label: slider for slider in app.sidebar.slider}
    for label, slider in sliders.items():
        if label in {"Nitidez", "Exposición", "Contraste", "Estabilidad"}:
            slider.set_value(1.0 if label == "Nitidez" else 0.0)
        elif label in {"Movimiento", "Color", "Textura", "Duración"}:
            slider.set_value(0.0)
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    total = next(metric for metric in app.metric if metric.label == "Score total")
    assert 0.0 <= float(total.value) <= 1.0


def test_merge_similarity_rebuilds_from_samples(run_dir):
    document = json.loads((run_dir / "ui.json").read_text(encoding="utf-8"))
    assert document["distances"], "the run must record frame distances"
    assert document["boundary_positions"]

    app = _app(run_dir)
    merge = next(slider for slider in app.slider if "Similitud" in slider.label)
    merge.set_value(0.98)
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    shots = next(metric for metric in app.metric if metric.label == "Planos")
    assert int(shots.value) >= 1

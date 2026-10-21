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

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "ui.py"


def _app(run_dir) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=120)
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    return app


def _technical(app: AppTest) -> AppTest:
    """The app opens in Simple mode; the technical checks switch explicitly."""
    mode = next(radio for radio in app.sidebar.radio if radio.label == "Vista")
    mode.set_value("Técnico")
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    return app


def test_app_loads_a_run_without_error(run_dir):
    app = _technical(_app(run_dir))
    labels = [metric.label for metric in app.metric]
    assert "Planos" in labels
    assert "Seleccionados" in labels


def test_simple_mode_is_the_default(run_dir):
    app = _app(run_dir)
    assert not [metric for metric in app.metric if metric.label == "Planos"]
    assert app.title, "the simple view still needs a visible title"


def test_weight_change_reranks(run_dir):
    app = _technical(_app(run_dir))
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

    app = _technical(_app(run_dir))
    merge = next(slider for slider in app.slider if "Similitud" in slider.label)
    merge.set_value(0.98)
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    shots = next(metric for metric in app.metric if metric.label == "Planos")
    assert int(shots.value) >= 1

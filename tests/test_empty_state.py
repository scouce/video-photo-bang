"""The app must open empty after a fresh clone: no video, no photos, just the uploader."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

os.environ.setdefault("VIDEO_DSP_RUNS_DIR", str(Path(tempfile.mkdtemp()) / "runs"))
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "ui.py"


def test_empty_state_renders_uploader():
    app = AppTest.from_file(str(APP), default_timeout=120)
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    assert len(app.file_uploader) >= 1
    assert any(button.label == "Analizar" for button in app.button)

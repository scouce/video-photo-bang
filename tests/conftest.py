"""Shared fixtures for the client tests.

The Streamlit tests need a real run on disk, so they build one from the synthetic sample and
point the app at it with ``VIDEO_DSP_RUNS_DIR``. Building it once per test keeps the tests
independent without sharing mutable state.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "synthetic_test.mov"
APP_DIR = ROOT / "app"
SRC = ROOT / "src"

for path in (SRC, APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture()
def run_dir(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from video_dsp.cli import main

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

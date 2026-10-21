"""Tests for the simplified client: gallery, downloads and plain-language copy.

The point of the mode is that a non-photographer can open the app, look at the photos and
take them away without knowing what a weight or a gate is. These tests hold that line while
keeping the technical mode intact.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

import copy_ui as copy  # noqa: E402
import simple  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "ui.py"

JARGON = ("Bhattacharyya", "MMR", "Tenengrad", "jitter", "percentil", "p5-p95", "gate")


def _app() -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=120)
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    return app


def _plain_text(app: AppTest) -> str:
    parts = [element.value for element in app.title]
    parts += [element.value for element in app.subheader]
    parts += [element.value for element in app.caption]
    parts += [element.label for element in app.radio]
    parts += [element.label for element in app.selectbox]
    parts += [element.label for element in app.button]
    parts += [element.label for element in app.download_button]
    parts += [
        element.value
        for element in app.markdown
        if "`" not in element.value and "**" not in element.value
    ]
    return " ".join(str(part) for part in parts)


def test_simple_mode_is_the_default(run_dir):
    del run_dir
    app = _app()
    mode = next(radio for radio in app.sidebar.radio if radio.label == "View")
    assert mode.value == "Simple"
    assert not [metric for metric in app.metric if metric.label == "Planos"]
    assert any(title.value == "Your photos" for title in app.title)


def test_gallery_has_one_card_per_recommended_shot(run_dir):
    del run_dir
    app = _app()
    fichas = [button for button in app.button if button.label == "View details"]
    downloads = [
        button
        for button in app.download_button
        if button.label in {"Download photo", "Download preview"}
    ]
    assert len(fichas) >= 1
    assert len(downloads) == len(fichas)


def test_main_page_offers_both_zips_and_config(run_dir):
    del run_dir
    app = _app()
    labels = [button.label for button in app.download_button]
    assert any("full quality" in label for label in labels)
    assert any("light" in label for label in labels)
    assert any("configuration" in label for label in labels)


def test_download_prefers_the_full_jpeg(run_dir):
    document = json.loads((run_dir / "ui.json").read_text(encoding="utf-8"))
    selected = [shot for shot in document["shots"] if shot["status"] == "selected"]
    assert selected
    for shot in selected:
        path, mime, label = simple.download_of(shot)
        assert Path(path) == Path(shot["photo_path"])
        assert mime == "image/jpeg"
        assert label == "Download photo"
        assert Path(path).stat().st_size > 0


def test_download_falls_back_to_the_preview_for_rejected_shots(run_dir):
    document = json.loads((run_dir / "ui.json").read_text(encoding="utf-8"))
    rejected = [
        shot for shot in document["shots"] if shot["status"].startswith("rejected")
    ]
    assert rejected
    # A run created after this change ships the full JPEG for rejected shots too.
    for shot in rejected:
        assert Path(shot["photo_path"]).exists()
    # A run from before it only had the 480 px preview: never promise more than that.
    legacy = {key: value for key, value in rejected[0].items() if key != "photo_path"}
    path, mime, label = simple.download_of(legacy)
    assert Path(path) == Path(legacy["thumb_path"])
    assert mime == "image/jpeg"
    assert label == "Download preview"


def test_the_full_jpeg_is_smaller_than_the_png(run_dir):
    document = json.loads((run_dir / "ui.json").read_text(encoding="utf-8"))
    for shot in document["shots"]:
        png = shot.get("selected_frame_image_path")
        if png:
            assert shot["photo_bytes"] < Path(png).stat().st_size


def test_zip_contains_the_recommended_pngs(run_dir):
    document = json.loads((run_dir / "ui.json").read_text(encoding="utf-8"))
    selected = [
        shot
        for shot in document["shots"]
        if shot["status"] == "selected" and shot.get("selected_frame_image_path")
    ]
    assert selected
    paths = tuple(shot["selected_frame_image_path"] for shot in selected)
    names = tuple(f"{shot['shot_id']}.png" for shot in selected)
    payload = simple.zip_bytes(paths, names)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert sorted(archive.namelist()) == sorted(names)
        assert all(archive.getinfo(name).file_size > 0 for name in names)


def test_discard_filter_shows_rejected_shots(run_dir):
    del run_dir
    app = _app()
    view = next(radio for radio in app.radio if radio.label == "Show")
    view.set_value("Discarded")
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    chips = [
        markdown.value
        for markdown in app.markdown
        if "Discarded" in markdown.value or "Recommended" in markdown.value
    ]
    assert any(value.startswith("⛔") for value in chips)
    assert not any(value.startswith("✅") for value in chips)


def test_no_jargon_in_the_simple_view(run_dir):
    del run_dir
    app = _app()
    text = _plain_text(app).lower()
    found = [word for word in JARGON if word.lower() in text]
    assert not found, f"technical jargon leaked into the simple view: {found}"


def test_switching_preset_writes_the_config(run_dir):
    del run_dir
    app = _app()
    picker = next(
        box for box in app.sidebar.selectbox if box.label == "Type of photo"
    )
    picker.set_value("landscape")
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    assert app.session_state["prefs"]["preset"] == "landscape"


def test_reset_returns_to_the_run_config(run_dir):
    del run_dir
    app = _app()
    picker = next(
        box for box in app.sidebar.selectbox if box.label == "Type of photo"
    )
    picker.set_value("low_light")
    app.run()
    reset = next(button for button in app.sidebar.button if button.label == "Reset")
    reset.click()
    app.run()
    assert not app.exception, [error.message for error in app.exception]
    assert app.session_state["prefs"]["preset"] != "low_light"


def test_why_sentence_is_deterministic_and_plain(run_dir):
    del run_dir
    shot = {
        "dimension_scores": {
            "sharpness": 0.9,
            "exposure": 0.8,
            "contrast": 0.5,
            "stability": 0.3,
            "motion": 0.2,
            "color": 0.6,
            "texture": 0.7,
            "duration": 1.0,
        },
        "score_weights_effective": {
            "sharpness": 0.3,
            "exposure": 0.2,
            "contrast": 0.1,
            "stability": 0.2,
            "motion": 0.05,
            "color": 0.05,
            "texture": 0.05,
            "duration": 0.0,
        },
    }
    first = copy.why_sentence(shot, shot["score_weights_effective"])
    second = copy.why_sentence(shot, shot["score_weights_effective"])
    assert first == second
    assert first.startswith("Stands out for its")
    assert "Weakest point: stability." in first


def test_clock_and_duration_use_plain_notation():
    assert copy.clock(78.4) == "1:18"
    assert copy.duration_label(3.6) == "3.6 s"

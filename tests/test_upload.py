"""Tests for the upload path: hashing, dedupe, deterministic run directory, job wiring."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("streamlit")

import upload  # noqa: E402


class FakeUpload(io.BytesIO):
    """Enough of ``st.file_uploader``'s value for the storage path."""

    def __init__(self, data: bytes, name: str) -> None:
        super().__init__(data)
        self.name = name


def test_store_upload_hashes_and_dedupes(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path)
    payload = b"fake movie bytes" * 1000

    first = upload.store_upload(FakeUpload(payload, "IMG_0001.mov"))
    assert first.sha256 == hashlib.sha256(payload).hexdigest()
    assert first.bytes == len(payload)
    assert first.path.exists()
    assert first.path.name.startswith(first.sha256[:12])
    assert first.reused is False

    second = upload.store_upload(FakeUpload(payload, "IMG_0001.mov"))
    assert second.path == first.path
    assert second.reused is True
    assert len(list(tmp_path.iterdir())) == 1


def test_store_upload_rejects_unknown_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path)
    with pytest.raises(upload.UploadError, match="Formato no admitido"):
        upload.store_upload(FakeUpload(b"x", "notes.txt"))
    assert not list(tmp_path.iterdir())


def test_store_local_does_not_copy(tmp_path):
    source = tmp_path / "clip.mov"
    source.write_bytes(b"already here")
    stored = upload.store_local(str(source))
    assert stored.path == source
    assert stored.bytes == source.stat().st_size
    assert stored.sha256 == hashlib.sha256(b"already here").hexdigest()


def test_store_local_rejects_a_missing_file(tmp_path):
    with pytest.raises(upload.UploadError, match="no existe|No existe"):
        upload.store_local(str(tmp_path / "nope.mov"))


def test_run_directory_is_deterministic_and_config_sensitive(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "RUNS_DIR", tmp_path)
    video = upload.StoredVideo(
        path=Path("/videos/IMG 1564.mov"), sha256="a" * 64, bytes=10, reused=False
    )
    first = upload.run_directory(video, {"preset": "balanced_v2"})
    again = upload.run_directory(video, {"preset": "balanced_v2"})
    other = upload.run_directory(video, {"preset": "portrait"})
    assert first == again
    assert first != other
    assert "IMG_1564" in first.name
    assert first.name.startswith("IMG_1564_aaaaaaaa")


def test_job_command_runs_the_cli_module(tmp_path):
    video = upload.StoredVideo(
        path=tmp_path / "clip.mov", sha256="b" * 64, bytes=1, reused=False
    )
    command = upload.job_command(video, tmp_path / "run")
    assert command[1:4] == ["-m", "video_dsp.cli", str(video.path)]
    assert "--run-dir" in command
    assert str(tmp_path / "run" / "audit.json") in command


def test_stream_yields_lines_without_terminators():
    process = SimpleNamespace(stdout=io.StringIO("one\n two \n"))
    job = upload.Job(process=process, run_dir=Path("."), started_at=0.0)
    assert list(upload.stream(job)) == ["one", " two"]


def test_progress_line_ignores_the_sampling_noise():
    assert upload._progress_line("[video_dsp] wrote 10 representative frames")
    assert not upload._progress_line("[video_dsp] sampled 200 frames...")
    assert not upload._progress_line("random output")

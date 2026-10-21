"""Upload a video from the browser and analyse it with the existing CLI.

The pipeline stays in one place: the client never decodes video and never re-implements the
ranking. An uploaded file is stored under ``out/uploads`` (hashed while it is written so the
same bytes are stored once), a deterministic run directory is derived from the file hash and
the config hash, and ``python -m video_dsp.cli`` is spawned exactly as a person would run it.

The job lives in ``st.session_state``; if the user navigates away the process keeps running
and its run appears in the selector on the next load.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from video_dsp.config import config_hash, load_config

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = Path(os.environ.get("VIDEO_DSP_RUNS_DIR", ROOT / "out" / "runs"))
UPLOADS_DIR = Path(os.environ.get("VIDEO_DSP_UPLOADS_DIR", ROOT / "out" / "uploads"))

ALLOWED_SUFFIXES = (".mov", ".mp4", ".m4v", ".avi", ".mkv")
CHUNK_BYTES = 8 * 1024 * 1024
MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024


class UploadError(Exception):
    """A problem the user can fix: wrong extension, missing file, too large."""


@dataclass(frozen=True)
class StoredVideo:
    path: Path
    sha256: str
    bytes: int
    reused: bool


@dataclass
class Job:
    process: subprocess.Popen[str]
    run_dir: Path
    started_at: float
    log: list[str] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned[:40] or "video"


def _validate(path: Path) -> None:
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise UploadError(
            f"Formato no admitido: {path.suffix or '(sin extensión)'}. "
            f"Se admiten {', '.join(ALLOWED_SUFFIXES)}."
        )
    if not path.exists():
        raise UploadError(f"No existe el archivo: {path}")


def store_upload(uploaded) -> StoredVideo:
    """Write an ``st.file_uploader`` value to disk in chunks, hashing as we go."""
    name = Path(getattr(uploaded, "name", "video.mov")).name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadError(
            f"Formato no admitido: {suffix or '(sin extensión)'}. "
            f"Se admiten {', '.join(ALLOWED_SUFFIXES)}."
        )

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    partial = UPLOADS_DIR / f".incoming_{os.getpid()}_{time.time_ns()}{suffix}"
    digest = hashlib.sha256()
    total = 0
    try:
        with partial.open("wb") as handle:
            while True:
                chunk = uploaded.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise UploadError(
                        "El vídeo supera los 4 GB. Usa el campo de ruta local para "
                        "analizarlo sin copiarlo."
                    )
                digest.update(chunk)
                handle.write(chunk)
        sha256 = digest.hexdigest()
        target = UPLOADS_DIR / f"{sha256[:12]}_{name}"
        if target.exists():
            partial.unlink(missing_ok=True)
            return StoredVideo(target, sha256, target.stat().st_size, True)
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return StoredVideo(target, sha256, total, False)


def store_local(raw_path: str) -> StoredVideo:
    """Use a file that already exists on this machine without copying it."""
    path = Path(raw_path).expanduser()
    _validate(path)
    if not path.is_file():
        raise UploadError(f"No es un archivo: {path}")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return StoredVideo(path, digest.hexdigest(), total, True)


def run_directory(video: StoredVideo, config: dict | None = None) -> Path:
    """Deterministic per (file bytes, config): re-analysing the same video reuses the run."""
    config = config or load_config()
    stamp = config_hash(config).split(":", 1)[-1][:6]
    return RUNS_DIR / f"{_safe_stem(video.path.name)}_{video.sha256[:8]}_{stamp}"


def job_command(video: StoredVideo, run_dir: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "video_dsp.cli",
        str(video.path),
        "--run-dir",
        str(run_dir),
        "--out",
        str(run_dir / "audit.json"),
    ]


def start_job(video: StoredVideo, run_dir: Path) -> Job:
    run_dir.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        job_command(video, run_dir),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=environment,
    )
    return Job(process=process, run_dir=run_dir, started_at=time.monotonic())


def stream(job: Job) -> Iterator[str]:
    if job.process.stdout is None:
        return
    for line in job.process.stdout:
        yield line.rstrip()


def cancel(job: Job) -> None:
    if job.process.poll() is None:
        job.process.terminate()


def _progress_line(line: str) -> bool:
    return line.startswith("[video_dsp]") and "sampled" not in line


def render_panel() -> None:
    """Uploader + local path. Runs the CLI and leaves the new run for the caller."""
    with st.container(border=True):
        st.markdown("**Analizar un vídeo nuevo**")
        st.caption(
            "El archivo se queda en tu equipo: se guarda en `out/uploads` y se procesa "
            "con el mismo motor que el CLI."
        )
        uploaded = st.file_uploader(
            "Sube un vídeo",
            type=[suffix.lstrip(".") for suffix in ALLOWED_SUFFIXES],
            key="upload_file",
            help="MOV, MP4, M4V, AVI o MKV. Hasta 4 GB.",
        )
        local_path = st.text_input(
            "…o escribe la ruta de un vídeo que ya está en este equipo",
            key="upload_local_path",
            placeholder=r"C:\Users\tu_usuario\Videos\clip.mov",
        )
        columns = st.columns([1, 3])
        start = columns[0].button(
            "Analizar", type="primary", width="stretch", key="upload_start"
        )
        if start:
            _start(uploaded, local_path)


def _start(uploaded, local_path: str) -> None:
    try:
        if local_path.strip():
            video = store_local(local_path.strip())
        elif uploaded is not None:
            video = store_upload(uploaded)
        else:
            st.warning("Elige un archivo o escribe una ruta.")
            return
    except UploadError as error:
        st.error(str(error))
        return

    run_dir = run_directory(video)
    if (run_dir / "ui.json").exists():
        st.session_state["pending_run"] = str(run_dir)
        st.toast("Ese vídeo ya estaba analizado: abriendo el resultado.", icon="♻️")
        st.rerun()

    st.session_state["upload_job"] = start_job(video, run_dir)
    st.session_state["upload_reused"] = video.reused
    st.rerun()


def run_pending_job() -> None:
    """Stream the child process to a status panel and hand the run back to the caller."""
    job: Job | None = st.session_state.get("upload_job")
    if job is None:
        return

    status = st.status("Analizando el vídeo…", expanded=True)
    for line in stream(job):
        job.log.append(line)
        if _progress_line(line):
            status.write(line.replace("[video_dsp] ", ""))
    job.process.wait()

    if job.process.returncode == 0 and (job.run_dir / "ui.json").exists():
        status.update(label="Análisis terminado", state="complete", expanded=False)
        st.session_state.pop("upload_job", None)
        st.session_state.pop("upload_reused", None)
        st.session_state["pending_run"] = str(job.run_dir)
        st.rerun()

    status.update(label="El análisis no terminó", state="error", expanded=True)
    st.code("\n".join(job.log[-40:]) or "(sin salida)", language="text")
    if st.button("Descartar este intento", key="upload_discard"):
        cancel(job)
        st.session_state.pop("upload_job", None)
        st.session_state.pop("upload_reused", None)
        st.rerun()

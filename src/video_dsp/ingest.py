"""File ingestion: hashing, ffprobe metadata extraction, and validation."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class IngestError(RuntimeError):
    """Raised when the input file cannot be ingested."""


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class VideoMetadata:
    path: str
    file_hash_sha256: str
    container: str
    codec: str
    width: int
    height: int
    fps: float
    avg_fps: float
    duration_seconds: float
    pix_fmt: str
    color_range: str
    color_space: str
    rotation_degrees: int
    nb_frames: int
    vfr: bool
    extension: str = ""
    nb_frames_estimated: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "file_hash_sha256": self.file_hash_sha256,
            "container": self.container,
            "extension": self.extension,
            "codec": self.codec,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "avg_fps": self.avg_fps,
            "duration_seconds": self.duration_seconds,
            "pix_fmt": self.pix_fmt,
            "color_range": self.color_range,
            "color_space": self.color_space,
            "rotation_degrees": self.rotation_degrees,
            "nb_frames": self.nb_frames,
            "nb_frames_estimated": self.nb_frames_estimated,
            "vfr": self.vfr,
            "warnings": list(self.warnings),
        }


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute the SHA-256 of a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ffprobe_json(path: Path) -> dict[str, Any]:
    """Run ffprobe and return its JSON output."""
    executable = shutil.which("ffprobe")
    if executable is None:
        raise IngestError("ffprobe not found on PATH")
    command = [
        executable,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive
        raise IngestError(f"ffprobe failed: {exc.stderr.strip()}") from exc
    stdout = completed.stdout
    if stdout is None:
        raise IngestError("ffprobe produced no output")
    return json.loads(stdout)


def parse_fps(value: str) -> float:
    """Parse an ffprobe rational frame rate such as ``25/1`` into a float."""
    if not value or value == "0/0":
        return 0.0
    numerator, _, denominator = value.partition("/")
    try:
        den = float(denominator) if denominator else 1.0
        return float(numerator) / den if den else 0.0
    except ValueError:
        return 0.0


def _rotation_degrees(stream: dict[str, Any]) -> int:
    for side in stream.get("side_data_list") or []:
        if side.get("side_data_type") == "Display Matrix":
            return int(side.get("rotation", 0) or 0)
    return 0


def extract_video_stream(probe: dict[str, Any]) -> dict[str, Any] | None:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return None


DECODABLE_CODECS = {
    "h264",
    "hevc",
    "prores",
    "mjpeg",
    "mpeg4",
    "mpeg2video",
    "vp8",
    "vp9",
    "av1",
    "png",
    "rawvideo",
    "dvvideo",
    "dnxhd",
}


def parse_metadata(path: Path, file_hash: str) -> VideoMetadata:
    """Build a :class:`VideoMetadata` from an ffprobe document."""
    probe = ffprobe_json(path)
    fmt = probe.get("format", {})
    stream = extract_video_stream(probe)

    warnings: list[str] = []
    if stream is None:
        return VideoMetadata(
            path=str(path),
            file_hash_sha256=file_hash,
            container=fmt.get("format_name", "unknown"),
            codec="unknown",
            width=0,
            height=0,
            fps=0.0,
            avg_fps=0.0,
            duration_seconds=0.0,
            pix_fmt="unknown",
            color_range="unknown",
            color_space="unknown",
            rotation_degrees=0,
            nb_frames=0,
            vfr=False,
            extension=path.suffix.lower(),
            warnings=["no_video_stream"],
        )

    fps = parse_fps(stream.get("r_frame_rate", "0/0"))
    avg_fps = parse_fps(stream.get("avg_frame_rate", "0/0"))
    vfr = abs(fps - avg_fps) > 1e-3
    rotation = _rotation_degrees(stream)
    duration = float(fmt.get("duration", 0.0) or 0.0)

    nb_frames = int(stream.get("nb_frames", 0) or 0)
    nb_frames_estimated = False
    if nb_frames <= 0 and duration > 0:
        reference_fps = avg_fps or fps
        nb_frames = int(round(duration * reference_fps))
        nb_frames_estimated = True
        warnings.append("nb_frames_unavailable_estimated_from_duration")

    if vfr:
        warnings.append(
            f"variable_frame_rate_detected (r_frame_rate={fps:.4f}, avg_frame_rate={avg_fps:.4f})"
        )
    if rotation:
        warnings.append(
            f"rotation_metadata_degrees={rotation} (orientation handling depends on the "
            "decoder; verify exported frames)"
        )
    codec = stream.get("codec_name", "unknown")
    if codec not in DECODABLE_CODECS:
        warnings.append(f"codec_{codec}_may_not_decode_with_opencv")

    return VideoMetadata(
        path=str(path),
        file_hash_sha256=file_hash,
        container=fmt.get("format_name", "unknown"),
        codec=codec,
        width=int(stream.get("width", 0) or 0),
        height=int(stream.get("height", 0) or 0),
        fps=fps,
        avg_fps=avg_fps,
        duration_seconds=duration,
        pix_fmt=stream.get("pix_fmt", "unknown"),
        color_range=stream.get("color_range", "unknown"),
        color_space=stream.get("color_space", "unknown"),
        rotation_degrees=rotation,
        nb_frames=nb_frames,
        vfr=vfr,
        extension=path.suffix.lower(),
        nb_frames_estimated=nb_frames_estimated,
        warnings=warnings,
    )


def validate_metadata(metadata: VideoMetadata, config: dict[str, Any]) -> ValidationResult:
    """Validate that the file is usable by the pipeline."""
    errors: list[str] = []
    warnings = list(metadata.warnings)

    if metadata.codec == "unknown" or metadata.width == 0:
        errors.append("missing_video_stream")
    if metadata.duration_seconds <= 0:
        errors.append("zero_or_unreadable_duration")
    if metadata.fps <= 0:
        errors.append("unparseable_fps")

    supported = tuple(
        extension.lower()
        for extension in config.get(
            "supported_extensions", [".mov", ".mp4", ".m4v", ".avi", ".mkv"]
        )
    )
    if metadata.extension and metadata.extension.lower() not in supported:
        warnings.append(
            f"extension_not_in_supported_list={metadata.extension} "
            f"(supported: {', '.join(supported)})"
        )

    min_res = config.get("min_resolution", {})
    if metadata.width and metadata.height:
        if metadata.width < int(min_res.get("width", 0)) or metadata.height < int(
            min_res.get("height", 0)
        ):
            errors.append(
                f"resolution_below_minimum ({metadata.width}x{metadata.height} < "
                f"{min_res.get('width')}x{min_res.get('height')})"
            )

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


def ffprobe_version() -> str:
    """Return the first line of ``ffprobe -version`` for the audit trail."""
    executable = shutil.which("ffprobe")
    if executable is None:
        return "unavailable"
    try:
        completed = subprocess.run(
            [executable, "-version"], capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace",
        )
        return completed.stdout.splitlines()[0].strip()
    except (subprocess.CalledProcessError, OSError):  # pragma: no cover - defensive
        return "unknown"


def read_input(path: Path, config: dict[str, Any]) -> tuple[VideoMetadata, ValidationResult]:
    """Hash, probe, and validate an input file."""
    if not path.exists():
        raise IngestError(f"input file not found: {path}")
    file_hash = sha256_file(path)
    metadata = parse_metadata(path, file_hash)
    validation = validate_metadata(metadata, config)
    return metadata, validation

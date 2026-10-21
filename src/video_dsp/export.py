"""Auditable JSON export and representative frame images."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .sampling import FrameReader


def jsonable(value: Any) -> Any:
    """Recursively convert numpy types into JSON-serializable Python types."""
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(document: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(jsonable(document), handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def build_output(
    *,
    schema_version: str,
    interpretation: str,
    pipeline: dict,
    source: dict,
    selection_request: dict,
    config: dict,
    config_hash_value: str,
    aggregation_strategy: dict,
    boundary_detection: dict,
    boundary_times: list[float],
    frame_distances: list[dict],
    selected_shots: list[dict],
    rejected_shots: list[dict],
    summary: dict,
    analysis_resolution: dict,
    extra: dict | None = None,
) -> dict:
    document = {
        "schema_version": schema_version,
        "generated_at_utc": utc_now_iso(),
        "interpretation": interpretation,
        "pipeline": pipeline,
        "source": source,
        "selection_request": selection_request,
        "analysis_resolution": analysis_resolution,
        "config": config,
        "config_hash": config_hash_value,
        "aggregation_strategy": aggregation_strategy,
        "boundary_detection": boundary_detection,
        "detected_boundaries_seconds": boundary_times,
        "frame_distances": frame_distances,
        "selected_shots": selected_shots,
        "rejected_shots": rejected_shots,
        "summary": summary,
    }
    if extra:
        for key, value in extra.items():
            document[key] = value
    return document


def build_error_output(
    *,
    schema_version: str,
    interpretation: str,
    pipeline: dict,
    source: dict,
    config: dict,
    config_hash_value: str,
    errors: list[str],
    warnings: list[str],
) -> dict:
    return {
        "schema_version": schema_version,
        "generated_at_utc": utc_now_iso(),
        "interpretation": interpretation,
        "pipeline": pipeline,
        "source": source,
        "config_hash": config_hash_value,
        "config": config,
        "error": {
            "errors": list(errors),
            "warnings": list(warnings),
            "aborted": True,
        },
        "selected_shots": [],
        "rejected_shots": [],
        "summary": {
            "total_shots": 0,
            "passed_gates": 0,
            "selected": 0,
            "samples_analyzed": 0,
            "warnings": list(warnings),
            "aborted": True,
        },
    }


def export_representative_frames(
    input_path: Path,
    selected_shots: list[dict],
    output_dir: Path,
) -> list[str]:
    """Write a full-resolution PNG for each selected shot's representative frame."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("shot_*_rank*_t*.png"):
        stale.unlink()
    written: list[str] = []
    with FrameReader(input_path) as reader:
        for shot in selected_shots:
            index = int(shot["selected_frame_index"])
            frame = reader.read_index(index)
            if frame is None:
                shot["warnings"].append(
                    f"representative_frame_decode_failed (frame_index={index})"
                )
                continue
            filename = (
                f"{shot['shot_id']}_rank{shot['rank']:02d}"
                f"_t{shot['selected_frame_timestamp']:.3f}.png"
            )
            target = output_dir / filename
            if not cv2.imwrite(str(target), frame):
                shot["warnings"].append(
                    f"representative_frame_write_failed (path={target})"
                )
                continue
            shot["selected_frame_image_path"] = str(target.as_posix())
            written.append(str(target))
    return written


def export_shot_thumbnails(
    input_path: Path,
    shots: list[dict],
    output_dir: Path,
    *,
    max_dimension: int = 480,
    quality: int = 80,
) -> list[str]:
    """Write a small JPEG preview per shot and record its size on the shot record.

    The gallery needs one cheap image per recommended and discarded shot; the full-resolution
    PNG stays reserved for the shots the user can download. Decoding happens once per shot
    here, at run time, so the client never has to open the video (RF-29).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("*.jpg"):
        stale.unlink()

    limit = max(1, int(max_dimension))
    parameters = [int(cv2.IMWRITE_JPEG_QUALITY), max(1, min(100, int(quality)))]
    written: list[str] = []
    with FrameReader(input_path) as reader:
        for shot in shots:
            index = int(shot["selected_frame_index"])
            frame = reader.read_index(index)
            if frame is None:
                shot["warnings"].append(f"thumbnail_decode_failed (frame_index={index})")
                continue
            height, width = frame.shape[:2]
            scale = min(1.0, limit / max(height, width))
            if scale < 1.0:
                frame = cv2.resize(
                    frame,
                    (max(1, round(width * scale)), max(1, round(height * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            target = output_dir / f"{shot['shot_id']}.jpg"
            if not cv2.imwrite(str(target), frame, parameters):
                shot["warnings"].append(f"thumbnail_write_failed (path={target})")
                continue
            shot["thumb_path"] = target.as_posix()
            shot["thumb_width"] = int(frame.shape[1])
            shot["thumb_height"] = int(frame.shape[0])
            written.append(str(target))
    return written

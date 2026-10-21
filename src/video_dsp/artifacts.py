"""Run artifacts: per-sample CSV, per-shot CSV, and the compact UI document.

The audit JSON remains the legal record. These artifacts exist so a client (the
Streamlit UI today, anything later) never has to re-decode a 4K file to change a weight.

Determinism note: gzip embeds a modification time by default, which would make two runs
with identical input differ. ``deterministic_gzip`` writes ``mtime=0`` and an empty
filename so the bytes are reproducible.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import config_hash, short_hash
from .metrics_spec import dimension_catalog, field_catalog
from .presets import list_presets

METRIC_EXCLUSIONS = {"histogram", "motion_gray"}


def run_id(source_hash: str, config: dict) -> str:
    """Deterministic identifier for a (video, config) pair."""
    return f"{short_hash(source_hash, 12)}_{short_hash(config_hash(config), 8)}"


def run_directory(root: Path, source_hash: str, config: dict) -> Path:
    return root / run_id(source_hash, config)


def sample_columns(samples: list[dict]) -> list[str]:
    metric_keys: set[str] = set()
    histogram_length = 0
    for sample in samples:
        for key, value in sample["metrics"].items():
            if key in METRIC_EXCLUSIONS:
                if key == "histogram":
                    histogram_length = max(histogram_length, len(value))
                continue
            if isinstance(value, (int, float)):
                metric_keys.add(key)
    ordered = sorted(metric_keys)
    ordered.extend(f"hist_{index:02d}" for index in range(histogram_length))
    return ["frame_index", "timestamp_seconds", *ordered]


def _iter_sample_rows(samples: list[dict], columns: list[str]) -> Iterable[list[Any]]:
    for sample in samples:
        metrics = sample["metrics"]
        histogram = metrics.get("histogram")
        row: list[Any] = [sample["frame_index"], f"{sample['timestamp_seconds']:.6f}"]
        for column in columns[2:]:
            if column.startswith("hist_"):
                index = int(column.split("_", 1)[1])
                value = (
                    float(histogram[index])
                    if histogram is not None and index < len(histogram)
                    else 0.0
                )
                row.append(f"{value:.6f}")
            else:
                row.append(f"{float(metrics[column]):.6f}")
        yield row


def write_samples_csv(
    samples: list[dict], path: Path, deterministic_gzip: bool = True
) -> dict[str, Any]:
    """Write per-sample metrics as CSV (gzip-compressed by default)."""
    columns = sample_columns(samples)
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in _iter_sample_rows(samples, columns):
        writer.writerow(row)
    payload = buffer.getvalue().encode("utf-8")

    with path.open("wb") as raw:
        mtime = 0 if deterministic_gzip else None
        # ``filename=""`` matters: GzipFile would otherwise embed the output path in the
        # header, making two otherwise identical runs differ byte for byte.
        with gzip.GzipFile(
            fileobj=raw, mode="wb", filename="", mtime=mtime
        ) as compressed:
            compressed.write(payload)
    return {
        "path": path.as_posix(),
        "columns": len(columns),
        "rows": len(samples),
        "bytes": path.stat().st_size,
        "deterministic_gzip": deterministic_gzip,
    }


SHOT_COLUMNS = (
    "shot_id",
    "rank",
    "plain_rank",
    "status",
    "start_time_seconds",
    "end_time_seconds",
    "duration_seconds",
    "sample_count",
    "total_score",
    "gate_passed",
    "selection_reason",
    "thumb_path",
)


def write_shots_csv(shots: list[dict], path: Path) -> dict[str, Any]:
    """Write one flat row per shot: identifiers, scores, dimensions and raw metrics."""
    dimension_keys = sorted({key for shot in shots for key in shot["dimension_scores"]})
    metric_keys = sorted({key for shot in shots for key in shot["metrics"]})
    columns = [
        *SHOT_COLUMNS,
        *(f"dim_{key}" for key in dimension_keys),
        *metric_keys,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for shot in shots:
            row: list[Any] = []
            for column in SHOT_COLUMNS:
                value = shot.get(column)
                if value is None:
                    row.append("")
                elif isinstance(value, float):
                    row.append(f"{value:.6f}")
                elif isinstance(value, bool):
                    row.append("1" if value else "0")
                else:
                    row.append(value)
            for key in dimension_keys:
                row.append(f"{float(shot['dimension_scores'][key]):.6f}")
            for key in metric_keys:
                row.append(f"{float(shot['metrics'][key]):.6f}")
            writer.writerow(row)
    return {
        "path": path.as_posix(),
        "columns": len(columns),
        "rows": len(shots),
    }


def build_ui_document(
    *,
    interpretation: str,
    pipeline: dict,
    source: dict,
    config: dict,
    config_hash_value: str,
    analysis_resolution: dict,
    boundaries: list[dict],
    boundary_positions: list[int],
    boundary_detection: dict,
    shot_records: list[dict],
    result: dict[str, Any],
    aggregation: dict[str, str],
    motion_aggregation: dict[str, str],
    artifacts: dict[str, Any],
    distances: list[dict] | None = None,
    evaluation: dict[str, Any] | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build the compact document consumed by the UI.

    It deliberately duplicates the ranked result instead of recomputing it on load, so
    the client can show the CLI's exact answer before the user touches a slider.
    """
    warnings = list(result["warnings"])
    if extra_warnings:
        warnings.extend(extra_warnings)
    return {
        "schema_version": config["schema_version"],
        "generated_at_utc": None,
        "interpretation": interpretation,
        "pipeline": pipeline,
        "source": source,
        "config_hash": config_hash_value,
        "config": config,
        "analysis_resolution": analysis_resolution,
        "presets": list_presets(),
        "active_preset": config["preset"],
        "field_catalog": field_catalog(),
        "dimension_catalog": dimension_catalog(),
        "normalization": result["normalization"],
        "score_weights_effective": result["score_weights_effective"],
        "aggregation_strategy": aggregation,
        "motion_aggregation_strategy": motion_aggregation,
        "boundaries": boundaries,
        "boundary_positions": list(boundary_positions),
        "boundary_detection": boundary_detection,
        "distances": distances or [],
        "shots": result["shots"],
        "selected": result["selected"],
        "displaced_by_diversity": result["displaced_by_diversity"],
        "summary": result["summary"],
        "evaluation": evaluation,
        "artifacts": artifacts,
        "warnings": _dedupe(warnings),
    }


def write_ui_document(document: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, indent=1, ensure_ascii=False, sort_keys=False)
        handle.write("\n")
    return path


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

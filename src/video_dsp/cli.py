"""Command-line entry point for the shot technical selector.

The CLI is orchestration only: decode, measure, detect, then delegate every scoring
decision to :mod:`video_dsp.selection_service`. That keeps the CLI and the UI on the
same code path, so a weight changed in the UI and a config changed here cannot diverge.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .aggregation import aggregation_strategy, motion_aggregation_strategy
from .artifacts import (
    build_ui_document,
    run_directory,
    write_samples_csv,
    write_shots_csv,
    write_ui_document,
)
from .boundaries import render_boundary_montages
from .config import (
    CALIBRATION_LABEL,
    PIPELINE_NAME,
    PIPELINE_VERSION,
    SCHEMA_VERSION,
    SUPPORTED_EXTENSIONS,
    config_hash,
    deep_merge,
    load_config,
)
from .evaluation import evaluate
from .export import (
    build_error_output,
    build_output,
    export_representative_frames,
    export_shot_thumbnails,
    write_json,
)
from .features import compute_frame_metrics, motion_thumbnail, resize_for_analysis
from .ingest import IngestError, VideoMetadata, ffprobe_version, read_input
from .labels import LABELS_SCHEMA_VERSION, LabelsError, load_labels
from .presets import list_presets
from .sampling import VideoDecodeError, iter_sampled_frames
from .selection_service import (
    STATUS_REJECTED_FLOOR,
    STATUS_REJECTED_GATE,
    build_shot_records,
    rank,
)
from .shot_detection import compute_distances, detect_boundaries, rebuild_shots

INTERPRETATION = "technical_dsp_draft_only"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video_dsp",
        description=(
            "Deterministic classical-DSP shot selector for .mov, .mp4, .m4v and .avi files."
        ),
    )
    parser.add_argument(
        "input",
        type=Path,
        help=f"Path to a video file ({', '.join(SUPPORTED_EXTENSIONS)}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Audit JSON path (default: <run-dir>/audit.json).",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=(
            "Artifact directory (default: out/runs/<video-hash>_<config-hash>). "
            "Contains ui.json, samples.csv.gz, shots.csv and media/."
        ),
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=None,
        help=f"Preference preset ({', '.join(sorted(list_presets()))}).",
    )
    parser.add_argument("--analysis-fps", type=float, default=None)
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--min-shot-duration", type=float, default=None)
    parser.add_argument("--max-shot-duration", type=float, default=None)
    parser.add_argument(
        "--peak-prominence",
        type=float,
        default=None,
        help=(
            "A boundary peak must exceed the median distance of its neighbourhood by "
            "this factor. 0 disables the filter."
        ),
    )
    parser.add_argument(
        "--merge-similarity",
        type=float,
        default=None,
        help=(
            "Merge adjacent shots whose averaged histograms are at least this similar "
            "(Bhattacharyya). 1.0 disables merging. Use it to counter over-segmentation."
        ),
    )
    parser.add_argument(
        "--diversity-weight",
        type=float,
        default=None,
        help="MMR diversity weight in [0,1]. 0 keeps a pure score ranking.",
    )
    parser.add_argument(
        "--quality-floor",
        type=float,
        default=None,
        help="Reject gate-passing shots below this total score. Negative disables it.",
    )
    parser.add_argument(
        "--analysis-max-dimension",
        type=int,
        default=None,
        help="Longest analysis edge in pixels; 0 disables resizing (native).",
    )
    parser.add_argument(
        "--config", type=Path, default=None, help="JSON file with config overrides."
    )
    parser.add_argument(
        "--thumbnails",
        type=Path,
        default=None,
        help="Directory for representative frames (default: <media>/representatives).",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=None,
        help="labels.json to evaluate this run against (level A verdicts, level B pairs).",
    )
    parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="Write only the audit JSON, skipping ui.json, CSV and media.",
    )
    parser.add_argument(
        "--no-montage",
        action="store_true",
        help="Skip the boundary montage images.",
    )
    return parser


def _cli_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if args.analysis_fps is not None:
        overrides["analysis_fps"] = args.analysis_fps
    if args.top_n is not None:
        overrides["top_n"] = args.top_n
    gates: dict[str, Any] = {}
    if args.min_shot_duration is not None:
        gates["min_shot_duration_s"] = args.min_shot_duration
    if args.max_shot_duration is not None:
        gates["max_shot_duration_s"] = args.max_shot_duration
    if gates:
        overrides["hard_gates"] = gates
    if args.merge_similarity is not None or args.peak_prominence is not None:
        detection: dict[str, Any] = {}
        if args.merge_similarity is not None:
            detection["merge_similarity"] = args.merge_similarity
        if args.peak_prominence is not None:
            detection["peak_prominence_ratio"] = args.peak_prominence
        overrides["shot_detection"] = detection
    if args.diversity_weight is not None:
        overrides["diversity"] = {"weight": args.diversity_weight}
    if args.quality_floor is not None:
        if args.quality_floor < 0:
            overrides["quality_floor"] = {"enabled": False}
        else:
            overrides["quality_floor"] = {
                "enabled": True,
                "min_total_score": args.quality_floor,
            }
    if args.analysis_max_dimension is not None:
        if args.analysis_max_dimension <= 0:
            overrides["analysis_resize"] = {"enabled": False}
        else:
            overrides["analysis_resize"] = {
                "enabled": True,
                "max_dimension": args.analysis_max_dimension,
            }
    if args.no_montage:
        overrides["boundary_montage"] = {"enabled": False}
    if args.no_artifacts:
        overrides["artifacts"] = {
            "samples_csv": False,
            "shots_csv": False,
            "ui_json": False,
        }
    return overrides


def resolve_config(args: argparse.Namespace) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if args.config is not None:
        file_overrides = json.loads(Path(args.config).read_text(encoding="utf-8"))
        deep_merge(merged, file_overrides)
    deep_merge(merged, _cli_overrides(args))
    return load_config(merged, preset=args.preset)


def pipeline_info() -> dict[str, Any]:
    return {
        "name": PIPELINE_NAME,
        "version": PIPELINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "labels_schema_version": LABELS_SCHEMA_VERSION,
        "deterministic": True,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "opencv_version": cv2.__version__,
        "ffprobe_version": ffprobe_version(),
    }


def analysis_resolution(width: int, height: int, config: dict) -> dict[str, Any]:
    resize = config.get("analysis_resize", {})
    if not resize.get("enabled"):
        return {
            "enabled": False,
            "max_dimension": None,
            "width": width,
            "height": height,
            "note": "native measurement resolution",
        }
    max_dimension = int(resize.get("max_dimension", 1280))
    longest = max(width, height)
    scale = min(1.0, max_dimension / longest) if longest else 1.0
    return {
        "enabled": True,
        "max_dimension": max_dimension,
        "width": int(round(width * scale)),
        "height": int(round(height * scale)),
        "interpolation": resize.get("interpolation", "area"),
        "note": "documented measurement resolution, not enhancement",
    }


def _write_error(
    out_path: Path,
    *,
    input_path: Path,
    metadata: VideoMetadata | None,
    config: dict,
    pipeline: dict,
    hash_value: str,
    errors: list[str],
    warnings: list[str],
    analysis: dict[str, Any] | None = None,
) -> None:
    source: dict[str, Any] = {"path": str(input_path)}
    if metadata is not None:
        source = metadata.to_dict()
    if analysis is not None:
        source["analysis_resolution"] = analysis
    document = build_error_output(
        schema_version=SCHEMA_VERSION,
        interpretation=INTERPRETATION,
        pipeline=pipeline,
        source=source,
        config=config,
        config_hash_value=hash_value,
        errors=errors,
        warnings=warnings,
    )
    write_json(document, out_path)


def _find_labels(args: argparse.Namespace, run_dir: Path) -> Path | None:
    if args.labels is not None:
        return Path(args.labels)
    candidates = [
        run_dir / "labels.json",
        Path(args.input).with_suffix(".labels.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _collect_samples(input_path: Path, config: dict) -> tuple[list[dict], tuple[int, int] | None]:
    samples: list[dict] = []
    decoded_size: tuple[int, int] | None = None
    thumb_dimension = int(config.get("motion", {}).get("thumb_max_dimension", 96))
    for frame in iter_sampled_frames(input_path, config["analysis_fps"]):
        if decoded_size is None:
            decoded_size = (frame.bgr.shape[1], frame.bgr.shape[0])
        analysis_frame = resize_for_analysis(frame.bgr, config)
        samples.append(
            {
                "frame_index": frame.frame_index,
                "timestamp_seconds": frame.timestamp_seconds,
                "metrics": compute_frame_metrics(analysis_frame, config),
                "motion_gray": motion_thumbnail(analysis_frame, thumb_dimension),
            }
        )
        if len(samples) % 200 == 0:
            print(f"[video_dsp] sampled {len(samples)} frames...", file=sys.stderr)
    return samples, decoded_size


def run(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    input_path = Path(args.input)
    pipeline = pipeline_info()
    hash_value = config_hash(config)

    metadata: VideoMetadata | None = None
    try:
        metadata, validation = read_input(input_path, config)
    except IngestError as exc:
        fallback = Path(args.out) if args.out else Path("out/shot_selection.json")
        _write_error(
            fallback,
            input_path=input_path,
            metadata=None,
            config=config,
            pipeline=pipeline,
            hash_value=hash_value,
            errors=[str(exc)],
            warnings=[f"thresholds_calibration={CALIBRATION_LABEL}"],
        )
        print(f"[video_dsp] ingestion failed: {exc}", file=sys.stderr)
        return 2

    run_dir = (
        Path(args.run_dir)
        if args.run_dir
        else run_directory(Path("out/runs"), metadata.file_hash_sha256, config)
    )
    media_dir = run_dir / "media"
    audit_path = Path(args.out) if args.out else run_dir / "audit.json"
    artifacts_enabled = bool(config["artifacts"].get("ui_json", True))

    analysis = analysis_resolution(metadata.width, metadata.height, config)

    if not validation.ok:
        _write_error(
            audit_path,
            input_path=input_path,
            metadata=metadata,
            config=config,
            pipeline=pipeline,
            hash_value=hash_value,
            errors=validation.errors,
            warnings=validation.warnings,
            analysis=analysis,
        )
        print(
            f"[video_dsp] validation failed: {'; '.join(validation.errors)}",
            file=sys.stderr,
        )
        return 1

    try:
        samples, decoded_size = _collect_samples(input_path, config)
    except VideoDecodeError as exc:
        _write_error(
            audit_path,
            input_path=input_path,
            metadata=metadata,
            config=config,
            pipeline=pipeline,
            hash_value=hash_value,
            errors=[f"opencv_decode_failed: {exc}"],
            warnings=validation.warnings,
            analysis=analysis,
        )
        print(f"[video_dsp] decode failed: {exc}", file=sys.stderr)
        print(
            "[video_dsp] OpenCV could not decode this container. Convert it first, e.g.: "
            f'ffmpeg -i "{input_path}" -c:v libx264 -crf 18 -c:a copy converted.mp4',
            file=sys.stderr,
        )
        return 2

    if len(samples) < 2:
        message = "opencv_decode_failed_or_no_frames_decoded"
        _write_error(
            audit_path,
            input_path=input_path,
            metadata=metadata,
            config=config,
            pipeline=pipeline,
            hash_value=hash_value,
            errors=[message],
            warnings=validation.warnings,
            analysis=analysis,
        )
        print(f"[video_dsp] {message}", file=sys.stderr)
        return 2

    source = metadata.to_dict()
    if decoded_size is not None:
        source["decoded_width"] = decoded_size[0]
        source["decoded_height"] = decoded_size[1]
        analysis = analysis_resolution(decoded_size[0], decoded_size[1], config)

    detection = config["shot_detection"]
    distances = compute_distances(samples, detection["weights"])
    min_gap_samples = max(
        1, int(round(detection["min_gap_seconds"] * config["analysis_fps"]))
    )
    boundary_positions, boundary_evidence = detect_boundaries(
        distances,
        detection["mad_multiplier"],
        min_gap_samples,
        prominence_ratio=float(detection.get("peak_prominence_ratio", 2.0)),
        prominence_radius=int(detection.get("peak_prominence_radius", 5)),
        prominence_guard=int(detection.get("peak_prominence_guard", 1)),
    )
    boundary_evidence["min_gap_samples"] = min_gap_samples

    shots, rebuild_evidence = rebuild_shots(
        samples,
        boundary_positions,
        merge_similarity=float(detection.get("merge_similarity", 1.0)),
        min_duration=config["hard_gates"]["min_shot_duration_s"],
        max_duration=config["hard_gates"]["max_shot_duration_s"],
    )
    boundary_evidence["rebuild"] = rebuild_evidence

    shot_records = build_shot_records(shots, distances, config)
    result = rank(shot_records, config)

    selected = result["selected"]
    rejected = [
        shot
        for shot in result["shots"]
        if shot["status"] in {STATUS_REJECTED_GATE, STATUS_REJECTED_FLOOR}
    ]
    unselected = [
        shot for shot in result["shots"] if shot["status"] == "passing_unselected"
    ]

    labels_path = _find_labels(args, run_dir)
    evaluation = None
    if labels_path is not None:
        try:
            labels = load_labels(labels_path)
            evaluation = evaluate(result["shots"], selected, labels, config["top_n"])
        except LabelsError as exc:
            print(f"[video_dsp] labels ignored: {exc}", file=sys.stderr)
            result["warnings"].append(f"labels_invalid: {exc}")

    written_frames: list[str] = []
    written_thumbs: list[str] = []
    montages: list[dict] = []
    representatives_dir = (
        Path(args.thumbnails) if args.thumbnails else media_dir / "representatives"
    )
    thumbnails_config = config["artifacts"].get("thumbnails", {})
    thumbs_dir = media_dir / "thumbs"
    artifacts: dict[str, Any] = {
        "run_dir": run_dir.as_posix(),
        "audit_json": audit_path.as_posix(),
        "ui_json": (run_dir / "ui.json").as_posix() if artifacts_enabled else None,
        "samples_csv": (
            (run_dir / "samples.csv.gz").as_posix()
            if config["artifacts"].get("samples_csv", True) and not args.no_artifacts
            else None
        ),
        "shots_csv": (
            (run_dir / "shots.csv").as_posix()
            if config["artifacts"].get("shots_csv", True) and not args.no_artifacts
            else None
        ),
        "representatives_dir": representatives_dir.as_posix(),
        "boundaries_dir": (
            (media_dir / "boundaries").as_posix()
            if config["boundary_montage"].get("enabled", True) and not args.no_artifacts
            else None
        ),
        "labels_json": labels_path.as_posix() if labels_path else None,
        "evaluation_json": (
            (run_dir / "evaluation.json").as_posix() if evaluation is not None else None
        ),
    }

    if artifacts_enabled or args.thumbnails:
        written_frames = export_representative_frames(
            input_path, selected, representatives_dir
        )

    if artifacts_enabled and thumbnails_config.get("enabled", True):
        preview_shots = [
            shot
            for shot in result["shots"]
            if shot["status"] in {"selected", "rejected_gate", "rejected_floor"}
        ]
        written_thumbs = export_shot_thumbnails(
            input_path,
            preview_shots,
            thumbs_dir,
            max_dimension=int(thumbnails_config.get("max_dimension", 480)),
            quality=int(thumbnails_config.get("quality", 80)),
        )

    artifacts["shot_thumbs_dir"] = thumbs_dir.as_posix() if written_thumbs else None

    if artifacts["boundaries_dir"] is not None:
        montages = render_boundary_montages(
            input_path,
            boundary_evidence["peaks"],
            media_dir / "boundaries",
            config,
            fps=metadata.fps,
        )

    if artifacts["samples_csv"] is not None:
        write_samples_csv(
            samples,
            run_dir / "samples.csv.gz",
            deterministic_gzip=bool(config["artifacts"].get("deterministic_gzip", True)),
        )
    if artifacts["shots_csv"] is not None:
        write_shots_csv(result["shots"], run_dir / "shots.csv")

    warnings = list(validation.warnings)
    warnings.append(f"thresholds_calibration={CALIBRATION_LABEL}")
    warnings.append("artifact_metrics_not_measured (blockiness/banding/mosquito)")
    expected_thumbs = len(
        [
            shot
            for shot in result["shots"]
            if shot["status"] in {"selected", "rejected_gate", "rejected_floor"}
        ]
    )
    if not thumbnails_config.get("enabled", True):
        warnings.append("shot_thumbnails_skipped (disabled in config)")
    elif not artifacts_enabled:
        warnings.append("shot_thumbnails_skipped (--no-artifacts)")
    elif len(written_thumbs) < expected_thumbs:
        warnings.append(
            f"shot_thumbnails_incomplete ({len(written_thumbs)}/{expected_thumbs})"
        )
    if analysis.get("enabled"):
        warnings.append(
            "analysis_resolution_resized_for_speed "
            f"({analysis['width']}x{analysis['height']})"
        )
    fallback_shots = [
        shot["shot_id"]
        for shot in result["shots"]
        if shot.get("stability_source") == "instability_fallback"
    ]
    if fallback_shots:
        warnings.append(
            "stability_from_instability_fallback "
            f"({len(fallback_shots)} shots, low phase-correlation confidence)"
        )
    if result["warnings"]:
        warnings.extend(result["warnings"])
    warnings = list(dict.fromkeys(warnings))

    summary = {
        **result["summary"],
        "samples_analyzed": len(samples),
        "source_duration_seconds": metadata.duration_seconds,
        "thumbnails_written": len(written_frames),
        "shot_thumbs_written": len(written_thumbs),
        "boundary_montages_written": len(montages),
        "warnings": warnings,
        "calibration": config["hard_gates"].get("calibration", CALIBRATION_LABEL),
        "interpretation": INTERPRETATION,
        "evaluation_status": (
            evaluation["status"] if evaluation is not None else "no_labels"
        ),
    }

    selection_request = {
        "preset": config["preset"],
        "preset_label": config.get("preset_label"),
        "top_n": config["top_n"],
        "analysis_fps": config["analysis_fps"],
        "merge_similarity": float(detection.get("merge_similarity", 1.0)),
        "weights": config["score_weights"],
        "weights_effective": config["score_weights_effective"],
        "targets": config["targets"],
        "quality_floor": config["quality_floor"],
        "diversity": config["diversity"],
        "normalization": config["normalization"],
        "hard_gates": config["hard_gates"],
        "ranges": config["ranges"],
    }

    document = build_output(
        schema_version=SCHEMA_VERSION,
        interpretation=INTERPRETATION,
        pipeline=pipeline,
        source=source,
        selection_request=selection_request,
        config=config,
        config_hash_value=hash_value,
        aggregation_strategy=aggregation_strategy(),
        boundary_detection=boundary_evidence,
        boundary_times=[peak["time_mid_seconds"] for peak in boundary_evidence["peaks"]],
        frame_distances=[distance.to_dict() for distance in distances],
        selected_shots=selected,
        rejected_shots=rejected,
        summary=summary,
        analysis_resolution=analysis,
        extra={
            "motion_aggregation_strategy": motion_aggregation_strategy(),
            "normalization": result["normalization"],
            "boundary_montages": montages,
            "evaluation": evaluation,
            "artifacts": artifacts,
            "warnings": warnings,
        },
    )
    document["unselected_shots"] = unselected
    write_json(document, audit_path)

    if evaluation is not None and not args.no_artifacts:
        evaluation_path = run_dir / "evaluation.json"
        write_json(evaluation, evaluation_path)
        artifacts["evaluation_json"] = evaluation_path.as_posix()

    if artifacts_enabled and not args.no_artifacts:
        ui_document = build_ui_document(
            interpretation=INTERPRETATION,
            pipeline=pipeline,
            source=source,
            config=config,
            config_hash_value=hash_value,
            analysis_resolution=analysis,
            boundaries=montages,
            boundary_positions=boundary_positions,
            boundary_detection=boundary_evidence,
            shot_records=shot_records,
            result=result,
            aggregation=aggregation_strategy(),
            motion_aggregation=motion_aggregation_strategy(),
            artifacts=artifacts,
            distances=[distance.to_dict() for distance in distances],
            evaluation=evaluation,
            extra_warnings=warnings,
        )
        ui_document["generated_at_utc"] = document["generated_at_utc"]
        ui_path = write_ui_document(ui_document, run_dir / "ui.json")
        artifacts["ui_json"] = ui_path.as_posix()

    print(
        f"[video_dsp] analyzed {len(samples)} sampled frames, "
        f"{len(result['shots'])} shots, {len(selected)} selected, "
        f"{len(rejected)} rejected, {len(unselected)} passing-but-unselected "
        f"(preset={config['preset']}).",
        file=sys.stderr,
    )
    print(f"[video_dsp] wrote {audit_path}", file=sys.stderr)
    if artifacts["ui_json"]:
        print(f"[video_dsp] wrote {artifacts['ui_json']}", file=sys.stderr)
    if written_frames:
        print(
            f"[video_dsp] wrote {len(written_frames)} representative frames",
            file=sys.stderr,
        )
    if montages:
        print(
            f"[video_dsp] wrote {len(montages)} boundary montages",
            file=sys.stderr,
        )
    if evaluation is not None:
        print(
            f"[video_dsp] evaluation: {evaluation['status']} "
            f"coverage={evaluation['coverage']['fraction']:.2f}",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("[video_dsp] interrupted", file=sys.stderr)
        return 130
    except KeyError as exc:
        print(f"[video_dsp] configuration error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

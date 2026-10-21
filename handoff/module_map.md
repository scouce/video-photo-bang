# Module map

Core modules live in `src/video_dsp/`. Pure DSP functions are unit-tested. The Streamlit
client lives in `app/` and may use pandas/Streamlit; the core may not.

| Module | Purpose | Key functions / types | RF |
|---|---|---|---|
| `config.py` | Defaults, ranges, targets, gates, weights, schema version, config hash | `load_config`, `config_hash`, `deep_merge`, `DEFAULT_CONFIG`, `SUPPORTED_EXTENSIONS` | RF-1, RF-18, RF-19, RF-35 |
| `presets.py` | Seven preference presets: weights, target bands, floor, normalization method | `PRESETS`, `list_presets`, `get_preset` | RF-18, RF-19, RF-31 |
| `metrics_spec.py` | Declarative field catalog, 8 dimensions, components with units and modes | `FIELD_CATALOG`, `DIMENSIONS`, `DIMENSION_ORDER`, `dimension_components`, `field_catalog`, `dimension_catalog` | RF-18 |
| `ingest.py` | File hash, ffprobe parsing, container/codec validation | `sha256_file`, `parse_fps`, `parse_metadata`, `validate_metadata`, `read_input`, `ffprobe_version` | RF-2, RF-3, RF-5, RF-36, RF-37 |
| `sampling.py` | Sequential sampling, random-access `FrameReader` for export | `iter_sampled_frames`, `read_frame_at_index`, `FrameReader`, `SampledFrame` | RF-4, RF-13 |
| `features.py` | Pure per-frame metrics: sharpness, exposure, texture, color, motion thumbnail | `to_luminance`, `resize_for_analysis`, `compute_variance_laplacian`, `compute_tenengrad`, `compute_edge_density`, `compute_luminance_stats`, `compute_histogram_entropy`, `compute_local_contrast`, `compute_color_stats`, `compute_frame_metrics`, `motion_thumbnail` | RF-6, RF-7, RF-38 |
| `shot_detection.py` | Distances, phase correlation, robust threshold, peaks, shot construction, merging | `FrameDistance`, `chi_square_distance`, `gradient_log_distance`, `edge_distance`, `estimate_translation`, `compute_distances`, `distances_from_dicts`, `robust_mad`, `mad_threshold`, `find_local_maxima`, `enforce_min_gap`, `detect_boundaries`, `build_shots`, `enforce_min_duration`, `split_long_shots`, `merge_similar_shots`, `rebuild_shots`, `bhattacharyya_similarity`, `shot_histogram_signature` | RF-8 to RF-12 |
| `aggregation.py` | Shot-level aggregation plus translation-derived motion statistics | `AGGREGATION`, `aggregate_shot_metrics`, `aggregation_strategy`, `motion_aggregation_strategy` | RF-14, RF-15, RF-16 |
| `normalization.py` | Percentile/absolute/band normalization with provenance and explicit fallbacks | `apply_transform`, `percentile_bounds`, `build_normalization`, `normalize_value`, `dimension_scores`, `combined_score` | RF-17, RF-18, RF-19, RF-20, RF-21, RF-40 |
| `selection_service.py` | **Single scoring path**: records, gates, floor, MMR, ranking | `build_shot_records`, `resolve_preferences`, `evaluate_gates`, `mmr_select`, `rank`, `recompute` | RF-21 to RF-26 |
| `boundaries.py` | Five-frame montage strip per detected boundary | `render_boundary_montages` | RF-13 |
| `artifacts.py` | `ui.json`, deterministic `samples.csv.gz`, `shots.csv`, run id | `run_id`, `run_directory`, `write_samples_csv`, `write_shots_csv`, `build_ui_document`, `write_ui_document` | RF-27, RF-28, RF-29 |
| `labels.py` | Versioned annotation store: level A verdicts, boundary verdicts, level B pairs | `empty_labels`, `load_labels`, `save_labels`, `validate_labels`, `record_shot_label`, `record_boundary_label`, `record_pair_label`, `coverage` | RF-32, RF-34 |
| `evaluation.py` | Precision/recall/NDCG, gate false rejects, dimension separation, pairwise accuracy | `evaluate`, `ndcg_at_k` | RF-33 |
| `export.py` | Audit JSON, error JSON, full-resolution PNG export | `jsonable`, `utc_now_iso`, `write_json`, `build_output`, `build_error_output`, `export_representative_frames` | RF-1, RF-27, RF-35, RF-36 |
| `cli.py` | Argument parsing and orchestration only; delegates all scoring | `build_parser`, `resolve_config`, `analysis_resolution`, `run`, `main` | RF-1 to RF-40 |
| `scoring.py` | **Legacy, unused.** v0.1.0 four-dimension absolute formula kept for reference | — | — |
| `app/ui.py` | Streamlit client: six tabs, live re-ranking, annotation writing, config export | `main`, `compute_result`, `build_config` | RF-30, RF-31 |

## Data flow

```text
video --> ingest (hash + metadata) --> sampling --> features (per frame)
      --> shot_detection (distances + translation, boundaries, shots, merge)
      --> aggregation (per-shot metrics + motion statistics)
      --> selection_service (normalize -> 8 dimensions -> gates -> floor -> MMR)
      --> export + artifacts (audit.json, ui.json, CSV, PNG)
                                   |
                                   v
                          app/ui.py (re-rank, rebuild, annotate)
```

The client never decodes video. It re-ranks from `ui.json`, and when the merge threshold
moves it reconstructs the samples from `samples.csv.gz` and the recorded frame distances,
then calls the same `build_shot_records` and `rank` used by the CLI.

## Config surface (`config.py`)

| Key | Default | Notes |
|---|---|---|
| `analysis_fps` | `5.0` | Sampling rate. |
| `top_n` | `10` | Selected shots. |
| `analysis_resize` | enabled, 1280 px, area | Documented measurement resolution. |
| `shot_detection.weights` | hist 0.65, grad 0.20, edge 0.15 | Combined distance. |
| `shot_detection.mad_multiplier` | `3.0` | Robust threshold. |
| `shot_detection.min_gap_seconds` | `0.4` | Minimum boundary spacing. |
| `shot_detection.merge_similarity` | `1.0` | Bhattacharyya threshold; 1.0 disables merging. |
| `ranges` | VoL [20, 400], Ten [500, 8000], std [0.05, 0.35], inst [0, 0.35], … | Absolute fallback, tied to 1280-px analysis. |
| `targets` | duration, motion/s, pan, saturation bands | Always absolute. |
| `normalization` | `per_video_percentile`, p5-p95, min 6 shots | Falls back to `ranges` with a recorded reason. |
| `hard_gates` | clips ≤ 0.10, sharpness ≥ 0.15, instability ≤ 0.40, duration 0.5–15 s | Uncalibrated. |
| `quality_floor` | enabled, 0.25 | Separate from gates. |
| `diversity` | enabled, weight 0.25 | MMR over histogram similarity. |
| `score_weights` | preset-dependent, sums to 1.0 | Renormalized over positive weights. |

## Tests

| File | Covers |
|---|---|
| `tests/test_features.py` | Luminance range, sharpness direction, histogram, entropy, local contrast, color stats, motion thumbnail, full catalog coverage. |
| `tests/test_shot_detection.py` | Chi-square symmetry, combined distance, injected peak, min gap, MAD-zero fallback, shot building, merge/split, Bhattacharyya bounds, phase-correlation shift recovery, shot rebuild evidence. |
| `tests/test_normalization.py` | Transform, percentile bounds, provenance, degenerate and too-few fallbacks, band behaviour, zero-weight renormalization, missing-metric warnings. |
| `tests/test_selection_service.py` | Determinism, top-N ordering, gate rejection with failed value, quality floor, passing-unselected, weight sensitivity, MMR diversity, stale-rank reset. |
| `tests/test_labels_evaluation.py` | Label schema validation, upsert, save/load, coverage, precision/recall/NDCG, gate false rejects, dimension separation, pairwise accuracy. |
| `tests/test_artifacts.py` | Run id, deterministic gzip bytes, CSV columns, UI document contract. |
| `tests/test_scoring.py` | Legacy v0.1.0 reference formula (not used by the pipeline). |
| `tests/test_export.py` | Numpy serialization, JSON round-trip, required keys, error document, config hash. |
| `tests/test_ingest.py` | FPS parsing and validation. |
| `tests/test_cli_integration.py` | End-to-end run on `samples/synthetic_test.mov`: audit contract, artifacts, legacy preset normalization. |
| `tests/test_ui_smoke.py` | Streamlit harness: app loads a run, weight change re-ranks, merge threshold rebuilds shots from the CSV. |

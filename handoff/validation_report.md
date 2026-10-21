# Validation report

**Date:** 2026-10-21
**Status:** MVP validated
**Interpretation:** `technical_dsp_draft_only`

## 1. Environment

| Component | Version |
|---|---|
| Python | 3.14.7 |
| numpy | 2.5.4 |
| opencv-python-headless | 5.0.0.93 |
| ffprobe | 8.1 |
| pytest | 9.1.1 |
| ruff | 0.17.1 |

## 2. Quality gates

| Check | Command | Result |
|---|---|---|
| Unit + integration tests | `.\.venv\Scripts\python.exe -m pytest -q` | **38 passed** |
| Lint | `.\.venv\Scripts\ruff.exe check .` | **All checks passed** |

## 3. Synthetic end-to-end test

Sample: `samples/synthetic_test.mov` (9 s, 640×360, 25 fps, three distinct shots).

| Check | Result |
|---|---|
| Detected boundaries | 2.9 s and 5.9 s (exact scene cuts) |
| Shots | 3 |
| Selected | 1 (`testsrc2` shot) |
| Rejected | 2: SMPTE bars (black clipping 0.138 > 0.10) and flat blue (sharpness 0) |
| Representative frame | PNG written and verified |

## 4. Real 4K sample

**Source:** `C:\Users\engcouce\Videos\IMG_1564.mov`

| Property | Value |
|---|---|
| SHA-256 | `ff4f93c9730ec72235e1dbdd40d181d37ce4bd61a7950f244324a557967f3552` |
| Container / codec | `mov,mp4,m4a,3gp,3g2,mj2` / `h264` |
| Stored resolution | 3840×2160 with 90° rotation metadata |
| Decoded resolution | 2160×3840 (decoder applies rotation) |
| FPS | 25.0 nominal, 25.0022 average (VFR flag raised) |
| Duration / frames | 343.49 s / 8588 |
| Analysis resolution | 720×1280 (1280-pixel max edge) |

### Results

| Metric | Value |
|---|---|
| Sampled frames | 1718 |
| Detected boundary positions | 98 |
| Shots after duration rules | 93 |
| Passed gates | 69 |
| Selected (top-N) | 10 |
| Passing but unselected | 59 |
| Rejected | 24 |
| Representative PNGs | 10 (2160×3840, ~6.3–7.4 MB each) |

### Top-10 selected shots

| Rank | Shot | Start–end (s) | Duration (s) | Score |
|---|---|---|---|---|
| 1 | `shot_0016` | 49.20–51.40 | 2.20 | 0.7985 |
| 2 | `shot_0017` | 51.60–56.00 | 4.40 | 0.7983 |
| 3 | `shot_0011` | 31.60–37.00 | 5.40 | 0.7925 |
| 4 | `shot_0018` | 56.20–61.79 | 5.59 | 0.7813 |
| 5 | `shot_0027` | 83.99–84.59 | 0.60 | 0.7705 |
| 6 | `shot_0013` | 41.20–45.00 | 3.80 | 0.7684 |
| 7 | `shot_0004` | 6.60–9.60 | 3.00 | 0.7669 |
| 8 | `shot_0007` | 16.80–23.80 | 7.00 | 0.7662 |
| 9 | `shot_0005` | 9.80–11.60 | 1.80 | 0.7650 |
| 10 | `shot_0024` | 78.19–81.79 | 3.60 | 0.7603 |

### Rejections

All 24 rejected shots failed a single gate: `min_sharpness_score` (threshold 0.15). The
later, softer portion of the clip (roughly after 85 s) does not enter the top-10, while 59
shots passed all gates but ranked outside the top-N.

### JSON contract checks

- Top-level keys present: `schema_version`, `generated_at_utc`, `interpretation`, `pipeline`,
  `source`, `selection_request`, `analysis_resolution`, `config`, `config_hash`,
  `aggregation_strategy`, `boundary_detection`, `detected_boundaries_seconds`,
  `frame_distances`, `selected_shots`, `rejected_shots`, `unselected_shots`, `summary`.
- Every selected shot has raw metrics, normalized metrics, category scores, gates, a
  representative frame timestamp/index, and an existing image path.
- Every rejected shot has gate, value, threshold, and interpretation.
- Warnings recorded: VFR, rotation metadata, uncalibrated thresholds, unmeasured artifact
  metrics, analysis resize.

### Visual check

The rank-1 representative frame was opened and confirmed to be a sharp, correctly oriented
portrait frame at full resolution.

## 5. Determinism

- `config_hash(load_config())` is stable across calls (unit-tested).
- Ranking uses a defined tie-break (score descending, then start time ascending).
- Output differs between runs only in `generated_at_utc` (and therefore the file bytes).

## 6. Known limitations

1. Thresholds and normalization ranges remain `initial_uncalibrated`; ranges were lightly
   tuned on one 4K iPhone sample at 1280-pixel analysis.
2. Ranges are tied to the analysis resolution; disabling the resize requires recalibration.
3. No per-frame CSV (deferred).
4. No blockiness/banding/mosquito artifact metrics.
5. Instability is a frame-distance proxy, not optical flow.
6. The representative frame is the sharpest sampled frame, not necessarily the most
   expressive moment.
7. VFR is detected and warned, not normalized.
8. The technical ranking favors the sharper first ~85 s of this clip; that is not an
   editorial judgment about the remaining footage.

## 7. Verdict

The MVP meets its completion criteria: it runs on the real sample, produces the full audit
JSON and full-resolution representative frames, records raw and normalized metrics and gate
evidence, passes all tests and lint, and keeps the core free of semantic AI. Remaining work
is calibration and feature expansion, tracked in `next_iterations.md`.

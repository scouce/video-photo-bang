# Plan 001 — MOV Shot Technical MVP

Read `docs/constitution.md` and `specs/001-mov-shot-mvp/spec.md` before changing code.
This plan maps every requirement to a module, a pure function, and a test.

## 1. Files and responsibilities

| File | Responsibility | RF coverage |
|---|---|---|
| `src/video_dsp/config.py` | Defaults, weights, gates, ranges, schema version, config hash | RF-11, RF-12, RF-16 |
| `src/video_dsp/ingest.py` | SHA-256, ffprobe parsing, validation, VFR/rotation notes | RF-2, RF-3, RF-17, RF-18 |
| `src/video_dsp/sampling.py` | Sequential sampling at `analysis_fps`, representative frame re-read | RF-4, RF-15 |
| `src/video_dsp/features.py` | Pure per-frame metrics on luminance, documented analysis resize | RF-5, RF-19 |
| `src/video_dsp/shot_detection.py` | Distances, MAD threshold + fallback, local maxima, min gap, shot building | RF-6, RF-7, RF-8, RF-9 |
| `src/video_dsp/aggregation.py` | Shot-level median/mean aggregation and instability proxy | RF-10 |
| `src/video_dsp/scoring.py` | Normalization, category scores, gates, ranking, representative frame | RF-11, RF-12, RF-13, RF-14 |
| `src/video_dsp/export.py` | Audit JSON, error JSON, full-resolution representative frames | RF-1, RF-15, RF-16, RF-17 |
| `src/video_dsp/cli.py` | Argument parsing and pipeline orchestration | RF-1, RF-16, RF-19, RF-20 |
| `tests/*` | Unit and integration coverage | NFR-4 |

## 2. Pure functions

```python
sha256_file(path) -> str
parse_fps(rational) -> float
validate_metadata(metadata, config) -> ValidationResult
to_luminance(bgr) -> np.ndarray
resize_for_analysis(bgr, config) -> np.ndarray
compute_variance_laplacian(gray) -> float
compute_tenengrad(gray) -> float
compute_edge_density(gray, low, high) -> float
compute_luminance_stats(gray, clip_low, clip_high) -> dict
compute_normalized_histogram(gray, bins) -> np.ndarray
chi_square_distance(a, b) -> float
gradient_log_distance(a, b) -> float
edge_distance(a, b) -> float
compute_distances(samples, weights) -> list[FrameDistance]
robust_mad(values) -> (median, mad)
mad_threshold(values, multiplier) -> (median, scaled_dispersion, threshold, source)
find_local_maxima(values, threshold, window) -> list[int]
enforce_min_gap(peaks, values, min_gap) -> list[int]
detect_boundaries(distances, multiplier, min_gap) -> (positions, evidence)
build_shots(samples, positions) -> list[list[sample]]
enforce_min_duration(shots, min_duration) -> list[shot]
split_long_shots(shots, max_duration) -> list[shot]
aggregate_shot_metrics(shot, distances) -> dict
normalize_higher_better(value, low, high) -> float
normalize_lower_better(value, low, high) -> float
compute_category_scores(aggregated, config) -> (categories, normalized)
apply_hard_gates(aggregated, categories, gates) -> (passed, failed)
rank_shots(scored, top_n) -> list[scored]
```

## 3. Algorithm pseudocode

```text
MAIN(input, out, config):
  hash = sha256(input)
  metadata = ffprobe(input)
  validation = validate(metadata, config)
  IF validation failed: write error JSON; exit non-zero

  samples = []
  FOR frame IN sample(input, analysis_fps):
      samples.append({index, timestamp, metrics(frame)})

  distances = combine(histogram_chi2, gradient_log, edge_diff)
  positions, evidence = detect_boundaries(distances, mad_multiplier, min_gap)
  shots = build_shots(samples, positions)
  shots = enforce_min_duration(shots, min_duration)
  shots = split_long_shots(shots, max_duration)

  scored = [score_shot(shot) for shot in shots]
  selected = rank(scored, top_n)
  rejected = [shot for shot in scored if not shot.gate_passed]
  unselected = [shot for shot in scored if shot.gate_passed and not in selected]

  export_representative_frames(input, selected)
  write_json(out, build_output(...))
```

## 4. Metric definitions

- **Luminance:** `Y = 0.114 B + 0.587 G + 0.299 R`, normalized to `[0, 1]` (BT.601).
- **Variance of Laplacian:** variance of `cv2.Laplacian(gray * 255, CV_32F)`.
- **Tenengrad:** mean of `Gx² + Gy²` from 3×3 Sobel on the 0–255 plane.
- **Edge density:** fraction of Canny edge pixels (`low=100`, `high=200`).
- **Black/white clipping:** fraction of pixels `<= 0.02` / `>= 0.98`.
- **Histogram:** 64 bins over `[0, 1]`, normalized to sum 1.
- **Combined distance:** `0.65 * chi2 + 0.20 * |Δlog Tenengrad| + 0.15 * |Δ edge|`.
- **Threshold:** `median + 3.0 * 1.4826 * MAD`; if MAD is degenerate, `0.10 * max`.
- **Instability:** mean of combined distances internal to the shot.

## 5. Category scores

- **Sharpness:** mean of normalized variance-of-Laplacian and Tenengrad.
- **Exposure:** `0.5 * (1 - clipping) + 0.5 * midtone proximity`.
- **Contrast:** normalized luminance standard deviation.
- **Stability:** lower-better normalization of instability (high = stable).
- **Total:** `0.40*sharpness + 0.25*exposure + 0.20*contrast + 0.15*stability`.

## 6. Hard gates

Minimum/maximum duration; maximum black clipping; maximum white clipping; minimum
sharpness score; maximum instability. Each failure records gate, value, threshold, and
interpretation. All thresholds carry `calibration = "initial_uncalibrated"`.

## 7. Technical decisions and rejected alternatives

| Decision | Reason | Rejected alternative |
|---|---|---|
| ffprobe for metadata | Reliable container/codec metadata | OpenCV-only metadata |
| OpenCV for MVP decoding | Simple, adequate for the draft | PyAV in MVP |
| Sequential frame decode | Exact frame indices, deterministic | Seek-based sampling (codec-dependent) |
| Luminance metrics | Matches human sensitivity and the DSP report | RGB-only metrics |
| Histogram + gradient + MAD | Transparent and auditable | PySceneDetect black box |
| MeanAD/relative fallback when MAD=0 | Avoids zero thresholds on static content | Raw MAD only |
| Median aggregation | Robust to outliers | Naive mean |
| Analysis resize to 1280 px max | Keeps 4K runs within minutes; recorded and disable-able | Native 4K only (slow) |
| JSON first | Auditable evidence | Clip export first |

## 8. Testing strategy

Unit tests for pure functions plus one end-to-end test on `samples/synthetic_test.mov`:

- `test_features.py`: luminance range, flat vs edge sharpness, histogram sum, clipping,
  no upscaling.
- `test_shot_detection.py`: chi-square symmetry, combined distance, injected peak, min gap,
  flat signal, MAD-zero fallback, shot building, duration merge/split.
- `test_scoring.py`: normalization bounds, category bounds, gate pass/fail, stability
  direction, deterministic ranking, top-N.
- `test_export.py`: numpy serialization, JSON round-trip, required keys, error document,
  config hash stability.
- `test_ingest.py`: FPS parsing, validation pass/fail.
- `test_cli_integration.py`: full pipeline on the synthetic sample, JSON contract, exported
  images.

Commands:

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```

## 9. RF coverage summary

Every RF maps to at least one module and one test or integration check. RF-1, RF-16, and
RF-17 are covered by `test_cli_integration.py` and `test_export.py`; RF-2 and RF-3 by
`test_ingest.py`; RF-4 to RF-15 by the unit suites; RF-18 to RF-20 by the integration test
and the audit JSON.

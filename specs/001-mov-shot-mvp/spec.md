# Spec 001 — MOV Shot Technical MVP

**Status:** implemented (v0.2.0, calibration-first)
**Interpretation:** `technical_dsp_draft_only`

## 1. Context and objective

Provide a deterministic Python CLI that samples frames from a local video file
(`.mov`, `.mp4`, `.m4v`, `.avi`, `.mkv`), detects shot boundaries with classical DSP
features, computes technical frame and shot metrics, scores eight technical dimensions,
applies hard gates and a quality floor, selects a Top-N that penalizes near-duplicates, and
writes an auditable run directory.

A local Streamlit client reads the same artifacts and lets a person change the preference
weights, gates, target bands and boundary merge, and see the ranking change without
re-decoding the video. The client and the CLI share one scoring service, so a config
exported from the client reproduces the CLI ranking exactly.

The MVP is a **technical draft selector**, not a final editorial judgment. Semantic,
narrative, and aesthetic evaluation are explicitly out of scope.

## 2. Users / actors

- **D.A. (lead developer):** calibrates the technical preferences and reviews the ranking.
- **Developer:** runs the CLI, inspects the JSON, and validates the output.
- **AI assistant:** implements and validates against this spec and the constitution.

## 3. User stories

- **HU-1:** As a lead developer, I want a ranked list of technically strong shots so I can
  review candidate footage quickly.
- **HU-2:** As a developer, I want raw and normalized metrics in the JSON so I can audit why
  a shot was selected or rejected.
- **HU-3:** As a DSP engineer, I want the core pipeline to stay classical and deterministic
  so results are reproducible.
- **HU-4:** As a lead developer, I want my technical preferences to change *which* shots
  reach the Top-N, and to see the effect immediately.
- **HU-5:** As a reviewer, I want to flag false cuts and near-duplicate shots so the
  detection can be corrected without re-editing the video.

## 4. Functional requirements (EARS)

### Ingest and sampling

- **RF-1:** WHEN a valid video path is provided, THE SYSTEM SHALL write the audit JSON to
  the configured output path (default `<run-dir>/audit.json`).
- **RF-2:** WHEN the input file is read, THE SYSTEM SHALL compute and store its SHA-256 hash.
- **RF-3:** WHEN metadata is available, THE SYSTEM SHALL store container, codec, width,
  height, FPS, average FPS, duration, pixel format, color range, color space, rotation,
  frame count, and the VFR flag.
- **RF-4:** WHILE sampling frames, THE SYSTEM SHALL process only frames selected at the
  configured `analysis_fps`.
- **RF-5:** THE SYSTEM SHALL accept `.mov`, `.mp4`, `.m4v`, `.avi` and `.mkv` containers and
  record the detected container and codec.

### Frame features

- **RF-6:** FOR EACH sampled frame, THE SYSTEM SHALL compute variance of Laplacian,
  Tenengrad, edge density, luminance percentiles, black/white clipping, standard deviation,
  histogram entropy, local contrast, saturation statistics, Hasler-Süsstrunk colorfulness,
  channel cast, and a normalized luminance histogram.
- **RF-7:** FOR EACH sampled frame, THE SYSTEM SHALL compute a small luminance thumbnail used
  only for translation estimation, and SHALL record its size.

### Shot detection

- **RF-8:** WHEN two consecutive sampled frames are compared, THE SYSTEM SHALL compute a
  combined distance from histogram chi-square, gradient log-distance, and edge-density
  distance using the configured weights, plus a phase-correlation translation estimate.
- **RF-9:** WHEN a combined distance exceeds the robust threshold and is a local maximum,
  THE SYSTEM SHALL mark a candidate shot boundary.
- **RF-10:** IF the median absolute deviation is degenerate, THEN THE SYSTEM SHALL use a
  relative-maximum fallback and record the dispersion source in the audit JSON.
- **RF-10a:** A candidate boundary SHALL be kept only when its combined distance is at
  least `peak_prominence_ratio` times the median distance of its neighbourhood
  (`peak_prominence_radius` samples, `peak_prominence_guard` excluded around the peak);
  otherwise it SHALL be recorded as rejected with its value, local reference and reason.
  A local maximum inside sustained motion is not a content change.
- **RF-11:** WHEN shot boundaries are produced, THE SYSTEM SHALL enforce the minimum shot
  duration (merge, default 1.0 s) and the maximum shot duration (split).
- **RF-12:** WHEN adjacent shots are at least `merge_similarity` similar by Bhattacharyya
  distance over their averaged histograms, THE SYSTEM SHALL merge them and record how many
  shots existed before and after merging.
- **RF-13:** THE SYSTEM SHALL render one five-frame montage strip per detected boundary and
  record the path, timestamps and frames present for each.

### Aggregation and scoring

- **RF-14:** FOR EACH shot, THE SYSTEM SHALL aggregate spatial metrics with the median, and
  clipping, edge density and instability with the mean, and SHALL record the strategy used.
- **RF-15:** FOR EACH shot, THE SYSTEM SHALL compute translation consistency, jitter, pan
  speed and change-per-second from the accumulated translation vectors.
- **RF-16:** IF phase-correlation confidence is too low for a shot, THEN THE SYSTEM SHALL
  fall back to instability for the stability dimension and record
  `stability_source = instability_fallback`.
- **RF-17:** FOR EACH shot, THE SYSTEM SHALL compute eight dimension scores: sharpness,
  exposure, contrast, stability, motion, color, texture, duration.
- **RF-18:** THE SYSTEM SHALL declare, for every normalized component, the raw variable, its
  unit, the transform, the mode, the bounds, the bound source, and its calibration label.
- **RF-19:** THE SYSTEM SHALL normalize ranking components with the per-video p5-p95 bounds
  by default, and SHALL fall back to the configured absolute ranges when there are too few
  shots or the spread is degenerate, recording the reason as a warning.
- **RF-20:** THE SYSTEM SHALL always normalize target bands and gate thresholds with absolute
  ranges, never percentiles.
- **RF-21:** WHEN the user supplies weights, THE SYSTEM SHALL renormalize them over the
  positive weights and REPORT the effective weights; a dimension with zero weight SHALL NOT
  contribute.

### Gates, selection and diversity

- **RF-22:** IF a shot fails any hard gate, THEN THE SYSTEM SHALL place it in
  `rejected_shots` with the gate name, value, threshold, and interpretation.
- **RF-23:** IF a shot passes every gate but scores below the quality floor, THEN THE SYSTEM
  SHALL mark it `rejected_floor`, distinct from a gate rejection.
- **RF-24:** WHEN shots pass all gates and the floor, THE SYSTEM SHALL rank them by total
  score descending and start time ascending.
- **RF-25:** THE SYSTEM SHALL select the Top-N with a maximal-marginal-relevance rule over
  Bhattacharyya histogram similarity, reporting the shots displaced by diversity.
- **RF-26:** THE SYSTEM SHALL export only the configured `top_n` shots in `selected_shots`;
  shots that pass but are not selected SHALL be reported separately, never as rejected.

### Artifacts and client

- **RF-27:** THE SYSTEM SHALL write, under the run directory, `audit.json`, `ui.json`,
  `samples.csv.gz`, `shots.csv`, representative frame PNGs, and boundary montages.
- **RF-28:** THE SYSTEM SHALL make `samples.csv.gz` byte-identical for identical input,
  config and library versions (gzip `mtime=0`, empty filename).
- **RF-29:** `ui.json` SHALL be self-contained: config, catalogs, shot records, frame
  distances, boundary positions and boundary montages. A client SHALL NOT need the video.
- **RF-30:** THE SYSTEM SHALL provide a client that re-ranks from `ui.json` alone, and that
  rebuilds shots from `samples.csv.gz` plus the recorded distances when the user changes the
  merge similarity.
- **RF-31:** THE SYSTEM SHALL let the user export the current config as JSON and SHALL accept
  that file back through `--config`.

### Annotation and evaluation

- **RF-32:** THE SYSTEM SHALL accept a versioned `labels.json` with shot verdicts (level A),
  boundary verdicts, and pairwise comparisons (level B), and SHALL reject invalid values.
- **RF-33:** WHEN labels are supplied, THE SYSTEM SHALL report precision@N, recall of
  positives, NDCG@N, gate false rejects, per-dimension separation, and pairwise accuracy.
- **RF-34:** THE SYSTEM SHALL NOT modify weights from labels automatically.

### Output contract and errors

- **RF-35:** THE SYSTEM SHALL include schema version, generation timestamp, interpretation
  label, pipeline and library versions, config hash, full config, detected boundaries,
  selected shots, rejected shots, passing-but-unselected shots, and a summary.
- **RF-36:** IF the input is invalid or cannot be decoded, THEN THE SYSTEM SHALL write a
  structured error JSON and exit with a non-zero status.
- **RF-37:** THE SYSTEM SHALL record a VFR warning when `r_frame_rate != avg_frame_rate`
  and a rotation note when rotation metadata is present.
- **RF-38:** THE SYSTEM SHALL record the analysis resolution used and whether resizing was
  applied.
- **RF-39:** THE SYSTEM SHALL produce identical results for identical input, config, and
  library versions, except for the generation timestamp.
- **RF-40:** EVERY fallback or degradation SHALL appear as a warning in the output.

## 5. Non-functional requirements

- **NFR-1:** Runs locally with no network access.
- **NFR-2:** The core pipeline is deterministic and `src/video_dsp` depends only on numpy and
  OpenCV; pandas/Streamlit are confined to `app/`.
- **NFR-3:** A 5.7-minute 4K sample completes in a few minutes at the default 1280-pixel
  analysis resolution.
- **NFR-4:** Code is typed where practical; pure functions are covered by unit tests.
- **NFR-5:** Errors are structured and never silently swallowed.
- **NFR-6:** No hidden enhancement. Analysis resizing is a documented, recorded
  measurement-resolution choice and can be disabled.
- **NFR-7:** The client never re-encodes, trims, or modifies the input file.

## 6. Edge cases

Missing video stream; corrupt file; unsupported codec; zero duration; unknown FPS; very
short or very long shots; black frames; white frames; high noise; strong compression
artifacts; rapid camera movement; fade to black; dissolve transitions; duplicate frames;
over-segmentation from a single continuous take; VFR files; rotation metadata; fewer than
`min_shots` shots (normalization fallback); a single shot (all percentile bounds fall back).

## 7. Out of scope

Semantic understanding; face detection; object detection; narrative relevance; blockiness/
banding/mosquito noise; HDR linearization; PyAV decoding; corpus calibration; automatic
weight fitting; clip export; batch processing (architecture ready, UI single-run).

## 8. Resolved clarifications

1. **OpenCV decoding:** allowed, with mandatory warnings; on hard failure the CLI aborts
   with a structured error and an ffmpeg conversion suggestion.
2. **Representative frames:** mandatory; exported as full-resolution PNGs.
3. **Per-frame CSV:** now emitted (`samples.csv.gz`), byte-deterministic.
4. **Thresholds:** accepted as illustrative and labeled `initial_uncalibrated`.
5. **VFR:** detected and warned only; no PTS remapping.
6. **Normalization:** per-video percentiles for ranking, absolute ranges for gates and target
   bands; `balanced_v1` keeps absolute ranges to reproduce v0.1.0.
7. **Annotation scope:** level A (verdict + closed-set reason + duplicate group) and level B
   (pairwise), nothing else.
8. **Clips:** out of the MVP; a five-frame boundary montage replaces them.

## 9. Completion criteria

- CLI runs successfully on the real 4K sample.
- Audit JSON contains source metadata, file hash, config, normalization table with ranges,
  boundaries with evidence, selected, rejected and passing-but-unselected shots, summary,
  and warnings.
- Each shot has raw metrics, normalized component scores with bounds, eight dimension scores,
  gates with failing value and threshold, and a representative frame.
- The client loads a run, re-ranks on weight changes, rebuilds shots on merge changes, and
  exports a config that reproduces the CLI ranking.
- Unit tests pass; linter passes.
- No core module uses hidden AI inference.
- Flowchart, module map, validation report, and `MEMORY.md` are current.

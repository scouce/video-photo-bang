# Tasks 001 — MOV Shot Technical MVP

Work top to bottom. Each task lists its requirement coverage and a concrete "Done when".
All MVP tasks are complete; future work is tracked in `handoff/next_iterations.md`.

- [x] **T1 — Project skeleton and tooling**
  - Create `pyproject.toml`, `AGENTS.md`, `MEMORY.md`, `docs/constitution.md`, venv, and
    editable install.
  - RF: all (foundation), NFR-4.
  - Done when: `pytest -q` and `ruff check .` run in the venv.

- [x] **T2 — Configuration**
  - Defaults for `analysis_fps`, `top_n`, detection weights, ranges, gates, score weights,
    `analysis_resize`, schema version, and a stable config hash.
  - RF-11, RF-12, RF-16.
  - Done when: `config_hash(load_config())` is stable across calls.

- [x] **T3 — Ingest and validation**
  - SHA-256, ffprobe metadata parsing, VFR and rotation notes, resolution/FPS/stream checks.
  - RF-2, RF-3, RF-17, RF-18.
  - Done when: `test_ingest.py` passes and invalid inputs produce structured errors.

- [x] **T4 — Frame sampling**
  - Sequential decode, keep every `round(fps / analysis_fps)`-th frame, exact frame index
    and timestamp, representative-frame re-read.
  - RF-4, RF-15.
  - Done when: sampling a fixed-rate video yields the expected sample count.

- [x] **T5 — Per-frame DSP features**
  - Luminance plane, documented analysis resize, variance of Laplacian, Tenengrad, edge
    density, luminance stats, normalized histogram.
  - RF-5, RF-19.
  - Done when: `test_features.py` passes and flat vs edge images rank correctly.

- [x] **T6 — Frame distances**
  - Histogram chi-square, gradient log-distance, edge-density distance, weighted combination.
  - RF-6.
  - Done when: identical frames give zero distance and distinct frames give positive distance.

- [x] **T7 — Robust boundary threshold**
  - `median + 3 * 1.4826 * MAD`, relative-max fallback when MAD is degenerate, recorded
    dispersion source, local maxima, plateau handling, minimum gap.
  - RF-7, RF-8.
  - Done when: injected peaks are detected and flat signals produce no boundaries.

- [x] **T8 — Shot construction and duration rules**
  - Split samples at boundary positions, merge short shots, split long shots.
  - RF-9.
  - Done when: `test_shot_detection.py` passes for split/merge cases.

- [x] **T9 — Shot aggregation**
  - Median for spatial metrics, mean for clipping and edge density, internal instability.
  - RF-10.
  - Done when: aggregated values are deterministic and traceable to frame metrics.

- [x] **T10 — Normalization and category scores**
  - Higher/lower-better normalization, sharpness, exposure, contrast, stability (correct
    direction: low instability = high stability).
  - RF-11.
  - Done when: category scores stay in `[0, 1]` and stability direction is regression-tested.

- [x] **T11 — Hard gates**
  - Duration, clipping, minimum sharpness, maximum instability, with gate/value/threshold/
    interpretation recorded.
  - RF-12.
  - Done when: failing shots carry at least one explicit failed gate.

- [x] **T12 — Ranking and representative frame**
  - Rank by score desc then start time asc, keep top-N, choose the sharpest sampled frame.
  - RF-13, RF-14, RF-15.
  - Done when: ranking is deterministic and top-N is respected.

- [x] **T13 — Audit JSON export**
  - Schema version, timestamp, interpretation, pipeline versions, source metadata, config
    hash, full config, boundaries, selected/rejected/unselected shots, summary.
  - RF-1, RF-16.
  - Done when: `test_export.py` key checks pass and the real file validates.

- [x] **T14 — Error JSON**
  - Structured error document, aborted flag, non-zero exit code.
  - RF-17.
  - Done when: ingestion/decode failures still write a readable JSON document.

- [x] **T15 — Full-resolution representative frames**
  - Re-read the selected frame from the source, write a full-resolution PNG, clean stale
    files from previous runs, record the path in the shot.
  - RF-15.
  - Done when: every selected shot has an existing, full-resolution image.

- [x] **T16 — CLI orchestration**
  - Argument parsing, config overrides, progress output, decode-failure guidance, analysis
    resolution reporting from the decoded frame.
  - RF-1 to RF-20.
  - Done when: the documented run command completes on the real sample.

- [x] **T17 — Tests and lint**
  - Unit suites plus an end-to-end synthetic-sample test.
  - NFR-4.
  - Done when: `pytest -q` and `ruff check .` are clean.

- [x] **T18 — Real-sample validation and handoff**
  - Run on `IMG_1564.mov`, inspect the JSON and thumbnails, write the handoff package and
    update `MEMORY.md`.
  - Acceptance criteria.
  - Done when: `handoff/validation_report.md` reflects the final run.

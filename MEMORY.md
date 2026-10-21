# MEMORY.md — Project memory

Living record of decisions, status, and open items. Updated at the end of every session.

## Current MVP status

- **Status:** MVP complete, recalibrated for v0.2.0 and validated on 4K footage. A
  non-photographer client (Simple mode) was added on top of the same config surface.
- **Target:** deterministic classical-DSP shot selector for `.mov`, `.mp4`, `.m4v`, `.avi`, `.mkv`.
- **Pipeline version:** 0.2.0 (`0.2.0` schema).
- **Quality gates:** 168 tests passing; `ruff check .` clean.

## Environment

- Python 3.14.7 via the `py` launcher (no `python`/`python3` alias on PATH).
- ffprobe 8.1 (FFmpeg full build) available on PATH.
- Virtual environment: `.venv` (numpy 2.5.4, opencv-python-headless 5.0.0.93, pytest 9.1.1, ruff 0.17.1).

## Chosen thresholds (initial, uncalibrated)

- `analysis_fps = 5.0`
- `top_n = 10`
- `min_shot_duration_s = 1.0`, `max_shot_duration_s = 15.0`
- Shot detection weights: histogram 0.65, gradient 0.20, edge 0.15
- `mad_multiplier = 3.0` (with 1.4826 consistency factor)
- `min_gap_seconds = 0.4`
- Peak prominence: ratio 2.0, radius 5 samples (±1 s), guard 1 sample. A candidate
  boundary must beat the median distance of its neighbourhood by 2x; `--peak-prominence 0`
  disables the filter (the pre-0.2.0 behaviour).
- Analysis resize: enabled, longest edge 1280 px, area interpolation (recorded, disable-able
  with `--analysis-max-dimension 0`).
- Ranking normalization: per-video p5-p95 with explicit fallbacks (`too_few_shots`,
  `degenerate_spread`); gates and target bands stay absolute.
- Normalization ranges (gates and bands) tuned on one 4K iPhone sample at 1280-px analysis:
  VoL [20, 400], Tenengrad [500, 8000], luminance std [0.05, 0.35], instability [0, 0.35],
  jitter [0, 3] px, entropy [0.30, 0.95], local contrast [0.010, 0.100].
- Hard gates: black/white clip ≤ 0.10, min sharpness score 0.15, max instability 0.40,
  max jitter 4.0 px.
## 2026-10-21 — 004 execution

- Downloads: `export_shot_photos` writes full-res JPEGs (q92, ~0.8 MB each) for selected +
  rejected shots into `media/photos/`, records `photo_path/photo_bytes/photo_width/photo_height`,
  CLI summary `shot_photos_written`/`shot_photos_dir`. Client serves the JPEG first and falls
  back to the 480 px preview; two bulk ZIPs (light < 1 MB, full ~15 MB) plus a folder-path
  fallback when a large download fails in a restricted browser. `load_ui` and `zip_bytes` now
  key their cache on the file mtime, so a regenerated run is not served stale.
- Upload: `.streamlit/config.toml` (maxUploadSize 4 GB); `app/upload.py` streams the upload in
  8 MB chunks while hashing, dedupes by SHA-256, derives a deterministic run directory and
  spawns `python -m video_dsp.cli` with live progress and cancel. Empty state shows the
  uploader instead of an error.
- Presets: optional `hard_gates` merged in `_apply_preset` and recorded as
  `preset_hard_gates`; portrait/action/landscape/low_light/shorts now differ in weights,
  bands, gates and duration intent. Measured Jaccard on IMG_1564.mov: all non-legacy pairs
  <= 0.67 (was 0.82-1.00). `balanced_v1` stays legacy.
- Tests: 104 passing; `pytest -q` and `ruff check .` clean.
- Next: specs/003 (calibration) when the user provides labeled shots.
- Diversity: MMR with weight 0.25 over Bhattacharyya histogram similarity.
- All thresholds carry `calibration = "initial_uncalibrated"`.

## Known codec / container issues

- OpenCV `VideoCapture` may not decode every professional `.mov` codec. On failure the CLI
  aborts with a structured error and suggests converting with ffmpeg.
- VFR is detected (`r_frame_rate != avg_frame_rate`) and warned, but not remapped.
- Rotation metadata (e.g. iPhone 90°) is recorded and warned. In practice OpenCV applied the
  rotation on the validation sample: ffprobe reports 3840×2160 but frames decode as 2160×3840.
  The audit JSON records both stored and decoded sizes.

## Pending calibration

- Normalization ranges for variance-of-Laplacian, Tenengrad, luminance std, instability.
- Gate thresholds against a representative corpus.
- Human pairwise validation (NDCG / Spearman / F1) — deferred.

## Decisions made by D.A.

- Full MVP implementation in the first session.
- Representative frame images are exported (full resolution).
- Per-frame CSV is deferred (shot JSON only).
- OpenCV decoding allowed with mandatory warnings; on hard failure, abort and plan a
  mov → other-format conversion.
- Hard gates accepted as illustrative and labeled `initial_uncalibrated`.
- VFR: detect + warn only, no PTS remapping.

## Validation results (2026-10-21)

- Synthetic sample: 3 shots, exact cuts at 2.9 s / 5.9 s, 1 selected, 2 rejected.
- Real sample `IMG_1564.mov` (343.49 s, 4K portrait), run `out/runs/img1564_calib2`:
  1718 samples, 98 boundary candidates → 76 kept (22 dropped by peak prominence), 66 shots,
  57 passed gates, 10 selected, 9 rejected (5 `min_sharpness_score`, 4 `max_jitter_px`),
  47 passing-but-unselected. 10 full-resolution PNGs and 76 boundary montages written.
- Top score 0.941; shortest selected shot 1.2 s; every Top-10 shot is between 1.8 and 5.6 s.
- Analysis resolution 720×1280; decoded size 2160×3840.
- See `handoff/validation_report.md` for the full evidence.

## Simple UI iteration (specs/002-ui-simple)

- Two modes, default **Simple**: gallery with preview + per-photo PNG download, ZIP of the
  recommended shots, config JSON download, and a modal "ficha" with a derived, jargon-free
  explanation. **Technical** keeps the six tabs unchanged.
- Encapsulation rule: every friendly control writes the same explicit config fields; the
  client still reproduces the CLI ranking from the exported JSON.
- Client modules: `app/ui.py` (shell), `app/simple.py` (simple mode), `app/copy_es.py`
  (plain copy). Each recommended/discarded shot now gets a 480 px JPEG in
  `media/thumbs/` (`export_shot_thumbnails`), so the gallery never decodes 4K PNGs.
- Decisions: F2 shipped before F1; thumbnails cover recommended + discarded only;
  downloads are individual + ZIP + config.
- Tests: `tests/test_ui_simple.py` covers default mode, card count, ZIP payload, discard
  filter, jargon leakage, preset/reset writes and the "why" sentence.

## Delivered artifacts

- Spec, clarification, plan, and tasks under `specs/001-mov-shot-mvp/` and `docs/`.
- Workflow agents and SDD commands under `.opencode/agents/` and `.opencode/commands/`.
- Handoff package under `handoff/`.
- Root `README.md`, `.gitignore`.

## Next steps

Prioritized backlog lives in `handoff/next_iterations.md`. Immediate items: calibration corpus,
per-frame CSV, artifact metrics, VFR normalization, and PyAV for professional codecs.

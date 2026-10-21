# MEMORY.md — Project memory

Living record of decisions, status, and open items. Updated at the end of every session.

## Current MVP status

- **Status:** MVP complete and validated (docs and handoff delivered).
- **Target:** deterministic classical-DSP shot selector for `.mov` files.
- **Pipeline version:** 0.1.0 (`0.1.0-mvp` schema).
- **Quality gates:** 38 tests passing; `ruff check .` clean.

## Environment

- Python 3.14.7 via the `py` launcher (no `python`/`python3` alias on PATH).
- ffprobe 8.1 (FFmpeg full build) available on PATH.
- Virtual environment: `.venv` (numpy 2.5.4, opencv-python-headless 5.0.0.93, pytest 9.1.1, ruff 0.17.1).

## Chosen thresholds (initial, uncalibrated)

- `analysis_fps = 5.0`
- `top_n = 10`
- `min_shot_duration_s = 0.5`, `max_shot_duration_s = 15.0`
- Shot detection weights: histogram 0.65, gradient 0.20, edge 0.15
- `mad_multiplier = 3.0` (with 1.4826 consistency factor)
- `min_gap_seconds = 0.4`
- `analysis_resize`: enabled, longest edge 1280 px, area interpolation (recorded, disable-able
  with `--analysis-max-dimension 0`).
- Normalization ranges tuned on one 4K iPhone sample at 1280-px analysis:
  VoL [20, 400], Tenengrad [500, 8000], luminance std [0.05, 0.35], instability [0, 0.35]
- Hard gates: black/white clip ≤ 0.10, min sharpness score 0.15, max instability 0.40
- Score weights: sharpness 0.40, exposure 0.25, contrast 0.20, stability 0.15
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
- Real sample `IMG_1564.mov` (343.49 s, 4K portrait): 1718 samples, 98 boundary positions,
  93 shots, 69 passed gates, 10 selected, 24 rejected (all `min_sharpness_score`), 59 passing
  but unselected. 10 full-resolution 2160×3840 PNGs written.
- Top score 0.7985 (`shot_0016`, 49.2–51.4 s). Selected range 6.6–84.6 s.
- Analysis resolution 720×1280; decoded size 2160×3840.
- See `handoff/validation_report.md` for the full evidence.

## Delivered artifacts

- Spec, clarification, plan, and tasks under `specs/001-mov-shot-mvp/` and `docs/`.
- Workflow agents and SDD commands under `.opencode/agents/` and `.opencode/commands/`.
- Handoff package under `handoff/`.
- Root `README.md`, `.gitignore`.

## Next steps

Prioritized backlog lives in `handoff/next_iterations.md`. Immediate items: calibration corpus,
per-frame CSV, artifact metrics, VFR normalization, and PyAV for professional codecs.

# MOV Shot Technical MVP

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://video-photo-bang-pdzq4ahkdbe3eqjwm6dars.streamlit.app/)

Deterministic classical-DSP shot selection for local `.mov`, `.mp4`, `.m4v` and `.avi` files.
The CLI samples frames, detects shot boundaries, measures technical metrics, scores eight
dimensions, applies hard gates and a quality floor, and selects a Top-N that penalizes
near-duplicates. Every number is traceable to a raw measurement and a declared range.

A separate Streamlit client reads the run artifacts and re-ranks live, so changing a
preference weight never re-decodes the video and never diverges from the CLI: both call
`video_dsp.selection_service`.

This is a **technical draft selector**, not an editorial or semantic judgment.

## Quick start

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

.\.venv\Scripts\python.exe -m video_dsp.cli "C:\path\to\video.mov"
```

Defaults write everything under `out/runs/<video-hash>_<config-hash>/`.

Fast smoke test:

```powershell
.\.venv\Scripts\python.exe -m video_dsp.cli samples\synthetic_test.mov --run-dir out\runs\synthetic
```

## First run

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ui]"

.\.venv\Scripts\python.exe -m streamlit run app/ui.py
```

The app starts **empty**: no videos or photos are preloaded. On the start screen
an uploader appears (or a local path field). Upload a `.mov`/`.mp4`/… or paste the
path of a file already on your machine; the analysis runs in the background and the
run appears in the selector when it finishes. The first run on a 4K clip takes a few
minutes; results are stored in `out/runs/` (gitignored, local only).

Para uso sin interfaz:

```powershell
.\.venv\Scripts\python.exe -m video_dsp.cli "C:\path\to\video.mov"
```

## Calibration UI

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
.\.venv\Scripts\python.exe -m streamlit run app/ui.py
```

Two modes, one client, one config:

**Simple** (default) answers three questions ("type of photo", "how many photos", "avoid
repetidos?") and shows a gallery of the recommended shots with a preview and a download
button per photo, two bulk ZIPs (a light 480 px one and the full-resolution JPEGs) and the
config JSON. It also accepts a new video: drop a `.mov`/`.mp4`/… into the uploader or paste
a local path, and the run is created on the spot. "View details" opens a
plain-language explanation derived from the ranking; the raw evidence stays one click away.

**Technical** keeps the six tabs:

| Tab | What it answers |
| --- | --- |
| Calibration | Does my preference change the Top-N? What is driving the score? |
| Ranking and gates | Why was this shot rejected, and with which value against which threshold? |
| Boundaries | Is each detected cut real? Is the video over-segmented? |
| Distributions | What ranges are being used, and where does this shot sit in them? |
| Summary | What did the run produce, and how does it score against my labels? |
| Audit | Exact config, pipeline versions, field catalog, normalization table. |

Both modes write the same config, so the sidebar export reproduces the exact ranking from
the command line with `--config`.

## Outputs

Per run directory:

- `audit.json` — schema version, timestamp, pipeline versions, source metadata and SHA-256,
  config hash, boundaries with evidence, selected/rejected/unselected shots, raw metrics,
  normalized component scores with their ranges, gates with failing value and threshold,
  warnings and evaluation.
- `ui.json` — self-contained document for the client: config, catalogs, shot records,
  frame distances, boundary positions and montages. No video access needed.
- `samples.csv.gz` — per-sample metrics and histogram bins, byte-deterministic
  (`mtime=0`, empty filename).
- `shots.csv` — one row per shot: status, score, 8 dimensions, raw metrics.
- `media/representatives/` — one full-resolution PNG per selected shot.
- `media/boundaries/` — five-frame strip per detected boundary.
- `labels.json` — only if you annotate (level A verdicts, level B pairs, boundary verdicts).
- `evaluation.json` — only if labels exist.

## Options

`--preset`, `--analysis-fps`, `--top-n`, `--min-shot-duration`, `--max-shot-duration`,
`--analysis-max-dimension` (0 = native), `--peak-prominence` (0 disables the filter),
`--merge-similarity`, `--diversity-weight`, `--quality-floor`, `--config`, `--labels`,
`--run-dir`, `--out`, `--thumbnails`, `--no-artifacts`, `--no-montage`.

Presets: `balanced_v2` (default), `balanced_v1` (legacy 0.1.0 absolute formula),
`portrait`, `landscape`, `action`, `low_light`, `product`.

The default analysis resize caps the longest edge at 1280 pixels for speed. It is recorded
in the JSON, and normalization ranges are tied to it.

## Scoring model

Eight dimensions: sharpness, exposure, contrast, stability, motion, color, texture,
duration. Each dimension blends declarative components defined in `metrics_spec.py`.

- **Ranking bounds** come from the p5-p95 of the shots of this video, after a declared
  monotonic transform. When there are too few shots or the spread is degenerate, the
  service falls back to the absolute config ranges and records why.
- **Gates and target bands are always absolute**: they express a hard limit or a
  preference, so a percentilee would be meaningless.
- `balanced_v1` keeps the absolute ranges so the v0.1.0 ranking stays reproducible.
- Near-duplicates are pushed out of the Top-N by MMR over Bhattacharyya histogram
  similarity; displaced shots are reported by name.

## Quality gates

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```

## Docs

- `AGENTS.md` — harness contract.
- `docs/constitution.md`, `docs/clarification.md`.
- `specs/001-mov-shot-mvp/` — spec, plan, tasks.
- `handoff/` — handoff README, flowchart, module map, validation report, next iterations.
- `MEMORY.md` — current status and decisions.

## Constraints

Classical DSP only in `src/video_dsp`; no hidden semantic AI; input video never modified; no
network calls; every fallback recorded as a warning; thresholds labeled
`initial_uncalibrated`. The UI layer may use pandas/Streamlit, the core may not.

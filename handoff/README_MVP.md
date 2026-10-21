# MOV Shot Technical MVP — Handoff

## What this is

A deterministic, classical-DSP Python CLI that reads a local `.mov` file, detects shot
boundaries, computes technical frame and shot metrics, applies hard gates, ranks the
technically strongest shots, and writes:

- an auditable JSON report (`out/shot_selection.json`), and
- one full-resolution representative PNG per selected shot (`out/thumbnails/`).

It is a **technical draft selector**. It does not judge story, emotion, faces, or editorial
value.

## Quick start

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# fast synthetic smoke test
.\.venv\Scripts\python.exe -m video_dsp.cli samples\synthetic_test.mov `
  --out out\synthetic_selection.json --thumbnails out\synthetic_thumbs

# real sample
.\.venv\Scripts\python.exe -m video_dsp.cli "C:\path\to\video.mov" `
  --out out\shot_selection.json --thumbnails out\thumbnails
```

The console script `video-dsp` is equivalent after the editable install:

```powershell
.\.venv\Scripts\video-dsp.exe "C:\path\to\video.mov"
```

## Outputs

- `shot_selection.json`: schema version, generation timestamp, pipeline/library versions,
  source metadata and SHA-256, config and config hash, detected boundaries, frame distances,
  selected shots, rejected shots, passing-but-unselected shots, and a summary.
- `thumbnails/shot_XXXX_rankNN_tSSSS.png`: full-resolution representative frame per selected
  shot (2160×3840 for the validation sample).

Every normalized score is traceable to saved raw metrics. Every gate failure records the
gate name, the value, the threshold, and an interpretation.

## Useful options

| Option | Meaning |
|---|---|
| `--analysis-fps` | Frames sampled per second (default 5). |
| `--top-n` | Number of selected shots (default 10). |
| `--min-shot-duration` / `--max-shot-duration` | Shot duration gates. |
| `--analysis-max-dimension` | Longest analysis edge in pixels (default 1280); `0` disables resizing. |
| `--config` | JSON file with config overrides. |
| `--thumbnails` | Directory for representative frames. |

The analysis resize is a documented measurement-resolution choice, not enhancement. It is
recorded in the JSON and can be disabled, but the normalization ranges are tied to the
default 1280-pixel analysis resolution.

## Quality gates

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```

## Documentation map

| Path | Contents |
|---|---|
| `AGENTS.md` | Harness contract and non-negotiable rules. |
| `docs/constitution.md` | Engineering constitution. |
| `docs/clarification.md` | Resolved ambiguities. |
| `specs/001-mov-shot-mvp/spec.md` | EARS requirements. |
| `specs/001-mov-shot-mvp/plan.md` | Architecture, algorithms, decisions, RF coverage. |
| `specs/001-mov-shot-mvp/tasks.md` | Ordered implementation tasks. |
| `handoff/flowchart.md` | Pipeline flowchart. |
| `handoff/module_map.md` | Module and function map. |
| `handoff/validation_report.md` | Test, lint, and real-sample results. |
| `handoff/next_iterations.md` | Prioritized backlog. |
| `MEMORY.md` | Current status and decisions. |

## Hard constraints

- Classical DSP only in `src/video_dsp`; no hidden semantic or learned models.
- The input video is never modified.
- No network calls.
- Every fallback or degradation is recorded as a warning in the output JSON.
- Thresholds are illustrative and labeled `initial_uncalibrated`.

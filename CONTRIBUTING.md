# Contributing

## Setup

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ui]"
```

## Quality gates

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

Both must pass before a change is considered done.

## Rules

- The core in `src/video_dsp` is classical DSP only: no face scoring, no narrative
  scoring, no learned quality models.
- The core is deterministic: same input + same config + same library versions must
  produce the same selection except for the generation timestamp.
- Every normalized score must be traceable to raw metrics; raw and normalized metrics,
  ranges and gates are saved in the output.
- The tool never modifies the input file and never makes network calls unless explicitly
  approved.
- `balanced_v1` reproduces the v0.1.0 formula exactly and must not change.
- Presets are data, never code, and stay `initial_uncalibrated` until a corpus supports
  a change.

## Tests

Pure DSP functions must have unit tests. UI changes are exercised with Streamlit's
`AppTest`. The synthetic sample `samples/synthetic_test.mov` is committed so the suite
runs without private data.

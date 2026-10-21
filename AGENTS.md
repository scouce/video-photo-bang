# AGENTS.md — MOV Shot Technical MVP

This file is the harness contract for any AI assistant working in this repository.
It is enforced before code, during code, and at validation time.

## Project

A small, deterministic Python CLI that classifies and ranks shots from a local `.mov`
file using **classical DSP only**. It produces an auditable JSON report and
representative frame images for human review.

## Non-negotiable rules

1. **Python 3.14+** is the development target (code must stay compatible with 3.11+).
2. **No hidden semantic AI** in the core DSP pipeline. No face scoring, no narrative
   scoring, no learned quality models inside `src/video_dsp`.
3. **Deterministic core**: same input + same config + same library versions must produce
   the same selection except for the generation timestamp.
4. **Raw metrics are saved.** Every normalized score must be traceable to raw metrics.
5. **Normalized metrics are saved** together with the ranges used.
6. **Gates are saved**, including the exact threshold and value that failed.
7. **No destructive video editing** in the MVP. The tool never modifies the input file.
8. **No network calls** unless explicitly approved.
9. **Tests before feature completion.** Pure DSP functions must be covered by unit tests.
10. **No silent fallbacks.** Every fallback or degradation must be recorded as a warning in
    the output JSON.

## Required workflow

- Work task by task from `specs/001-mov-shot-mvp/tasks.md`.
- Read `docs/constitution.md`, the spec, and the plan before implementing.
- Keep functions small, typed where practical, and pure where possible.
- Run `pytest -q` and `ruff check .` before declaring a task done.
- Do not start the next task until the current one is reviewed.

## Commands

```bash
# environment
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# quality gates
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .

# run
.\.venv\Scripts\python.exe -m video_dsp.cli samples/synthetic_test.mov --out out/shot_selection.json
```

## Output contract

The CLI always writes a JSON document containing: schema version, generation timestamp,
pipeline versions, config hash, source metadata, file hash, detected boundaries, selected
shots, rejected shots, and a global summary. See `specs/001-mov-shot-mvp/spec.md`.

---
description: Run tests, lint, and an end-to-end sample validation
agent: coordinator
---

Validate the current implementation: $ARGUMENTS

Run and report:

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```

Then run the pipeline on a sample and verify the JSON contract:

```bash
.\.venv\Scripts\python.exe -m video_dsp.cli samples\synthetic_test.mov --out out\validation.json --thumbnails out\validation_thumbs
```

Check that the JSON contains schema version, generation timestamp, interpretation, pipeline
versions, source metadata, file hash, config hash, detected boundaries, selected shots,
rejected shots, and a summary. Confirm every selected shot has raw metrics, normalized
metrics, category scores, gates, a representative frame, and an existing image; confirm every
rejected shot lists its failed gates. Update `handoff/validation_report.md` with the results.
Do not claim success for a check you did not run.

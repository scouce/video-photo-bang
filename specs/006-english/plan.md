# Plan 006 — English localisation

Translate the whole product to English: UI copy, technical copy, DSP warnings, output-field
labels, presets, documentation and tests. The DSP core, the output schema shape and the
determinism guarantees do not change; only the human-facing strings and field names do.

## 1. Scope

In scope:
- `app/copy_es.py` → `app/copy.py` (English strings).
- `app/ui.py`, `app/simple.py`, `app/upload.py` (all user-facing text).
- `src/video_dsp/metrics_spec.py` (`label_es`/`description_es` → `label`/`description`,
  `unit_es` → `unit`).
- `src/video_dsp/presets.py` (`label_es`/`description_es`).
- `src/video_dsp/cli.py`, `ingest.py`, `export.py`, `normalization.py` (warnings,
  progress lines, error messages).
- `src/video_dsp/config.py` (notes, calibration label stays the code token
  `initial_uncalibrated`).
- Tests that assert on Spanish strings.
- `README.md`, `AGENTS.md`, `MEMORY.md`, `CONTRIBUTING.md`, `docs/index.md`, specs.

Out of scope:
- Renaming the `initial_uncalibrated` code token (it is an audit value, not copy).
- i18n framework / bilingual toggle (single language: English).

## 2. Field-name migration

`label_es` → `label`, `description_es` → `description`, `unit_es` → `unit`. The
`_es` suffix implied a language that no longer matches; neutral names keep the output
contract readable. `build_ui_document` and the client read the new keys. Old runs
generated before this change are not supported (regenerate).

## 3. Order of execution

| Step | Work | Gate |
|---|---|---|
| L1 | `metrics_spec.py` + `presets.py` + `config.py` field renames | unit tests |
| L2 | `cli.py`/`ingest.py`/`export.py`/`normalization.py` messages | integration tests |
| L3 | `app/copy.py` (new) + delete `copy_es.py`; wire imports | `ruff` |
| L4 | `app/ui.py`, `app/simple.py`, `app/upload.py` text | AppTest suite |
| L5 | Tests updated to English strings | `pytest` |
| L6 | Docs and README | manual review |
| L7 | Regenerate the 4K run, verify the UI | browser check |

## 4. Risks

- Large mechanical change: every UI test asserts on labels; they must be updated in the
  same commit.
- The `initial_uncalibrated` token stays (audit contract); only the surrounding copy
  changes.
- No semantic change: weights, bands, gates, scoring untouched.

## 5. Acceptance

- `ruff check .` and `pytest -q` green.
- No Spanish user-facing strings remain in `app/` or `src/video_dsp/`.
- README and docs in English.
- Deployed app shows English.

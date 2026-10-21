# Plan 005 — Release hygiene and empty-state default

Goal: make the repository publishable. The app must start with **no video and no photos**
loaded, the tree must contain only what the tests generate, and the documentation must
describe the first-run flow. No behavioural change to the DSP core.

## 1. What is already true

- `out/` is gitignored and nothing under it is tracked (only `samples/synthetic_test.mov`).
- The client already shows an uploader instead of an error when there are no runs
  (implemented in 004, verified by `tests/tmp_empty_state.py` during development).
- `find_runs()` sorts by mtime and the empty state is the default after a fresh clone.

## 2. What still needs to change

### 2.1 Remove the real sample video

`samples/optional_test.mov` is a real clip used only as a manual example in `AGENTS.md`.
It is not referenced by any test. Keep `samples/synthetic_test.mov` (the tests depend on
it) and point the example command at it.

### 2.2 Defensive `.gitignore`

Add explicit rules so a contributor can never accidentally commit a run, a photo, an
upload or a downloaded export:

```
out/
*.mov
*.mp4
*.m4v
*.avi
*.mkv
*.jpg
*.jpeg
*.png
*.zip
.streamlit/secrets.toml
```

`samples/synthetic_test.mov` is the one exception and is force-added (or kept with
`!samples/synthetic_test.mov`).

### 2.3 Clean the local working tree

Delete `out/` (runs, uploads, exports, photos) so the developer's machine matches a
fresh clone. This is local only and never touches tracked files.

### 2.4 First-run documentation

`README.md` gets a "Primera ejecución" section: clone → venv → `streamlit run app/ui.py`
→ the app opens empty with an uploader → drop a clip or paste a path → the run appears
in the selector. The CLI one-liner stays for headless use. Mention that the first run
takes a few minutes on 4K footage and that `out/` is generated locally.

### 2.5 Repository metadata

- `LICENSE` (MIT) and a short `CONTRIBUTING.md` (how to run tests, ruff, the
  determinism rule, no semantic scoring in `src/video_dsp`).
- `.github/workflows/ci.yml`: Python 3.11 and 3.14, `pip install -e ".[dev,ui]"`,
  `ruff check .`, `pytest -q`. The synthetic sample is committed, so the suite runs
  in CI without any private data.
- Optional: `.github/workflows/pages.yml` that publishes `docs/` (or a generated
  static copy of the README) to GitHub Pages. The Streamlit app itself is not hosted
  there; it runs locally or on Streamlit Community Cloud.

### 2.6 Verify the empty state in CI

Add a test that sets `VIDEO_DSP_RUNS_DIR` to an empty directory and asserts the app
renders the uploader with no exception and no "No hay runs" error. (A variant of the
smoke test used during 004.)

### 2.7 Final audit

- `git ls-files` contains no `.mov`/`.mp4`/`.jpg`/`.png`/`.zip` except the synthetic
  sample.
- `git status` clean after a fresh run of `pytest -q` (tests write only to `tmp_path`).
- `ruff check .` clean.

## 3. Out of scope

- Hosting the Streamlit app on GitHub Pages (it needs a Python server; use Streamlit
  Community Cloud instead, documented in the README).
- Removing the synthetic sample (the tests need it).
- Any change to the DSP core or to the scoring.

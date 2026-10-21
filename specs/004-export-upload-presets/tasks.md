# Tasks 004 — Downloads, upload, presets

Work in order; `pytest -q` and `ruff check .` before marking a task done. The core stays
classical and deterministic; the input video is never modified.

## D — Downloads

- [x] T-D1.1 `config.py`: `artifacts.photos = {enabled, quality: 92}`.
- [x] T-D1.2 `export.py`: `export_shot_photos(input_path, shots, dir, quality)` writes
      `media/photos/<shot_id>.jpg` and records `photo_path`, `photo_bytes`, `photo_width`,
      `photo_height` for every shot with a representative frame.
- [x] T-D1.3 `cli.py`: call it for selected + rejected shots; add `photos_written`,
      `photos_total_bytes`, `photos_dir` to the run summary/artifacts; warn when disabled or
      incomplete.
- [x] T-D1.4 `tests/test_cli_integration.py`: every selected/rejected shot has a JPEG, the
      file is smaller than the PNG, and the fields match the decoded size.
- [x] T-D2.1 `app/simple.py`: card download prefers `photo_path`, falls back to `thumb_path`
      with an honest label; two bulk buttons (light ZIP, full ZIP); keys stable.
- [x] T-D2.2 `app/ui.py`: `load_ui(path, mtime)` and `zip_bytes` keyed by mtimes, so a
      regenerated run is not served from cache.
- [x] T-D3.1 Verify the three downloads in the browser: sizes and `completed` state.
- [x] T-D3.2 If the full ZIP still fails, keep the light ZIP as the only bulk download and
      show the absolute folder path (recorded as a warning).

## U — Upload from the web

- [x] T-U1.1 `.streamlit/config.toml`: `server.maxUploadSize = 4096`, headless defaults.
- [x] T-U1.2 `app/upload.py`: `save_upload(uploaded) -> StoredVideo` (8 MB chunks, SHA-256,
      dedupe by hash), `prepare_source(uploaded, local_path)`.
- [x] T-U1.3 `app/upload.py`: `run_directory(stem, hash)` deterministic; `existing_run(...)`
      returns the run when hash + config hash match.
- [x] T-U1.4 `app/upload.py`: `start_job(...)` (Popen, merged stderr), `stream_job(...)`
      (line-by-line, last line + elapsed), `cancel_job(...)`.
- [x] T-U1.5 `app/ui.py`: "Subir un vídeo" block at the top of the simple view and in the
      technical sidebar; progress panel; cancel; error panel with the log tail.
- [x] T-U1.6 Cleanup: remove the run dir if the job failed before writing `ui.json`.
- [x] T-U1.7 Tests: hash equal to `hashlib.sha256`, dedupe, invalid extension, deterministic
      run dir, fake process streaming, no `ui.json` on cancel.

## P — Presets

- [x] T-P1.1 `presets.py`: optional `hard_gates` per preset.
- [x] T-P1.2 `config.py`: `_apply_preset` merges the preset gates (recorded in the audit).
- [x] T-P1.3 New weights/targets/gates for `portrait`, `action`, `landscape`, `low_light`,
      `shorts`; `balanced_v2` stays as the reference.
- [x] T-P1.4 Tests: pairwise weight L1 ≥ 0.10 or differing target band; Top-10 Jaccard < 0.8
      on a fixed fixture; `balanced_v1` unchanged.
- [x] T-P1.5 UI: show dominant dimension and duration band in the preset caption.
- [x] T-P2.1 Measure Jaccard on `IMG_1564.mov` with `tmp_presets.py`; all non-legacy pairs
      ≤ 0.7.
- [x] T-P2.2 Regenerate the 4K run and confirm the simple view still renders.

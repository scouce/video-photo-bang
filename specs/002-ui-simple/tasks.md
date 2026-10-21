# Tasks 002 — Simple UI for non-photographers

Work in order. One task at a time; run `pytest -q` and `ruff check .` before marking a task
done. Do not start a task until the previous one is reviewed.

## F2 — Shell + Resultados (done)

- [x] T2.1 Client split: `app/ui.py` (shell + technical tabs), `app/simple.py` (simple mode),
      `app/copy_es.py` (plain copy). Technical views untouched; the app directory is put on
      `sys.path` so the flat imports work under both `streamlit run` and AppTest.
- [x] T2.2 Mode selector in the sidebar (`Simple` default, `Técnico`); run switches reset
      preferences, the focused shot and the gallery page.
- [x] T2.3 Header in plain language ("El vídeo dura 5:43 y tiene 66 planos…"); the
      `initial_uncalibrated` banner stays in both modes.
- [x] T2.4 Gallery cards: status chip with icon + text, plain discard reason, `mm:ss` +
      duration, preview, `Ver ficha`, `Descargar` (full-resolution PNG).
- [x] T2.5 Filters (`Recomendados | Descartados | Todos`), order (`Mejor primero | Por
      tiempo`), paginated at 12 cards.
- [x] T2.6 `Descargar recomendadas (ZIP)` built from the full-resolution PNGs, plus
      `Descargar configuración (JSON)`.
- [x] T2.7 Ficha in a modal dialog: large preview, derived "Destaca por…" sentence,
      filters it failed, and `Ver detalle técnico` with the raw/normalized table.
- [x] T2.8 Tests: `tests/test_ui_simple.py` (default mode, card count, ZIP payload, discard
      filter, jargon, preset writes config, reset, "why" determinism) and the smoke tests
      updated to switch to Técnico explicitly.

## F1 — Data: thumbnails for recommended and discarded shots

- [ ] T1.1 `config.py`: add `artifacts.thumbnails = {"enabled": true, "max_dimension": 480, "quality": 80}`.
- [ ] T1.2 `artifacts.py`: `export_shot_thumbnails(video_path, shots, dir, config)` → one JPEG
      per shot, deterministic path `media/thumbs/<shot_id>.jpg`, returns written paths + sizes.
- [ ] T1.3 `cli.py`: call it after shot records exist; add `thumb_path`, `thumb_width`,
      `thumb_height` for selected + `rejected_gate` + `rejected_floor`; warn
      (`thumbnails_skipped`) when disabled or failed.
- [ ] T1.4 `ui.json` / `shots.csv`: expose the new fields; update `build_ui_document`.
- [ ] T1.5 Measure the added cost on `IMG_1564.mov` (19 shots, expected +10–20 s).
- [ ] T1.6 Tests: `test_thumbnail_artifact` (path, existence, max edge), config defaults.
- [ ] T1.7 Client: prefer `thumb_path` over the in-memory downscale when present, and use
      `preview_bytes` only as fallback.

## F3 — Ajustar (encapsulated controls)

- [ ] T3.1 `Ajustar` page: preset (6 plain options, no `balanced_v1`), `top_n` (5/10/20),
      diversity toggle — the controls that already exist in the simple sidebar.
- [ ] T3.2 Quality level (`Permisiva | Estándar | Exigente`) mapped to the 4 documented fields;
      show the mapping in a "¿Qué cambia exactamente?" expander.
- [ ] T3.3 Minimum duration (0.5 / 1 / 2 s).
- [ ] T3.4 `Avanzado` expander with the 8 weights and plain descriptions.
- [ ] T3.5 `Restablecer` (exists) and `Ver configuración` (JSON preview) + `Descargar config`.
- [ ] T3.6 Tests: level → exact values; exported config reproduces the CLI ranking.

## F4 — Copy and accessibility

- [ ] T4.1 Extend `app/copy_es.py` with the glossary surface in the sidebar (`GLOSSARY`).
- [ ] T4.2 Map every gate name to plain language (done for the 7 active gates); keep the
      unknown-gate fallback.
- [ ] T4.3 Contrast and target-size pass on the dark theme; gallery reflows at 200 % zoom.
- [ ] T4.4 `test_no_jargon_in_simple_mode` (done) and `test_technical_mode_unchanged`.
- [ ] T4.5 Update `README.md` (done), `handoff/module_map.md` (done),
      `handoff/next_iterations.md`; note the iteration in `MEMORY.md`.
- [ ] T4.6 Screenshots of Resultados, the ficha dialog and the discard view.

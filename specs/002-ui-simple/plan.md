# Plan 002 — Simple UI for non-photographers

Read `docs/constitution.md`, `specs/001-mov-shot-mvp/spec.md` (RF-27 to RF-31) and this plan
before changing the client. The DSP core is **not** touched by this iteration.

## 1. Why

The current client is a calibration console for the person who wrote the pipeline:

| Signal | Current value |
|---|---|
| Tabs | 6 (Calibración, Ranking y gates, Fronteras, Distribuciones, Resumen, Auditoría) |
| Adjustable controls | ~36 (8 weights, 7 gates, 4 target bands × 3, floor, Top-N, diversity, merge, normalization) |
| Vocabulary | Tenengrad, Bhattacharyya, MMR, p5–p95, jitter, `initial_uncalibrated` |
| Photo preview | Buried at the bottom of Calibración, one shot at a time |
| Download | Config and `audit.json` only; no image download |

A user who does not understand photography cannot answer *"what weight should texture get?"*.
They can answer *"are these for portraits or for landscapes?"*. The UI must ask the second
question and translate the answer into the same auditable config.

## 2. Principle: encapsulate, never hide

Constitution rule 1 says every decision must be reconstructible from the output. Therefore:

1. Every simple control writes **explicit config fields** (no new hidden defaults).
2. Every simple control has a **"¿Qué cambia exactamente?"** expander with the field names
   and values it sets.
3. **"Descargar config"** keeps working and must reproduce the CLI ranking byte-for-byte
   (existing `test_ui_smoke.py::test_weight_change_reranks` extended).
4. The `initial_uncalibrated` banner stays visible in both modes.
5. Technical mode is always one click away and keeps all 6 tabs unchanged.

## 3. Information architecture

Decisions taken with the user before implementation:

| Question | Decision |
|---|---|
| Order of work | F2 first, with the PNGs the run already exports, then F1 widens coverage |
| Default mode | Simple; the choice is remembered only for the session |
| Thumbnail coverage | Recommended + discarded (selected, `rejected_gate`, `rejected_floor`) |
| Downloads on the main page | Individual PNG + ZIP of the recommended + config JSON |

Two modes, one shell.

```
Sidebar                          Main
─────────────────────────────    ────────────────────────────────────────────
[modo: (●) Simple  ( ) Técnico]
Run: img1564_calib2
                                 Modo Simple
Fuente: IMG_1564.mov              ├─ Resultados   (default)
5 min 43 s · 66 planos            └─ Ajustar
                                  Modo Técnico: the current 6 tabs
Qué buscas: [Equilibrado ▾]
Cuántas: [10]
Evitar repetidos: [x]
Exigencia: [Estándar ▾]
[Restablecer]  [Ver configuración]
```

### 3.1 Resultados (main page)

1. **Header** in plain language: total duration, shots found, recommended count.
2. **Gallery** (responsive 3-column grid, paginated 12 at a time):
   - 480 px thumbnail (portrait images keep a fixed aspect box, no layout jump).
   - `mm:ss` start, duration, status chip with **icon + text** (`✓ Recomendado` /
     `✕ Descartado` / `· Pasa, no elegido`).
   - Discard reason in plain language (`min_sharpness_score` → "Se ve borroso").
   - Buttons: **Ver ficha** and **Descargar foto**.
3. **Download all**: `Descargar recomendadas (ZIP)` with the full-resolution PNGs.
4. **Filters**: `Recomendados | Todos | Descartados`, order `Mejor primero | Por tiempo`.
5. **Ficha** (expander/modal): large image, a deterministic "Por qué está aquí" sentence
   built from the two highest-contribution dimensions, and **Ver detalle técnico** which
   opens the existing raw/normalized table.

### 3.2 Ajustar

Three questions, then optional depth:

| Question | Options | Writes |
|---|---|---|
| ¿Para qué usarás las fotos? | Equilibrado, Personas, Paisajes, Acción, Poca luz, Clips cortos | `preset` → `score_weights`, `targets`, `quality_floor` |
| ¿Cuántas fotos quieres? | 5 / 10 / 20 | `top_n` |
| ¿Evitar planos repetidos? | Sí / No | `diversity.enabled` (weight stays 0.25) |
| ¿Cuánta exigencia? | Permisiva / Estándar / Exigente | see table below |
| Duración mínima | 0.5 / 1 / 2 s | `hard_gates.min_shot_duration_s` |

Quality levels are explicit and visible (proposal, still `initial_uncalibrated`):

| Level | `quality_floor.min_total_score` | `min_sharpness_score` | `max_jitter_px` | `max_instability` |
|---|---|---|---|---|
| Permisiva | 0.00 | 0.05 | 6.0 | 0.55 |
| Estándar | 0.25 | 0.15 | 4.0 | 0.40 |
| Exigente | 0.45 | 0.35 | 2.0 | 0.25 |

"Avanzado" (collapsed) keeps the 8 weight sliders with plain names and one-line
descriptions; it is the same widget set the technical mode uses.

## 4. Plain-language layer

- All copy in `app/copy_es.py` (single reviewable source).
- **Glossary** expander: nitidez, exposición, estabilidad, movimiento, diversidad, p5–p95.
- **Status chips** never rely on color alone (icon + text + reason).
- **Derived "why"**: template built from `dimension_scores` and `weights_effective`, e.g.
  "Está aquí por su nitidez (0.98) y su exposición (0.97); pierde algo de estabilidad."
  Marked as "explicación derivada del ranking", not an editorial judgement.
- Discard reasons mapped: `min_sharpness_score` → "Poco nítido",
  `max_jitter_px` → "Se mueve demasiado", `max_black_clip` → "Demasiado oscuro",
  `max_white_clip` → "Quemado", `max_instability` → "Cambia demasiado dentro del plano",
  `min_shot_duration` → "Demasiado corto".

## 5. Artifact changes

The gallery needs an image per shot; today only the 10 selected shots get a PNG and only
`selected_frame_image_path` is recorded.

1. New artifact: `media/thumbs/<shot_id>.jpg`, longest edge 480 px, JPEG quality 80, for
   every **recommended and discarded** shot (selected + `rejected_gate` + `rejected_floor`).
   Shots that pass but are not selected stay table-only in the technical mode; that keeps
   the extra seeks to ~19 of 66 on the 4K sample.
2. `ui.json` shot records gain `thumb_path`, `thumb_width`, `thumb_height`; `ui.json` keeps
   its self-contained contract (RF-29) — the client still never opens the video.
3. Full-resolution PNGs stay limited to `top_n` (unchanged `export_representative_frames`).
4. `config["artifacts"]["thumbnails"] = {enabled, max_dimension: 480, quality: 80}`.
5. **Determinism note:** JPEG bytes depend on the libjpeg/OpenCV build, exactly like the
   existing PNGs. `samples.csv.gz` remains the byte-stable artifact (RF-28); the plan adds
   a warning line to the audit if thumbnails are skipped.
6. **Interim (F2, shipped):** while F1 is pending, the client downscales the full PNG in
   memory (`simple.preview_bytes`, cached by path + mtime) so the gallery never ships 6 MB
   images to the browser. F1 replaces that work at render time with a precomputed file.

## 6. Accessibility checklist (WCAG 2.1 AA)

| Item | Target |
|---|---|
| Contrast | Text ≥ 4.5:1, UI borders ≥ 3:1 (verify the current dark theme) |
| Color independence | Every chip has an icon and text |
| Target size | ≥ 44×44 px for buttons and download actions |
| Keyboard | All controls reachable; Streamlit native widgets only |
| Focus | Visible focus ring on download buttons |
| Zoom | 200% usable; gallery reflows to 1 column |
| Alt text | `caption` describes the shot and its timestamp |
| Language | Plain Spanish (B1), sentences < 20 words, no DSP jargon in Simple mode |
| Errors | Empty/denied states explain the cause and the fix |
| Motion | No autoplay, no animation |
| Consent | Nothing applies until `Aplicar`; `Restablecer` always available |

## 7. Code structure

| File | Change |
|---|---|
| `app/ui.py` | Keeps the shell: run selection, mode switch, session state, shared loaders |
| `app/views_simple.py` | New: Resultados + Ajustar |
| `app/views_technical.py` | Move the 6 existing tabs, unchanged behaviour |
| `app/copy_es.py` | New: labels, plain-language reasons, glossary, tooltips |
| `app/theming.py` | New: status chips, gallery card, section helpers |
| `src/video_dsp/artifacts.py` | Thumbnail export + shot fields |
| `src/video_dsp/config.py` | `artifacts.thumbnails`, quality-level presets (data only) |
| `src/video_dsp/cli.py` | Wire thumbnail generation, record the warning when skipped |

Streamlit caveat found during review: widget keys are scoped by `generation`, and switching
run or mode must bump it, otherwise the sliders keep stale values. F2 includes an explicit
reset test for that.

## 8. Tests

| Test | Type | Asserts |
|---|---|---|
| `test_ui_simple_default` | AppTest | Simple mode is default; Resultados renders; one card per selected shot |
| `test_gallery_download_buttons` | AppTest | One download button per card + ZIP button |
| `test_zip_contains_selected_pngs` | unit | ZIP has exactly `top_n` entries with the shot ids |
| `test_quality_level_mapping` | unit | Level → exact gate/floor values, recorded in the exported config |
| `test_simple_config_reproduces_cli_ranking` | integration | Export config → CLI rerun → same shot ids and order |
| `test_no_jargon_in_simple_mode` | AppTest | Rendered simple-mode text contains none of `Bhattacharyya`, `MMR`, `p5`, `tenengrad`, `jitter` |
| `test_mode_switch_resets_state` | AppTest | Switching run/mode resets sliders to the run's config |
| `test_technical_mode_unchanged` | AppTest | The 6 tabs still render and re-rank |
| `test_thumbnail_artifact` | unit | Every shot has `thumb_path`, file exists, longest edge ≤ 480 |

## 9. Risks

| Risk | Mitigation |
|---|---|
| Hiding controls hides calibration truth | "¿Qué cambia exactamente?", config export, uncalibrated banner |
| Plain "quality levels" read as validated | Explicit "sin calibrar" copy next to each level |
| 66 thumbnails slow the run | 480 px JPEG, measure; fall back to selected + rejected |
| Gallery with 6 MB PNGs | Thumbnails in the grid; full PNG only behind the download button |
| Two modes drift apart | One config write path (`build_config`), one test that both modes export the same JSON |
| Session state staleness | `generation` bump on run/mode change + regression test |

## 10. Phases

| Phase | Deliverable | Acceptance |
|---|---|---|
| F1 — Data | Thumbnails + paths + config + tests | 66 shots with `thumb_path`; run cost measured; tests green |
| F2 — Shell + Resultados | Mode switch, gallery, preview, download one/all | A non-photographer can open the app and download a photo without leaving the main page |
| F3 — Ajustar | 3 questions + quality level + advanced + reset | Preset choice changes Top-N and the export matches the CLI |
| F4 — Copy + a11y | `copy_es.py`, glossary, checklist, docs | Jargon test passes; contrast and keyboard checklist recorded |

Each phase ends with `pytest -q`, `ruff check .`, and a screenshot of the new screen.

## 11. Out of scope

Semantic scoring, faces, aesthetic judgement, batch multi-video, clip export, auth,
telemetry. The tool remains a technical draft selector.

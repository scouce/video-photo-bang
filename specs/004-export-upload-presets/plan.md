# Plan 004 — Downloads, upload from the web, and presets that differ

Three user-facing gaps, each with a measured cause:

1. The download buttons fail (`state=failed`, 0 bytes) for the PNG (7 MB) and the ZIP (71 MB);
   the 4 KB config JSON downloads fine.
2. The only way to get a run is the CLI; the web app cannot take a video.
3. `portrait` and `low_light` select **exactly the same Top-10** (Jaccard 1.00) and
   `balanced_v2` overlaps them at 0.82. The presets are labels on almost the same numbers.

Constraints unchanged: the core stays classical and deterministic, no semantic scoring, the
input video is never modified, and every derived value is recorded.

---

## 1. Downloads

### 1.1 What was measured

| Download | Size | Result in the connected browser |
|---|---|---|
| Config JSON (`st.download_button`) | 4 KB | completed, 4 302 bytes |
| One representative frame (PNG) | 7.0 MB | **failed, 0 bytes** |
| "Descargar recomendadas" (ZIP of 10 PNG) | 71.3 MB | **failed, 0 bytes** |
| `/media/...` endpoint, direct `fetch` | all | HTTP 200, correct `Content-Type` |

The server is not the problem: the endpoint serves the exact bytes. The failure scales with
size, and the payloads are absurd for a gallery: a 4K PNG is 7 MB and the ZIP is 71 MB.

### 1.2 Secondary defect found

`load_ui(path)` is cached by path only, so after regenerating a run the client kept serving
the old `ui.json`. That is why the gallery was still downscaling full PNGs in memory instead
of using the new 480 px thumbnails. Cache keys must include the file mtime.

### 1.3 Design

**Full-resolution JPEG as the download format.**
`export_shot_photos(input_path, shots, dir, quality=92)` writes `media/photos/<shot_id>.jpg`
for every shot with a representative frame, and records `photo_path`, `photo_*_bytes`,
`photo_width`, `photo_height`. Measured on this clip: **0.81–0.94 MB per photo** (vs 6.4–7.3 MB
PNG), no visible loss at q92 for review and social use. The PNG stays available through the
CLI (`--thumbnails`) and in `ui.json` for archival use; the UI downloads the JPEG.

**Two ZIPs, explicitly labelled.**

| Button | Content | Expected size |
|---|---|---|
| `Descargar todas (ligero)` | 480 px thumbnails | ~0.4 MB |
| `Descargar todas (calidad completa)` | full-resolution JPEGs | ~9 MB |

The light ZIP is the default because it is the one that works everywhere and is what a
non-photographer needs to share a pick; the full ZIP is one click away.

**Every card can download something.** Recommended and discarded shots both have a
thumbnail; recommended shots also have the full JPEG. The card offers the best available
file and names it accordingly (`Descargar foto` vs `Descargar vista previa 480 px`). No
button ever promises a resolution it cannot deliver.

**Cache correctness.** `load_ui(path, mtime)` and `zip_bytes(paths, names)` keyed by mtimes,
so a regenerated run is picked up without restarting the server.

**Filenames and MIME.** `shot_0003_00m06s.jpg` (time is in the name, stable across reruns),
`mime="image/jpeg"`, `ZIP` named `<run_id>_fotos.zip`. The CLI artifact keeps its own naming.

### 1.4 Acceptance

- In the connected browser, a real click on each button ends in `completed` with a non-zero
  size: photo ≈ 0.9 MB, light ZIP < 1 MB, full ZIP < 15 MB.
- `pytest` covers the export function (file exists, JPEG magic, dimensions unchanged, fields
  recorded) and the CLI integration (10 photos for 10 selected shots).
- The run reports `photos_written` and the total bytes in the summary.

### 1.5 Fallback if a size still fails

Keep the light ZIP as the only bulk download and add a "carpeta de descargas" line with the
absolute path of `media/photos/`, so the user can open it from the file explorer. This is
recorded as a warning, not silently swapped.

---

## 2. Upload a video from the web

### 2.1 Design

A new module `app/upload.py`, outside `src/video_dsp` (the core keeps its single entry point).

**Inputs.**

- `st.file_uploader` accepting `.mov .mp4 .m4v .avi .mkv`, streamed to disk in 8 MB chunks
  (never fully in memory) while hashing with SHA-256.
- A "ruta local" text field for files that already exist on the machine (a 3 GB clip does not
  need to cross the websocket). Both paths funnel into the same `prepare_source()`.

**Storage.** `out/uploads/<sha256[:12]>_<original_name>`; the directory is inside the existing
`out/` ignore rule. Re-uploading the same bytes reuses the same file (hash check, no copy).

**Run directory.** `out/runs/<stem>_<hash8>` (deterministic). If `ui.json` already exists for
that hash **and** the default config hash, the app opens it instead of reprocessing: "Ya
teníamos este vídeo, abriendo el análisis". A different config means a new run.

**Execution.** `subprocess.Popen([sys.executable, "-m", "video_dsp.cli", source, "--run-dir",
run_dir, "--out", run_dir/audit.json], cwd=ROOT)`, stdout and stderr merged, read line by
line and shown in `st.status`. The CLI is the only pipeline entry point, so a run created
from the web is byte-identical to one created from the terminal. The process handle lives in
`st.session_state`; if the user navigates away, the process still finishes and the run
appears in the selector on the next rerun.

**Progress.** The CLI already prints `[video_dsp] sampled N frames...`; the panel shows the
last line plus elapsed time, and a "Cancelar" button that terminates the process and records
`job_cancelled` in the run directory. On failure, the last 40 log lines are shown and the run
directory is kept for inspection.

**Limits and honesty.** `.streamlit/config.toml` with `server.maxUploadSize = 4096` (MB).
Above that the app says so before starting, and points to the local-path field. The upload is
local; no network call leaves the machine.

**Config used.** The run uses the current preset of the session when it starts, and the run
records it. Changing presets afterwards recomputes in the client without re-decoding, exactly
as today.

### 2.2 Acceptance

- Uploading a 20 MB synthetic sample from the browser creates a run, shows progress, and the
  new run is selected and rendered when it finishes.
- Uploading a file whose hash already has a run does not reprocess.
- A cancelled job leaves no half-written `ui.json` (the CLI writes artifacts at the end).
- Tests: `save_upload` writes the same hash as `hashlib.sha256` over the bytes, dedupe works,
  the run-directory name is stable, and an invalid extension is rejected with a message.
- `st.file_uploader` and the subprocess are exercised with a fake object and a stub process;
  the real upload is verified once by hand on `IMG_1564.mov`.

### 2.3 Out of scope

Background queue, multiple simultaneous uploads, remote hosting, transcoding. One upload at a
time, one process at a time.

---

## 3. Presets that are actually different

### 3.1 What was measured (current table, `IMG_1564.mov`, Top-10)

| | v1 | v2 | portrait | action | landscape | low_light | shorts |
|---|---|---|---|---|---|---|---|
| v2 | .67 | — | .82 | .18 | .82 | .82 | .33 |
| portrait | .82 | .82 | — | .25 | .67 | **1.00** | .43 |
| low_light | .82 | .82 | **1.00** | .25 | .67 | — | .43 |

`portrait` and `low_light` are the same selection. The weights differ by at most 0.06 and the
gates are global, so a preset changes the ordering slightly but not the answer.

### 3.2 Design

**Presets may override gates.** `_apply_preset` merges an optional `hard_gates` block from the
preset into the config (recorded in the audit, as today with `calibration`). Gates are part of
what a preset means: an action preset must tolerate jitter that a portrait preset rejects.

**Each preset states one intent and moves the numbers that express it.** Weights alone are
not enough; the differences are in weights **and** target bands **and** tolerances:

| Preset | Intent | Dominant weights | Band | Gates it relaxes/tightens |
|---|---|---|---|---|
| `balanced_v2` | reference | sharpness .28, exposure .18, stability .16 | duration 3–8 s, motion .04–.45 | baseline |
| `portrait` | one person, clean frame | sharpness .30, exposure .24, stability .16, color .12 | duration 2.5–7 s, motion .01–.20, saturation .20–.60 | tighter jitter (3 px), sharper floor (.20) |
| `action` | movement is the point | motion .30, sharpness .18, exposure .12 | duration 1.5–5 s, motion .20–1.20, pan ≤ 120 | looser instability (.55), jitter 8 px |
| `landscape` | scene detail | texture .20, contrast .18, color .14, sharpness .20 | duration 4–12 s, motion .02–.25 | tighter sharpness floor (.25), looser duration |
| `low_light` | dark footage | exposure .34, sharpness .22, stability .18 | saturation .05–.40, motion .02–.30 | black clip .35, white clip .02 |
| `shorts` | vertical/social clips | duration .18, motion .16, sharpness .22 | duration 1–4 s, motion .08–.70 | min duration 1.0, max 6 s |

`balanced_v1` is legacy and untouched (reproducibility).

**Tests assert separation, not just numbers.** A preset test computes the Top-10 of a fixed
synthetic fixture for every preset and requires every non-legacy pair to have Jaccard < 0.8,
plus a table test that every pair differs in at least 0.10 of total weight L1 **and** in at
least one target band. That turns "the presets look the same" into a failing test.

**UI.** The sidebar already shows the description; it now also shows the dominant dimension
and the duration band, so the user sees what will change before switching.

### 3.3 Acceptance

- On `IMG_1564.mov`, every non-legacy pair has Jaccard ≤ 0.7 (currently portrait/low_light =
  1.00, v2/portrait = 0.82). Measured and printed by the plan's script, recorded in the PR
  notes.
- Each preset's Top-10 has a different mean profile: the dominant dimension of the selected
  set moves in the intended direction (e.g. `action` picks the highest-motion shots).
- Existing tests pass; `balanced_v1` output is unchanged (guard test).
- Presets stay `initial_uncalibrated`: this is a design change, not a calibration claim.

---

## 4. Order and verification

| Step | Work | Gate |
|---|---|---|
| D1 | `export_shot_photos` + fields + CLI summary | unit + integration tests |
| D2 | Client: photo/thumbnail download, two ZIPs, cache by mtime | `pytest`, `ruff` |
| D3 | Real-browser check of the three downloads | `state=completed`, sizes recorded |
| U1 | `.streamlit/config.toml`, `app/upload.py`, UI block | tests + one real upload |
| U2 | Dedupe by hash, cancel, failure handling | tests |
| P1 | `hard_gates` per preset, new weights/targets | preset separation test |
| P2 | Measure Jaccard on the 4K run, regenerate it | numbers in the summary |

Every step keeps `pytest -q` and `ruff check .` green before the next one starts.

## 5. Risks

| Risk | Mitigation |
|---|---|
| A 9 MB ZIP may still fail in a restricted browser | light ZIP is the default; the path fallback is documented |
| JPEG q92 is "lossy" | it is a delivery copy; the PNG stays in the run and the CLI can re-export |
| Uploading GBs blocks the UI | streamed to disk, subprocess, progress, cancel |
| A cancelled job leaves partial artifacts | the CLI writes artifacts at the end; the UI deletes a run dir it created if `ui.json` is missing |
| Presets tuned on one clip | keep `initial_uncalibrated`, assert only separation, not quality; 003 calibrates later |
| Duplicate downloads of the same run | hash + config hash dedupe |

## 6. Out of scope

Cloud upload, authentication, multi-user, background queue, video preview/trimming inside the
browser, calibrating the new presets (that is 003).

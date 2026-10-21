# Next iterations

Prioritized backlog after the calibration-first iteration (v0.2.0). Keep the core classical
and deterministic.

## Done in v0.2.2 (simple UI, F2)

- `Simple` mode is the default: results gallery with previews, per-photo PNG download, ZIP of
  the recommended shots and config JSON — all on the main page.
- Modal "ficha" per shot: derived, jargon-free explanation plus the raw/normalized evidence.
- Encapsulated sidebar (foto type, count, duplicate suppression) writing the same config.
- `Técnico` mode keeps the six tabs; one config write path, one export.
- 480 px JPEG preview per recommended and discarded shot (`media/thumbs/<shot_id>.jpg`),
  so the gallery shows every card without decoding 4K PNGs.

## Next for the simple UI

1. **F3 — Ajustar page**: quality level (permisiva/estándar/exigente) mapped to explicit
   gates, minimum duration, advanced weights, "¿Qué cambia exactamente?".
2. **F4 — accessibility pass**: glossary surface, contrast/target-size check, screenshots.
3. **Keyboard-first gallery**: per-card focus ring and `Enter` to open the ficha.
4. **Classification review**: the discard reasons and the "Destaca por…" sentence are the
   first place to look when a recommended shot feels wrong; the technical mode still holds
   the raw values.

## Done in v0.2.0

- Per-frame CSV (`samples.csv.gz`), byte-deterministic.
- Near-duplicate suppression with MMR over Bhattacharyya similarity.
- Preference presets (7) with weights, target bands and quality floor.
- Human annotation loop: level A verdicts, level B pairs, boundary verdicts, and an
  evaluation report (precision/recall/NDCG, gate false rejects, dimension separation).
- Boundary evidence montages (five frames per cut), replacing clip export.
- Live re-ranking client with real shot rebuild on merge changes.
- `.mp4` / `.m4v` / `.avi` / `.mkv` support.

## Done in v0.2.1

- Boundary prominence filter (`peak_prominence_ratio`): a local maximum inside sustained
  motion is no longer a cut. On `IMG_1564.mov` this removed 22 of 98 candidates.
- Minimum shot duration raised from 0.5 s to 1.0 s, so sub-second fragments are merged
  before scoring instead of competing for the Top-N.
- Rejected peaks are recorded in the audit and listed in the boundary tab.

## P0 — Calibration and trust

1. **Calibration corpus.** Run the pipeline on 10–20 varied clips (indoor/outdoor, low/high
   light, static/handheld, portrait/landscape) and record metric distributions per preset.
2. **Range calibration.** Compare per-video percentiles against corpus percentiles per
   preset; keep per-video as default, offer corpus bounds as an explicit alternative and
   record which one was used.
3. **Gate calibration.** Set the sharpness and clipping gates from labelled false-reject /
   false-accept analysis. Keep `initial_uncalibrated` until the corpus supports a change.
4. **Determinism regression test.** Run the pipeline twice on the synthetic sample and assert
   `audit.json` is identical after removing `generated_at_utc`, and that `samples.csv.gz`
   bytes match.

## P1 — Detection quality

5. **Over-segmentation control in the CLI.** `--merge-similarity` exists; add a per-run report
   of *which* merges happened (shot pairs, similarity) so a bad threshold is visible without
   opening the UI.
5b. **Discriminative diversity signature.** On single-scene handheld footage the mean
   luminance histogram gives Bhattacharyya similarity ≥ 0.95 for almost every pair, so the
   MMR slider is inert (`displaced_by_diversity` is empty). Replace or augment the signature
   with a spatial grid (coarse luminance blocks) or an added color histogram so diversity can
   actually displace near-duplicates. Record which signature was used.
6. **Transition handling.** Detect fades and dissolves explicitly instead of treating them as
   cuts or long shots.
7. **Artifact metrics.** Blockiness, banding and mosquito-noise estimates, to catch
   compression damage that sharpness alone misses.
8. **Optical-flow instability.** Replace or augment the distance proxy with a coarse flow
   magnitude/variance measure (still classical, still deterministic).

## P2 — Workflow

9. **Remove the legacy `scoring.py` path.** It is no longer imported by the CLI or the client;
   keep it only until `balanced_v1` no longer needs a readable reference implementation.
10. **Batch runs.** Score a folder, keep the per-run contract, add a cross-video summary. The
   service layer already accepts arbitrary shot lists; the CLI is the single-video entry.
11. **Label-guided preset proposal.** Suggest which weight vector best explains the existing
    level A/B labels (a constrained grid search, reported as a proposal, never applied
    automatically).
12. **VFR normalization.** Optionally remap to constant frame rate with ffmpeg when VFR is
    detected.
13. **Config provenance.** Record the resolved config file path and the CLI overrides in the
    audit JSON, not only the merged config.

## P3 — Product surface

13. **Contact sheet.** One montage of the Top-N frames for quick review.
14. **Multi-run comparison in the UI.** Diff two runs (different presets) side by side.
15. **Performance.** Native-resolution analysis with tiled metric computation, or a faster
    sampling path for long clips. Current cost is dominated by 4K decode plus per-frame HSV
    and local-contrast passes.
16. **Packaging.** Publish a small CLI wheel and document Windows/macOS/Linux installs.

## Explicitly out of scope

Semantic understanding, face scoring, narrative scoring, learned quality models, and any
network service.

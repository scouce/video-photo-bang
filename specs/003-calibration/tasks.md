# Tasks 003 — Full calibration of the technical measurements

Work in order. One task at a time; `pytest -q` and `ruff check .` before marking a task done.
The DSP core stays classical and deterministic; RF-34 stays: no automatic weight changes.

## C0 — Veto and frame-level rubric (immediate)

- [ ] T0.1 `labels.py`: schema 1.1 with `frame_verdict`, `frame_timestamp`, extended reasons
      (`mid_gesture`, `eyes_closed`), and a `excluded` flag; migrate 1.0 files on load.
- [ ] T0.2 `config.py` + `selection_service.py`: `excluded_shot_ids`, applied before gates and
      recorded per shot (`excluded_by_user`) and in the summary.
- [ ] T0.3 CLI: `--exclude-shot` (repeatable) and reading the flag from `labels.json`.
- [ ] T0.4 UI Calibración: "Esta foto no vale" one-click veto on the large frame, plus the
      reason dropdown; show the vetoed shots in a separate list with an "undo".
- [ ] T0.5 Simple view: excluded shots never appear in "Recomendados"; they show in
      "Descartados" with "excluido por ti".
- [ ] T0.6 Tests: veto removes the shot, the config records it, the audit shows it, undo works.
- [ ] T0.7 Verify on `img1564_calib2`: 1:22 and 1:25 leave, the other eight stay.

## C1 — Annotation tooling

- [ ] T1.1 Annotation panel: frame first (large), then shot; keyboard shortcuts.
- [ ] T1.2 Label coverage report: shots labelled / total, pairs, κ on the repeated subset.
- [ ] T1.3 Export/summary of the labelled distribution by reason.

## C2 — Representative-frame rule

- [ ] T2.1 Implement `central_window`, `sharp_typical` in `sampling.py`/`export.py` as pure
      frame selectors over the sampled frames of a shot.
- [ ] T2.2 Config block `representative_frame = {strategy, center_margin, typicality_weight}`.
- [ ] T2.3 Experiment script comparing the four rules against `frame_verdict`; report table.
- [ ] T2.4 Apply the winning rule, record it per shot, rerun the 4K sample.

## C3 — Diversity

- [ ] T3.1 Spatial-grid signature (4×4 block histograms) computed per sampled frame.
- [ ] T3.2 AUC comparison on `duplicate` pairs: global hist vs grid vs HSV.
- [ ] T3.3 `diversity.min_time_gap_seconds` in config + MMR.
- [ ] T3.4 Sweep weight × spacing; report precision@10 and duplicate pairs in the Top-10.

## C4 — Measurement validity

- [ ] T4.1 Relative acutance metric (high/mid frequency energy) in `features.py`.
- [ ] T4.2 Texture as a band; contrast measured against the plain-background case.
- [ ] T4.3 AUC vs `blur` / `keep` labels; keep or drop each change with the number.

## C5 — Gates and floor

- [ ] T5.1 Threshold sweep per gate with the false-reject constraint.
- [ ] T5.2 Record the ROC point and the sample size in `calibration_report.json`.

## C6 — Weights

- [ ] T6.1 NNLS/Bradley-Terry on pairs; coordinate search on NDCG@10.
- [ ] T6.2 Bootstrap CI, constraint check, holdout comparison.
- [ ] T6.3 `proposed_config.json` + UI comparison table (baseline vs proposal).

## C7 — Corpus and promotion

- [ ] T7.1 Label 5–8 clips (varied conditions).
- [ ] T7.2 Leave-one-clip-out evaluation.
- [ ] T7.3 Promotion report: `calibrated_v1` or an explicit "not yet", with the numbers.

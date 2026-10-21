# Plan 003 — Full calibration of the technical measurements

Read `docs/constitution.md`, `specs/001-mov-shot-mvp/spec.md` (RF-32 to RF-34, RF-40) and
`specs/002-ui-simple/plan.md` before starting. Calibration changes numbers and policy, never
the DSP nature of the pipeline.

## 0. The seed case

The user reviewed the Top-10 of `IMG_1564.mov` and marked **1:22 (`shot_0021`) and 1:25
(`shot_0022`) as very bad photos; the other eight are fine**.

Both are technically excellent under the current scores:

| shot | t (s) | score | sharp | expo | contrast | stability | motion | texture |
|---|---|---|---|---|---|---|---|---|
| `shot_0021` | 82.0 | 0.887 | 0.90 | 0.96 | 0.97 | 0.73 | 1.00 | 0.89 |
| `shot_0022` | 84.8 | 0.888 | 0.89 | 0.97 | 0.94 | 0.71 | 1.00 | 0.84 |

The frames show the subject **bending over** and **with a hand in her hair**. No threshold can
separate them from `shot_0020` (0.941) without also rejecting good shots: the defect is the
pose/gesture, which is outside DSP by constitution. This single observation shapes the plan:

1. Some failures are **measurement failures** (the metric claims something it does not
   measure) → calibrate the metric.
2. Some failures are **representation failures** (the shot is fine but the chosen frame is a
   bad moment) → calibrate the representative-frame rule.
3. Some failures are **taste/context** (a mid-gesture frame is unusable for the user) → needs
   an explicit human veto, not a fake metric.

The plan separates the three, because calibrating one to fix another is how a ranking ends up
overfitted to a single video.

## 1. What "calibrating the measurements" covers

| Layer | Question | Evidence | Artifact |
|---|---|---|---|
| **Validity** | Does `sharpness` measure sharpness, or scene texture? | Correlation with human `blur` labels | `calibration_report.json` |
| **Normalization** | Which raw → 0..1 mapping is stable across clips? | Spread of scores per clip, holdout stability | `normalization` block |
| **Decision policy** | Gates, quality floor, target bands | ROC/F1 against closed-set reasons | `hard_gates`, `quality_floor` |
| **Ranking** | Weights | Pairwise labels (Bradley-Terry / NNLS) + NDCG@10 | `score_weights` |
| **Diversity** | Which similarity signature, which weight | AUC on `duplicate` pairs | `diversity` |
| **Frame choice** | Which sampled frame represents the shot | Agreement with `frame_verdict` | `representative_frame` |
| **Detection** | Cut thresholds | Boundary labels (`real_cut`) | `shot_detection` |

## 2. Ground truth

### 2.1 Two units, not one

The user's complaint is about a *photo* (the chosen frame), not necessarily about the shot.
The annotation must separate them:

- `shot_verdict` ∈ {keep, reject, unsure}: is this a usable **clip**?
- `frame_verdict` ∈ {keep, reject, unsure}: is the **frame we show** usable?
- `reject_reason` (closed set, extended): `blur`, `shake`, `bad_exposure`, `blocked_view`,
  `mid_gesture`, `eyes_closed`, `transition`, `too_short`, `duplicate`, `other`.

`mid_gesture` and `eyes_closed` are *human labels only*. They are never computed by the
pipeline; they exist so we can measure whether a proxy (frame rule, temporal spacing)
reduces them.

### 2.2 Sampling and reliability

- Level A on every shot of a clip (66 shots ≈ 20 min with thumbnails).
- Level B pairs: 60–100 per clip, sampled to cover the score range, not just the top.
- Repeat 10 % of items after 48 h; report Cohen's κ. Below 0.6, the rubric is rewritten
  before any calibration is trusted.
- Splits: **temporal holdout** (first half calibrates, second half validates) while only one
  clip exists; **leave-one-clip-out** once the corpus has ≥ 5 clips.

### 2.3 Corpus

| Phase | Clips | Purpose |
|---|---|---|
| C0–C3 | 1 (`IMG_1564`) | Seed, rule design, frame/diversity work |
| C4–C6 | 5–8 | Ranges, gates, weights, normalization choice |
| C7 | 10–20 | Promotion to `calibrated_v1` |

Diversity of conditions matters more than volume: indoor/outdoor, low/high light, static/
handheld, portrait/landscape, one subject / many.

## 3. Measurement inventory and hypotheses

Each row is a hypothesis to test, not a decision.

| Dimension | Raw metric now | Claim | Suspicion | Candidate change | Validation |
|---|---|---|---|---|---|
| sharpness | variance of Laplacian, Tenengrad (frame mean) | "in focus" | Rewards busy texture: braids 205 vs plain wall 67 | **Relative acutance**: high-frequency energy ÷ mid-frequency energy, per frame; keep absolute as secondary | AUC vs `blur` labels; correlation with `keep` |
| texture | edge density, entropy, local contrast | "detail" | Monotonic "more is better" rewards clutter | Convert to a **band** (enough detail, not noise) | Sign of correlation with `keep` |
| contrast | luminance std | "good contrast" | Plain backgrounds score low (0.39–0.55) | Band, not monotonic; or merge into exposure | AUC vs `keep` |
| exposure | clip fractions, mean, entropy | "well exposed" | Looks correct | Keep; recalibrate ranges only | AUC vs `bad_exposure` |
| stability | phase correlation, jitter | "no shake" | Looks correct; jitter is 0 on tripod-like shots | Keep; recalibrate gate | AUC vs `shake` |
| motion | translation per second | "liveliness" | **Saturated at 1.00 for every shot** | Narrow the band or drop the dimension | Distribution per clip |
| color | saturation, colourfulness | "pleasant colour" | 0.71–0.83 for all; low discrimination | Keep but check weight | Correlation with `keep` |
| duration | band | "usable length" | Fine | Recalibrate band from labels | Distribution |

**Rule:** a dimension that shows |correlation| < 0.1 with the labels over ≥ 100 shots is a
candidate for removal or re-weighting, not for "threshold tuning".

## 4. Method per layer

### 4.1 Ranges (`ranges`)

Per preset and per metric, take the corpus distribution and set `low = p10`, `high = p90` of
the **kept** shots. Report the sample size and the clip that contributed the extremes.
Keep the per-video p5–p95 normalization as the default; corpus ranges are the fallback and
must be recorded as such (`config_absolute` vs `per_video_p5_p95`, already in the artifact).

### 4.2 Gates and quality floor

For each gate, sweep its threshold and compute, against the shots labelled bad *for that
reason*:

- true reject rate (recall of bad),
- false reject rate (good shots lost),
- the threshold that maximises F1 subject to **false reject ≤ 5 %**.

Record the ROC point, not just the threshold. A gate that no label supports stays at its
current value and keeps `initial_uncalibrated`.

### 4.3 Weights

Two estimators, both deterministic and both reported side by side:

1. **NNLS on pairwise labels** (Bradley-Terry): features = dimension differences, positive
   coefficients, normalized to one.
2. **Coordinate search** over the simplex maximising NDCG@10 on the calibration half.

Accept a weight vector only if it also improves the holdout half. Report bootstrap CIs
(1 000 resamples, fixed seed). Constraints: each weight in `[0.02, 0.35]`, sum = 1.
RF-34 stands: the pipeline never applies these; the person does, via an exported config.

### 4.4 Diversity

Compare three signatures on the `duplicate` pairs: current 48-bin global luminance histogram,
4×4 spatial grid of block histograms, and an added HSV colour histogram. Metric: AUC to
separate `duplicate` from non-duplicate pairs. Then sweep the MMR weight and the temporal
spacing `min_time_gap_seconds` and measure precision@10 plus the number of near-duplicate
pairs in the Top-10.

### 4.5 Representative frame

Candidates, all deterministic:

| Rule | Definition |
|---|---|
| `max_variance_laplacian` (current) | Sharpest sampled frame |
| `central_window` | Sharpest within the middle 60 % of the shot |
| `sharp_typical` | Sharpest × (1 − 0.6 × histogram distance to the shot median) |
| `acutance_typical` | Same, using relative acutance instead of variance of Laplacian |

Select by agreement with `frame_verdict` on the labelled frames of the calibration half, and
confirm on the holdout. The chosen rule and its parameters are recorded on every shot
(`selected_frame_rule`, already in the artifact).

### 4.6 Human veto (not a metric)

A shot the user rejects by taste is stored in `labels.json` and applied as an **explicit
exclusion**: `excluded_shot_ids` in the config, shown in the audit and in the UI ("excluido
por ti"). It is deterministic, reversible and fully traceable. It does not pretend to be a
measurement, and it never enters the score.

## 5. Acceptance criteria

A parameter change is accepted only if all of this holds on the **holdout**:

| Criterion | Threshold |
|---|---|
| Primary metric (NDCG@10 or frame agreement) | +2 points over baseline |
| Any secondary metric | no drop > 1 point |
| False reject rate on `keep` shots | ≤ 5 % |
| Calibration sample | ≥ 30 labelled items for the affected metric |
| Reproducibility | the report regenerates byte-identically from labels + run |

Promotion from `initial_uncalibrated` to `calibrated_v1` requires ≥ 3 clips, ≥ 200 shots,
≥ 300 pairs, both holdouts, and every criterion above. Until then, the banner stays.

## 6. Tooling

| Piece | What it does |
|---|---|
| `labels.json` v1.1 | Adds `frame_verdict`, `frame_timestamp`, extended reasons, `excluded` flag |
| UI *Calibración* | Frame-large annotation: "esta foto es buena/mala" + reason, then "este plano es bueno/malo"; one-click veto |
| `scripts/calibrate.py` | Reads labels + runs, writes `calibration_report.json` and `proposed_config.json`; never writes config |
| `calibration_report.json` | Per parameter: old, new, metric before/after, n, CI, split, verdict |
| UI *Resumen* | Baseline vs proposal table on the holdout: NDCG@10, precision@10, false rejects, duplicates in Top-10 |
| `tests/test_calibration.py` | Estimators are deterministic; report schema; holdout split reproducibility |

Scripts live outside `src/video_dsp`; the core stays free of calibration code and of pandas.

## 7. Phases

| Phase | Deliverable | Acceptance |
|---|---|---|
| **C0** | Frame-level rubric + veto (`excluded_shot_ids`) in config, CLI, UI | 1:22 and 1:25 leave the Top-10, the other eight remain, the exclusion is in the audit |
| **C1** | Annotation tooling: frame vs shot verdicts, extended reasons, κ check | 66 shots + 10 frames labelled in ≤ 30 min; labels validate |
| **C2** | Frame-rule experiment on the labelled frames | Best rule ≥ 80 % agreement, holdout confirms |
| **C3** | Diversity signature + temporal spacing sweep | Top-10 duplicate pairs ≤ 1; precision@10 not worse |
| **C4** | Relative acutance and texture band as measured alternatives | AUC vs `blur` ≥ current + 0.05, or discarded with the number |
| **C5** | Gates and floor from the labelled corpus | F1 improvement with false reject ≤ 5 % |
| **C6** | Weights from pairs, bootstrap CI, holdout | NDCG@10 +2 points, all constraints met |
| **C7** | Corpus of 10–20 clips, leave-one-clip-out | Promotion report (`calibrated_v1`) or an explicit "not yet" |

C0 is immediate and independent of the rest: it fixes the reported case without touching a
single metric.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Overfitting to one video | Temporal holdout in C0–C3, leave-one-clip-out from C4 |
| "Good photo" is subjective | κ check, rubric with closed reasons, pairwise labels for order |
| Calibrating texture to fix gestures | The C0 seed shows the defect is pose, not measurement; document it |
| Silent drift of the label `initial_uncalibrated` | Promotion gate in §5, banner tested |
| Calibration code leaking into the core | Scripts outside `src/video_dsp`, `ruff` and a test enforcing no pandas there |
| User time | 20 min per clip; batch labelling in the UI with thumbnails |

## 9. Out of scope

Face detection, gaze estimation, aesthetic or "smile" scoring, learned models inside the
pipeline. Labels may describe a gesture; the pipeline may never compute it.

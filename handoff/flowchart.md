# Pipeline flowchart

```mermaid
flowchart TD
    A["CLI: input .mov / .mp4 / .m4v / .avi / .mkv"] --> B["SHA-256 + ffprobe metadata"]
    B --> C{"Valid input?"}
    C -- "no" --> E["Structured error JSON + non-zero exit"]
    C -- "yes" --> D["Sequential sampling at analysis_fps"]
    D --> F["Per-frame DSP metrics<br/>Laplacian, Tenengrad, edges, clips,<br/>entropy, local contrast, saturation,<br/>colorfulness, cast, histogram,<br/>motion thumbnail"]
    F --> G["Frame-to-frame distances<br/>histogram + gradient + edge<br/>+ phase-correlation translation"]
    G --> H["Robust threshold<br/>median + 3 x 1.4826 x MAD<br/>(relative-max fallback)"]
    H --> I["Local maxima + minimum gap"]
    I --> J["Candidate boundaries"]
    J --> K["Build shots<br/>merge short / split long<br/>merge near-identical neighbours"]
    K --> L["Aggregate shot metrics<br/>median spatial, mean clipping<br/>+ translation coherence, jitter, pan"]
    L --> M["Normalize per component<br/>p5-p95 per video, absolute fallback<br/>(recorded reason)"]
    M --> N["8 dimension scores<br/>sharpness, exposure, contrast, stability,<br/>motion, color, texture, duration"]
    N --> O{"Hard gates"}
    O -- "fail" --> P["rejected_gate<br/>gate, value, threshold, interpretation"]
    O -- "pass" --> Q{"Quality floor"}
    Q -- "fail" --> R["rejected_floor"]
    Q -- "pass" --> S["MMR selection over<br/>Bhattacharyya similarity"]
    S --> T["Top-N selected"]
    S --> U["passing_unselected<br/>(never treated as rejected)"]
    S --> V["displaced_by_diversity"]
    T --> W["Representative PNGs"]
    J --> X["Boundary montage strips"]
    T --> Y["audit.json + ui.json<br/>samples.csv.gz + shots.csv"]
    P --> Y
    R --> Y
    U --> Y
    V --> Y
    W --> Y
    X --> Y
    Y --> Z["app/ui.py<br/>re-rank from ui.json<br/>rebuild from samples.csv.gz<br/>write labels.json"]
    Z --> AA["evaluation.json<br/>precision / recall / NDCG<br/>gate false rejects"]
```

## Stage notes

| Stage | Deterministic? | Evidence saved |
|---|---|---|
| Metadata + hash | yes | source block, SHA-256, container, codec, rotation |
| Sampling | yes | sample count, analysis resolution |
| Per-frame metrics | yes | shot-level aggregates, frame distances |
| Boundary detection | yes | median, dispersion, source, threshold, peaks |
| Shot merge | yes | boundary positions, merge similarity, shots before/after |
| Aggregation | yes | raw shot metrics, aggregation strategy, stability source |
| Normalization | yes | per component: raw variable, unit, transform, bounds, source, fallback reason |
| Scoring | yes | 8 dimension scores, component scores, effective weights |
| Gating | yes | failed gate, value, threshold, interpretation |
| Quality floor | yes | enabled flag, minimum score, resulting status |
| MMR selection | yes | rank, objective, similarity to already selected, displaced shots |
| Export | yes (except timestamp) | JSON, CSV, PNG and montage paths |
| Client re-rank | yes | config export reproduces the CLI ranking |
| Evaluation | yes | metrics, gate diagnostics, dimension separation, pairwise accuracy |

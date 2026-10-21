# Clarifications — MOV Shot Technical MVP

These are the ambiguities resolved before implementation. They are binding for the MVP.

## C1. Decoder choice and failure behavior

**Question:** Is OpenCV acceptable for decoding `.mov` in the MVP?

**Resolution:** Yes, OpenCV is allowed as the MVP decoder, with mandatory warnings in the
output JSON. If decoding fails hard, the CLI aborts with a structured error document and a
concrete ffmpeg conversion suggestion. PyAV is deferred.

## C2. Representative frame format

**Question:** Are representative frame images mandatory, and in what format?

**Resolution:** Mandatory. Each selected shot exports one full-resolution PNG at its sharpest
sampled timestamp. The image path is recorded in the shot record. No clip export in the MVP.

## C3. Per-frame data

**Question:** Should a per-frame CSV be produced?

**Resolution:** Deferred. The MVP writes shot-level metrics plus frame-to-frame distances in
the JSON. A per-frame CSV is listed in `handoff/next_iterations.md`.

## C4. Threshold calibration status

**Question:** Are the DSP thresholds calibrated?

**Resolution:** No. All thresholds are illustrative and labeled
`calibration = "initial_uncalibrated"` in config, summary, and warnings. Ranges were lightly
tuned on one 4K iPhone sample at the default 1280-pixel analysis resolution and still require
a broader corpus.

## C5. Variable frame rate

**Question:** Should VFR files be normalized?

**Resolution:** Detect and warn only. When `r_frame_rate != avg_frame_rate`, the JSON records
a `variable_frame_rate_detected` warning. No PTS remapping or frame duplication in the MVP.

## C6. Analysis resolution (added during implementation)

**Question:** Native 4K analysis is slow; may the pipeline measure at a reduced resolution?

**Resolution:** Yes, with conditions. The default analysis resize caps the longest edge at
1280 pixels using area interpolation. This is a documented measurement-resolution choice, not
enhancement. It is recorded in `analysis_resolution` and in warnings, and can be disabled with
`--analysis-max-dimension 0` (native). Normalization ranges are tied to this analysis
resolution and must be recalibrated if it changes.

# Skill: dsp-quality

Reusable guardrails for the classical DSP pipeline. Apply whenever touching
`src/video_dsp/` or the spec/plan.

## When to use

- Implementing or reviewing frame features, shot detection, aggregation, or scoring.
- Reviewing the JSON output for auditability.

## Rules

1. **Never enhance before measuring.** No sharpening, denoising, debanding, tone mapping,
   or upscaling before metrics are computed. If a transform is unavoidable, record it.
2. **Measure on luminance.** Convert to a float luminance plane (BT.601 weights) in `[0, 1]`
   before computing sharpness, exposure, contrast, and histogram metrics.
3. **Use robust aggregation.** Median for spatial metrics, mean for clipping / edge density.
   Record which strategy was used per metric.
4. **Expose explicit gates.** Every gate must report the metric value, the threshold, and a
   human-readable interpretation.
5. **Always emit the audit JSON.** Raw metrics, normalized metrics, ranges, weights, config
   hash, source metadata, and file hash are mandatory.
6. **No silent fallbacks.** Any degradation (seek failure, unsupported codec, VFR, rotation)
   becomes a warning in the output.
7. **Keep it deterministic.** No randomness, no time-dependent thresholds, no hidden models.

## Checklist before marking a DSP task done

- [ ] Pure functions have unit tests.
- [ ] No enhancement is applied to the measured frame.
- [ ] Metrics are computed on luminance.
- [ ] Aggregation strategy is explicit and recorded.
- [ ] Output JSON contains raw + normalized metrics, gates, warnings, config hash.
- [ ] `pytest -q` and `ruff check .` pass.

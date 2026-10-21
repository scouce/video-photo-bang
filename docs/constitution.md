# Constitution — MOV Shot Technical MVP

Non-negotiable principles. Every spec, plan, task, and line of code must comply.
If a requirement conflicts with this document, the constitution wins.

1. **Auditability first.** Every score must expose raw metrics, the normalization method,
   the ranges and thresholds used, the gates applied, and the config hash. Any decision must
   be reconstructible from the output JSON alone.
2. **Deterministic core.** Same input + same config + same library versions must produce the
   same selection, except for the generation timestamp. No randomness, no wall-clock-dependent
   thresholds, no hidden model inference.
3. **DSP only in MVP.** No semantic AI, no face scoring, no narrative or aesthetic scoring in
   the core pipeline. The MVP is a *technical draft selector*, never a final editorial choice.
4. **No hidden enhancement.** Do not apply sharpening, denoising, tone mapping, upscaling, or
   any other transform before measurement unless it is explicitly documented and recorded.
5. **Robust aggregation.** Use median / percentilees for spatial metrics and avoid naive means
   when outliers are expected. Aggregation strategy must be recorded in the output.
6. **Safe failure.** Invalid files, unsupported codecs, missing streams, or decoding errors must
   produce structured errors and a JSON error document, never an unhandled crash or a silent
   wrong result.

## Interpretation label

The MVP output must always carry:

```json
"interpretation": "technical_dsp_draft_only"
```

and must never claim `"final_editorial_choice"`.

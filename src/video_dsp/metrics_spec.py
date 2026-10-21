"""Declarative field catalog: metrics, dimensions, components, units and transforms.

Every number that reaches the UI or the audit JSON must be traceable to an entry in
this module. The keys are English and stable (they are part of the JSON contract);
the human-facing labels are Spanish.

Design rules:

* A *metric* is a raw scalar measured per shot (aggregated from samples).
* A *component* maps one metric onto ``[0, 1]`` through a declared ``mode`` and
  ``transform``. Components that are non-monotonic use a target band.
* A *dimension* is a weighted blend of components and is the unit that the user
  weights in the preference controls.
* Nothing here reads a file or depends on config; the absolute ranges live in
  ``config["ranges"]`` and are referenced through ``range_key``.
"""

from __future__ import annotations

from typing import Any

DIMENSION_ORDER: tuple[str, ...] = (
    "sharpness",
    "exposure",
    "contrast",
    "stability",
    "motion",
    "color",
    "texture",
    "duration",
)

ANALYSIS = "resolution de analysis"


def _percentile_metric(label: str, description: str) -> dict[str, Any]:
    """Build a luminance-percentile field entry (seven of them share this shape)."""
    return {
        "label_es": label,
        "unit_es": "luminance [0,1]",
        "description_es": description,
        "aggregation": "median",
        "measured_on": ANALYSIS,
    }


FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "variance_laplacian": {
        "label_es": "Variance of the Laplacian",
        "unit_es": "var(Laplaciano), scale 0-255 del shot Y",
        "description_es": (
            "High-frequency energy. Classic sharpness proxy; "
            "sube con el fine detail."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "tenengrad": {
        "label_es": "Tenengrad",
        "unit_es": "mean(∇²), scale 0-255",
        "description_es": (
            "Mean squared Sobel gradient magnitude. Second focus proxy."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "edge_density": {
        "label_es": "Densidad de edges",
        "unit_es": "fraction of pixels [0,1]",
        "description_es": (
            "Proportion of pixels marked by Canny. Detects empty or "
            "texturedos."
        ),
        "aggregation": "mean",
        "measured_on": ANALYSIS,
    },
    "mean": {
        "label_es": "Mean luminance",
        "unit_es": "luminance [0,1]",
        "description_es": (
            "Median luminance of shot Y. Used for the deviation from mid-grey.",
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "std": {
        "label_es": "Luminance deviation",
        "unit_es": "luminance [0,1]",
        "description_es": (
            "Contrast global del shot. Bajo = shot lavado; alto = contrast duro."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "p01": _percentile_metric("Percentile 1", "Deep shadow."),
    "p05": _percentile_metric("Percentil 5", "Sombra."),
    "p25": _percentile_metric("Percentil 25", "Cuarto inferior."),
    "p50": _percentile_metric("Percentile 50", "Median."),
    "p75": _percentile_metric("Percentil 75", "Cuarto superior."),
    "p95": _percentile_metric("Percentil 95", "Alta light."),
    "p99": _percentile_metric("Percentil 99", "Alta light extrema."),
    "black_clip": {
        "label_es": "Recorte de blacks",
        "unit_es": "fraction of pixels [0,1]",
        "description_es": (
            "Pixels below ``clip_low``. Unrecoverable clipping."
        ),
        "aggregation": "mean",
        "measured_on": ANALYSIS,
    },
    "white_clip": {
        "label_es": "Recorte de whites",
        "unit_es": "fraction of pixels [0,1]",
        "description_es": (
            "Pixels above ``clip_high``. Unrecoverable clipping."
        ),
        "aggregation": "mean",
        "measured_on": ANALYSIS,
    },
    "entropy": {
        "label_es": "Histogram entropy",
        "unit_es": "bits normalizados [0,1]",
        "description_es": (
            "Riqueza tonal. Bajo = shot shot o clipped; alto = distribution amplia."
        ),
        "aggregation": "median",
        "measured_on": "histograma de 64 bins",
    },
    "local_contrast": {
        "label_es": "Contrast local",
        "unit_es": "std de luminance por bloque 8x8 [0,1]",
        "description_es": (
            "Microcontrast texturel. Distingue detail real de una imagen suave."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "saturation_mean": {
        "label_es": "Mean saturation",
        "unit_es": "saturation HSV [0,1]",
        "description_es": (
            "Mean chroma. Neither grey nor neon; scored against a target band."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "saturation_std": {
        "label_es": "Saturation dispersion",
        "unit_es": "saturation HSV [0,1]",
        "description_es": "Variedad de color dentro del shot.",
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "colorfulness": {
        "label_es": "Colorfulness (Hasler-Süsstrunk)",
        "unit_es": "normalised index, typically 0.0-0.5",
        "description_es": (
            "Combination of variance and mean of the red-green and yellow-blue axes."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "channel_cast": {
        "label_es": "Dominante de canal",
        "unit_es": "diferencia maximum entre means de canal [0,1]",
        "description_es": (
            "Desbalance de color global. Alto = dominante fuerte o balance malo."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "instability": {
        "label_es": "Instability interna",
        "unit_es": "distancia combinada mean por par de samples",
        "description_es": (
            "Cambio interno del shot: motion, parpadeo o noise de exposure."
        ),
        "aggregation": "mean of pairwise distances",
        "measured_on": "samples a analysis_fps",
    },
    "motion_per_second": {
        "label_es": "Cambio por segundo",
        "unit_es": "distancia combinada / s",
        "description_es": (
            "Ritmo de cambio visual. Escala con ``analysis_fps`` para ser comparable."
        ),
        "aggregation": "mean of pairwise distances / dt",
        "measured_on": "samples a analysis_fps",
    },
    "translation_consistency": {
        "label_es": "Coherencia de translation",
        "unit_es": "coherence vectorial [0,1]",
        "description_es": (
            "1 = motion in a single direction (clean pan); "
            "0 = random direction (unstable tripod)."
        ),
        "aggregation": "vector coherence |sum(v)| / sum(|v|)",
        "measured_on": "thumbnail de motion, lado mayor 96 px",
    },
    "jitter_px": {
        "label_es": "Jitter",
        "unit_es": "px por par de samples",
        "description_es": (
            "Deviation of translation acceleration. Proxy for hand shake."
        ),
        "aggregation": "std of translation deltas",
        "measured_on": "thumbnail de motion, lado mayor 96 px",
    },
    "pan_speed_px_s": {
        "label_es": "Velocidad de pan",
        "unit_es": "px/s en el thumbnail de motion",
        "description_es": "Mediana de la magnitud de translation por segundo.",
        "aggregation": "median magnitude / dt",
        "measured_on": "thumbnail de motion, lado mayor 96 px",
    },
    "phase_response": {
        "label_es": "Confianza de fase",
        "unit_es": "respuesta de phaseCorrelate [0,1]",
        "description_es": (
            "Reliability of the translation estimate. Low on shots without texture."
        ),
        "aggregation": "median",
        "measured_on": "thumbnail de motion",
    },
    "duration_seconds": {
        "label_es": "Duration del shot",
        "unit_es": "segundos",
        "description_es": (
            "Duration measured between the first and last sample of the shot."
        ),
        "aggregation": "end - start",
        "measured_on": "timestamps de sample",
    },
    "clip_total": {
        "label_es": "Recorte total",
        "unit_es": "fraction of pixels [0,1]",
        "description_es": "``black_clip + white_clip``, acotado a 1.",
        "aggregation": "derived",
        "measured_on": ANALYSIS,
    },
    "midtone_dev": {
        "label_es": "Midtone deviation",
        "unit_es": "[0,1], 0 = centrado en 0.5",
        "description_es": (
            "``2 * |mean - 0.5|``. Penaliza shots subexpuestos o pasados de light."
        ),
        "aggregation": "derived",
        "measured_on": ANALYSIS,
    },
    "dynamic_range": {
        "label_es": "Useful dynamic range",
        "unit_es": "luminance [0,1]",
        "description_es": (
            "``p95 - p05``. Contrast sin contaminar por outliers extremos."
        ),
        "aggregation": "derived",
        "measured_on": ANALYSIS,
    },
}

DIMENSIONS: dict[str, dict[str, Any]] = {
    "sharpness": {
        "label_es": "Sharpness",
        "description_es": (
            "Real focus: high-frequency energy measured on the Y plane."
        ),
        "components": [
            {
                "id": "vol",
                "metric": "variance_laplacian",
                "weight": 0.5,
                "mode": "higher_better",
                "transform": "log1p",
                "range_key": "variance_laplacian",
            },
            {
                "id": "ten",
                "metric": "tenengrad",
                "weight": 0.5,
                "mode": "higher_better",
                "transform": "log1p",
                "range_key": "tenengrad",
            },
        ],
        "fallback_components": [],
    },
    "exposure": {
        "label_es": "Exposure",
        "description_es": (
            "Recorte irrecuperable y centrado del tono medio. "
            "Absolute formula, not percentile."
        ),
        "components": [
            {
                "id": "clip",
                "metric": "clip_total",
                "weight": 0.5,
                "mode": "lower_better",
                "transform": "identity",
                "range_key": "clip_total",
                "force_absolute": True,
            },
            {
                "id": "midtone",
                "metric": "midtone_dev",
                "weight": 0.5,
                "mode": "lower_better",
                "transform": "identity",
                "range_key": "midtone_dev",
                "force_absolute": True,
            },
        ],
        "fallback_components": [],
    },
    "contrast": {
        "label_es": "Contrast",
        "description_es": (
            "Global deviation and useful range. Avoids washed-out or harsh shots without detail."
        ),
        "components": [
            {
                "id": "std",
                "metric": "std",
                "weight": 0.7,
                "mode": "higher_better",
                "transform": "identity",
                "range_key": "luminance_std",
            },
            {
                "id": "range",
                "metric": "dynamic_range",
                "weight": 0.3,
                "mode": "higher_better",
                "transform": "identity",
                "range_key": "dynamic_range",
            },
        ],
        "fallback_components": [],
    },
    "stability": {
        "label_es": "Stability",
        "description_es": (
            "Paneo limpio frente a shake. Usa translation de fase; si no es fiable, "
            "cae a instability y lo registra."
        ),
        "components": [
            {
                "id": "coherence",
                "metric": "translation_consistency",
                "weight": 0.6,
                "mode": "higher_better",
                "transform": "identity",
                "range_key": "translation_consistency",
            },
            {
                "id": "jitter",
                "metric": "jitter_px",
                "weight": 0.4,
                "mode": "lower_better",
                "transform": "identity",
                "range_key": "jitter_px",
            },
        ],
        "fallback_components": [
            {
                "id": "instability",
                "metric": "instability",
                "weight": 1.0,
                "mode": "lower_better",
                "transform": "identity",
                "range_key": "instability",
            },
        ],
    },
    "motion": {
        "label_es": "Motion",
        "description_es": (
            "Cantidad de motion contra una banda objetivo: "
            "ni shot muerto ni caos."
        ),
        "components": [
            {
                "id": "pan",
                "metric": "pan_speed_px_s",
                "weight": 0.5,
                "mode": "band",
                "transform": "identity",
                "band_key": "pan_speed_px_s",
            },
            {
                "id": "change",
                "metric": "motion_per_second",
                "weight": 0.5,
                "mode": "band",
                "transform": "identity",
                "band_key": "motion_per_second",
            },
        ],
        "fallback_components": [],
    },
    "color": {
        "label_es": "Color",
        "description_es": (
            "Riqueza de croma, saturation razonable y ausencia de dominante."
        ),
        "components": [
            {
                "id": "colorfulness",
                "metric": "colorfulness",
                "weight": 0.45,
                "mode": "higher_better",
                "transform": "identity",
                "range_key": "colorfulness",
            },
            {
                "id": "saturation",
                "metric": "saturation_mean",
                "weight": 0.35,
                "mode": "band",
                "transform": "identity",
                "band_key": "saturation_mean",
            },
            {
                "id": "cast",
                "metric": "channel_cast",
                "weight": 0.20,
                "mode": "lower_better",
                "transform": "identity",
                "range_key": "channel_cast",
            },
        ],
        "fallback_components": [],
    },
    "texture": {
        "label_es": "Texture",
        "description_es": (
            "Tonal richness and micro-contrast. Rewards images with information, "
            "no empty shots."
        ),
        "components": [
            {
                "id": "entropy",
                "metric": "entropy",
                "weight": 0.5,
                "mode": "higher_better",
                "transform": "identity",
                "range_key": "entropy",
            },
            {
                "id": "local",
                "metric": "local_contrast",
                "weight": 0.5,
                "mode": "higher_better",
                "transform": "identity",
                "range_key": "local_contrast",
            },
        ],
        "fallback_components": [],
    },
    "duration": {
        "label_es": "Duration",
        "description_es": (
            "Duration del shot contra una banda objetivo del preset."
        ),
        "components": [
            {
                "id": "duration",
                "metric": "duration_seconds",
                "weight": 1.0,
                "mode": "band",
                "transform": "identity",
                "band_key": "duration_seconds",
            },
        ],
        "fallback_components": [],
    },
}


def dimension_components(dimension: str, fallback: bool = False) -> list[dict[str, Any]]:
    """Return the component list for a dimension, optionally its fallback list."""
    key = "fallback_components" if fallback else "components"
    return list(DIMENSIONS[dimension][key])


def metric_label(metric: str) -> str:
    return FIELD_CATALOG.get(metric, {}).get("label_es", metric)


def field_catalog() -> dict[str, dict[str, Any]]:
    """Return a shallow copy suitable for embedding in the UI document."""
    return {key: dict(value) for key, value in FIELD_CATALOG.items()}


def dimension_catalog() -> dict[str, dict[str, Any]]:
    """Return the dimension definitions, components included, for the UI document."""
    return {
        key: {
            "label_es": value["label_es"],
            "description_es": value["description_es"],
            "components": [dict(component) for component in value["components"]],
            "fallback_components": [
                dict(component) for component in value["fallback_components"]
            ],
        }
        for key, value in DIMENSIONS.items()
    }

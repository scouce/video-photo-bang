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

ANALYSIS = "resolución de análisis"


def _percentile_metric(label: str, description: str) -> dict[str, Any]:
    """Build a luminance-percentile field entry (seven of them share this shape)."""
    return {
        "label_es": label,
        "unit_es": "luminancia [0,1]",
        "description_es": description,
        "aggregation": "median",
        "measured_on": ANALYSIS,
    }


FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "variance_laplacian": {
        "label_es": "Varianza del Laplaciano",
        "unit_es": "var(Laplaciano), escala 0-255 del plano Y",
        "description_es": (
            "Energía de alta frecuencia. Proxy clásico de nitidez; "
            "sube con el detalle fino."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "tenengrad": {
        "label_es": "Tenengrad",
        "unit_es": "media(∇²), escala 0-255",
        "description_es": (
            "Magnitud media del gradiente de Sobel al cuadrado. Segundo proxy de foco."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "edge_density": {
        "label_es": "Densidad de bordes",
        "unit_es": "fracción de píxeles [0,1]",
        "description_es": (
            "Proporción de píxeles marcados por Canny. Detecta planos vacíos o "
            "texturados."
        ),
        "aggregation": "mean",
        "measured_on": ANALYSIS,
    },
    "mean": {
        "label_es": "Luminancia media",
        "unit_es": "luminancia [0,1]",
        "description_es": (
            "Media del plano Y. Se usa para el desvío respecto del gris medio."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "std": {
        "label_es": "Desvío de luminancia",
        "unit_es": "luminancia [0,1]",
        "description_es": (
            "Contraste global del plano. Bajo = plano lavado; alto = contraste duro."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "p01": _percentile_metric("Percentil 1", "Sombra profunda."),
    "p05": _percentile_metric("Percentil 5", "Sombra."),
    "p25": _percentile_metric("Percentil 25", "Cuarto inferior."),
    "p50": _percentile_metric("Percentil 50", "Mediana."),
    "p75": _percentile_metric("Percentil 75", "Cuarto superior."),
    "p95": _percentile_metric("Percentil 95", "Alta luz."),
    "p99": _percentile_metric("Percentil 99", "Alta luz extrema."),
    "black_clip": {
        "label_es": "Recorte de negros",
        "unit_es": "fracción de píxeles [0,1]",
        "description_es": (
            "Píxeles por debajo de ``clip_low``. Recorte irrecuperable."
        ),
        "aggregation": "mean",
        "measured_on": ANALYSIS,
    },
    "white_clip": {
        "label_es": "Recorte de blancos",
        "unit_es": "fracción de píxeles [0,1]",
        "description_es": (
            "Píxeles por encima de ``clip_high``. Recorte irrecuperable."
        ),
        "aggregation": "mean",
        "measured_on": ANALYSIS,
    },
    "entropy": {
        "label_es": "Entropía del histograma",
        "unit_es": "bits normalizados [0,1]",
        "description_es": (
            "Riqueza tonal. Bajo = plano plano o quemado; alto = distribución amplia."
        ),
        "aggregation": "median",
        "measured_on": "histograma de 64 bins",
    },
    "local_contrast": {
        "label_es": "Contraste local",
        "unit_es": "std de luminancia por bloque 8x8 [0,1]",
        "description_es": (
            "Microcontraste textural. Distingue detalle real de una imagen suave."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "saturation_mean": {
        "label_es": "Saturación media",
        "unit_es": "saturación HSV [0,1]",
        "description_es": (
            "Croma medio. Ni gris ni neón; se puntúa contra una banda objetivo."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "saturation_std": {
        "label_es": "Dispersión de saturación",
        "unit_es": "saturación HSV [0,1]",
        "description_es": "Variedad de color dentro del plano.",
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "colorfulness": {
        "label_es": "Colorfulness (Hasler-Süsstrunk)",
        "unit_es": "índice normalizado, típico 0.0-0.5",
        "description_es": (
            "Combinación de varianza y media de los ejes rojo-verde y amarillo-azul."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "channel_cast": {
        "label_es": "Dominante de canal",
        "unit_es": "diferencia máxima entre medias de canal [0,1]",
        "description_es": (
            "Desbalance de color global. Alto = dominante fuerte o balance malo."
        ),
        "aggregation": "median",
        "measured_on": ANALYSIS,
    },
    "instability": {
        "label_es": "Inestabilidad interna",
        "unit_es": "distancia combinada media por par de muestras",
        "description_es": (
            "Cambio interno del plano: movimiento, parpadeo o ruido de exposición."
        ),
        "aggregation": "mean of pairwise distances",
        "measured_on": "muestras a analysis_fps",
    },
    "motion_per_second": {
        "label_es": "Cambio por segundo",
        "unit_es": "distancia combinada / s",
        "description_es": (
            "Ritmo de cambio visual. Escala con ``analysis_fps`` para ser comparable."
        ),
        "aggregation": "mean of pairwise distances / dt",
        "measured_on": "muestras a analysis_fps",
    },
    "translation_consistency": {
        "label_es": "Coherencia de traslación",
        "unit_es": "coherencia vectorial [0,1]",
        "description_es": (
            "1 = movimiento en una sola dirección (paneo limpio); "
            "0 = dirección aleatoria (trípode inestable)."
        ),
        "aggregation": "vector coherence |sum(v)| / sum(|v|)",
        "measured_on": "thumbnail de movimiento, lado mayor 96 px",
    },
    "jitter_px": {
        "label_es": "Jitter",
        "unit_es": "px por par de muestras",
        "description_es": (
            "Desvío de la aceleración de traslación. Proxy de temblor de mano."
        ),
        "aggregation": "std of translation deltas",
        "measured_on": "thumbnail de movimiento, lado mayor 96 px",
    },
    "pan_speed_px_s": {
        "label_es": "Velocidad de paneo",
        "unit_es": "px/s en el thumbnail de movimiento",
        "description_es": "Mediana de la magnitud de traslación por segundo.",
        "aggregation": "median magnitude / dt",
        "measured_on": "thumbnail de movimiento, lado mayor 96 px",
    },
    "phase_response": {
        "label_es": "Confianza de fase",
        "unit_es": "respuesta de phaseCorrelate [0,1]",
        "description_es": (
            "Fiabilidad de la estimación de traslación. Baja en planos sin textura."
        ),
        "aggregation": "median",
        "measured_on": "thumbnail de movimiento",
    },
    "duration_seconds": {
        "label_es": "Duración del plano",
        "unit_es": "segundos",
        "description_es": (
            "Duración medida entre la primera y la última muestra del plano."
        ),
        "aggregation": "end - start",
        "measured_on": "timestamps de muestra",
    },
    "clip_total": {
        "label_es": "Recorte total",
        "unit_es": "fracción de píxeles [0,1]",
        "description_es": "``black_clip + white_clip``, acotado a 1.",
        "aggregation": "derived",
        "measured_on": ANALYSIS,
    },
    "midtone_dev": {
        "label_es": "Desvío de tono medio",
        "unit_es": "[0,1], 0 = centrado en 0.5",
        "description_es": (
            "``2 * |mean - 0.5|``. Penaliza planos subexpuestos o pasados de luz."
        ),
        "aggregation": "derived",
        "measured_on": ANALYSIS,
    },
    "dynamic_range": {
        "label_es": "Rango dinámico útil",
        "unit_es": "luminancia [0,1]",
        "description_es": (
            "``p95 - p05``. Contraste sin contaminar por outliers extremos."
        ),
        "aggregation": "derived",
        "measured_on": ANALYSIS,
    },
}

DIMENSIONS: dict[str, dict[str, Any]] = {
    "sharpness": {
        "label_es": "Nitidez",
        "description_es": (
            "Foco real: energía de alta frecuencia medida sobre el plano Y."
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
        "label_es": "Exposición",
        "description_es": (
            "Recorte irrecuperable y centrado del tono medio. "
            "Fórmula absoluta, no percentil."
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
        "label_es": "Contraste",
        "description_es": (
            "Desvío global y rango útil. Evita planos lavados o duros sin matices."
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
        "label_es": "Estabilidad",
        "description_es": (
            "Paneo limpio frente a temblor. Usa traslación de fase; si no es fiable, "
            "cae a inestabilidad y lo registra."
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
        "label_es": "Movimiento",
        "description_es": (
            "Cantidad de movimiento contra una banda objetivo: "
            "ni plano muerto ni caos."
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
            "Riqueza de croma, saturación razonable y ausencia de dominante."
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
        "label_es": "Textura",
        "description_es": (
            "Riqueza tonal y microcontraste. Premia imágenes con información, "
            "no planos vacíos."
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
        "label_es": "Duración",
        "description_es": (
            "Duración del plano contra una banda objetivo del preset."
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

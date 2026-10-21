"""Preference presets.

A preset is a named bundle of dimension weights, target bands and a normalization
method. Presets are data, never code: they are serialized into every output document
so a selection can always be explained by the preset that produced it.

All presets are ``initial_uncalibrated`` except ``balanced_v1``, which reproduces the
v0.1.0 absolute-range formula exactly and is kept only for reproducibility.
"""

from __future__ import annotations

from typing import Any

from .metrics_spec import DIMENSIONS


def _weights(**values: float) -> dict[str, float]:
    """Build a full 8-dimension weight dict, defaulting missing dims to 0."""
    weights = {dimension: float(values.get(dimension, 0.0)) for dimension in DIMENSIONS}
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("preset weights must sum to a positive number")
    return {key: value / total for key, value in weights.items()}


PRESETS: dict[str, dict[str, Any]] = {
    "balanced_v1": {
        "label_es": "Equilibrado v1 (legado 0.1.0)",
        "description_es": (
            "Fórmula original de 4 dimensiones con rangos absolutos. Reproduce el ranking "
            "del MVP 0.1.0; se conserva solo para comparar y auditar."
        ),
        "calibration": "legacy_v0_1_0",
        "normalization_method": "absolute",
        "weights": _weights(sharpness=0.40, exposure=0.25, contrast=0.20, stability=0.15),
        "targets": {
            "duration_seconds": {"low": 0.5, "high": 15.0, "falloff": 1.0},
            "motion_per_second": {"low": 0.0, "high": 10.0, "falloff": 5.0},
            "pan_speed_px_s": {"low": 0.0, "high": 1000.0, "falloff": 500.0},
            "saturation_mean": {"low": 0.0, "high": 1.0, "falloff": 0.2},
        },
        "quality_floor": {"enabled": False, "min_total_score": 0.0},
    },
    "balanced_v2": {
        "label_es": "Equilibrado v2 (por defecto)",
        "description_es": (
            "Ocho dimensiones con normalización por vídeo. Premia nitidez y exposición, "
            "pero exige movimiento razonable, color y textura, y castiga duraciones extremas."
        ),
        "calibration": "initial_uncalibrated",
        "normalization_method": "per_video_percentile",
        "weights": _weights(
            sharpness=0.28,
            exposure=0.18,
            contrast=0.12,
            stability=0.16,
            motion=0.10,
            color=0.06,
            texture=0.05,
            duration=0.05,
        ),
        "targets": {
            "duration_seconds": {"low": 3.0, "high": 8.0, "falloff": 1.5},
            "motion_per_second": {"low": 0.04, "high": 0.45, "falloff": 0.20},
            "pan_speed_px_s": {"low": 0.5, "high": 40.0, "falloff": 20.0},
            "saturation_mean": {"low": 0.15, "high": 0.65, "falloff": 0.15},
        },
        "quality_floor": {"enabled": True, "min_total_score": 0.25},
    },
    "portrait": {
        "label_es": "Retrato / persona",
        "description_es": (
            "Prioriza piel bien expuesta y tono de color sobre movimiento y duración. "
            "Exige estabilidad y una nitidez mínima más alta."
        ),
        "calibration": "initial_uncalibrated",
        "normalization_method": "per_video_percentile",
        "weights": _weights(
            sharpness=0.28,
            exposure=0.22,
            contrast=0.06,
            stability=0.16,
            motion=0.04,
            color=0.14,
            texture=0.02,
            duration=0.08,
        ),
        "targets": {
            "duration_seconds": {"low": 2.0, "high": 5.0, "falloff": 1.2},
            "motion_per_second": {"low": 0.01, "high": 0.20, "falloff": 0.12},
            "pan_speed_px_s": {"low": 0.0, "high": 25.0, "falloff": 15.0},
            "saturation_mean": {"low": 0.25, "high": 0.65, "falloff": 0.10},
        },
        "hard_gates": {"min_sharpness_score": 0.20, "max_jitter_px": 3.0},
        "quality_floor": {"enabled": True, "min_total_score": 0.28},
    },
    "action": {
        "label_es": "Acción / movimiento",
        "description_es": (
            "Premia movimiento y tolera más inestabilidad y jitter: el gesto importa más "
            "que el pulso. Bandas de movimiento y paneo altas."
        ),
        "calibration": "initial_uncalibrated",
        "normalization_method": "per_video_percentile",
        "weights": _weights(
            sharpness=0.18,
            exposure=0.12,
            contrast=0.10,
            stability=0.10,
            motion=0.30,
            color=0.06,
            texture=0.08,
            duration=0.06,
        ),
        "targets": {
            "duration_seconds": {"low": 1.5, "high": 5.0, "falloff": 1.0},
            "motion_per_second": {"low": 0.20, "high": 1.20, "falloff": 0.40},
            "pan_speed_px_s": {"low": 15.0, "high": 120.0, "falloff": 40.0},
            "saturation_mean": {"low": 0.15, "high": 0.70, "falloff": 0.15},
        },
        "hard_gates": {"max_instability": 0.55, "max_jitter_px": 8.0},
        "quality_floor": {"enabled": True, "min_total_score": 0.22},
    },
    "landscape": {
        "label_es": "Paisaje / escena",
        "description_es": (
            "Textura, contraste y color por encima de movimiento. Planos más largos y "
            "nitidez mínima más exigente."
        ),
        "calibration": "initial_uncalibrated",
        "normalization_method": "per_video_percentile",
        "weights": _weights(
            sharpness=0.20,
            exposure=0.12,
            contrast=0.18,
            stability=0.10,
            motion=0.03,
            color=0.14,
            texture=0.20,
            duration=0.03,
        ),
        "targets": {
            "duration_seconds": {"low": 5.0, "high": 12.0, "falloff": 3.0},
            "motion_per_second": {"low": 0.02, "high": 0.25, "falloff": 0.15},
            "pan_speed_px_s": {"low": 0.0, "high": 30.0, "falloff": 15.0},
            "saturation_mean": {"low": 0.18, "high": 0.70, "falloff": 0.15},
        },
        "hard_gates": {"min_sharpness_score": 0.25},
        "quality_floor": {"enabled": True, "min_total_score": 0.25},
    },
    "low_light": {
        "label_es": "Baja luz / nocturno",
        "description_es": (
            "Planos largos y quietos, como una exposición nocturna: premia estabilidad y "
            "nitidez, acepta negros profundos y no premia el color vivo."
        ),
        "calibration": "initial_uncalibrated",
        "normalization_method": "per_video_percentile",
        "weights": _weights(
            sharpness=0.18,
            exposure=0.30,
            contrast=0.08,
            stability=0.22,
            motion=0.06,
            color=0.08,
            texture=0.02,
            duration=0.06,
        ),
        "targets": {
            "duration_seconds": {"low": 3.0, "high": 12.0, "falloff": 5.0},
            "motion_per_second": {"low": 0.01, "high": 0.14, "falloff": 0.10},
            "pan_speed_px_s": {"low": 0.0, "high": 20.0, "falloff": 12.0},
            "saturation_mean": {"low": 0.10, "high": 0.30, "falloff": 0.08},
        },
        "hard_gates": {
            "max_black_clip": 0.35,
            "max_white_clip": 0.02,
            "max_jitter_px": 2.0,
        },
        "quality_floor": {"enabled": True, "min_total_score": 0.24},
    },
    "shorts": {
        "label_es": "Clips cortos / redes",
        "description_es": (
            "Banda de duración corta (1-4 s) y movimiento ágil; los planos largos se "
            "rechazan aunque estén bien medidos."
        ),
        "calibration": "initial_uncalibrated",
        "normalization_method": "per_video_percentile",
        "weights": _weights(
            sharpness=0.22,
            exposure=0.14,
            contrast=0.08,
            stability=0.12,
            motion=0.16,
            color=0.05,
            texture=0.05,
            duration=0.18,
        ),
        "targets": {
            "duration_seconds": {"low": 1.0, "high": 4.0, "falloff": 0.8},
            "motion_per_second": {"low": 0.08, "high": 0.70, "falloff": 0.25},
            "pan_speed_px_s": {"low": 2.0, "high": 70.0, "falloff": 30.0},
            "saturation_mean": {"low": 0.15, "high": 0.70, "falloff": 0.15},
        },
        "hard_gates": {"min_shot_duration_s": 1.0, "max_shot_duration_s": 6.0},
        "quality_floor": {"enabled": True, "min_total_score": 0.24},
    },
}

DEFAULT_PRESET = "balanced_v2"


def list_presets() -> dict[str, dict[str, Any]]:
    """Return preset metadata (no component internals) for the UI selector."""
    return {
        key: {
            "label_es": value["label_es"],
            "description_es": value["description_es"],
            "calibration": value["calibration"],
            "normalization_method": value["normalization_method"],
            "weights": dict(value["weights"]),
            "targets": {
                target: dict(band) for target, band in value["targets"].items()
            },
            "quality_floor": dict(value["quality_floor"]),
            "hard_gates": dict(value.get("hard_gates", {})),
        }
        for key, value in PRESETS.items()
    }


def get_preset(name: str) -> dict[str, Any]:
    if name not in PRESETS:
        available = ", ".join(sorted(PRESETS))
        raise KeyError(f"unknown preset {name!r}; available: {available}")
    preset = PRESETS[name]
    return {
        "name": name,
        "label_es": preset["label_es"],
        "description_es": preset["description_es"],
        "calibration": preset["calibration"],
        "normalization_method": preset["normalization_method"],
        "weights": dict(preset["weights"]),
        "targets": {key: dict(value) for key, value in preset["targets"].items()},
        "quality_floor": dict(preset["quality_floor"]),
        "hard_gates": dict(preset.get("hard_gates", {})),
    }

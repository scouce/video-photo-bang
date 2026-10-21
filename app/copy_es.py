"""Plain-language copy for the simplified view.

Everything a non-photographer reads lives here so the wording can be reviewed in one place.
The technical mode keeps using the catalogs from ``video_dsp.metrics_spec``.
"""

from __future__ import annotations

from typing import Any

# Preset name -> (short label, one-sentence explanation).
PRESET_CHOICES: dict[str, tuple[str, str]] = {
    "balanced_v2": ("Equilibrado", "Un poco de todo: nítido, bien expuesto y estable."),
    "portrait": ("Personas", "Prioriza caras y piel bien expuestas, con color natural."),
    "landscape": ("Paisajes", "Premia detalle, color y planos pausados."),
    "action": ("Acción", "Acepta movimiento si el plano sigue siendo nítido."),
    "low_light": ("Poca luz", "Pensado para escenas oscuras o interiores."),
    "shorts": ("Clips cortos", "Favorece planos breves y con energía."),
    "balanced_v1": ("Clásico (v0.1)", "Fórmula antigua, solo para comparar."),
}

# Status -> (icon, text). Never color alone.
STATUS_CHIPS: dict[str, tuple[str, str]] = {
    "selected": ("✅", "Recomendado"),
    "passing_unselected": ("⚪", "Pasa, no elegido"),
    "rejected_gate": ("⛔", "Descartado"),
    "rejected_floor": ("⛔", "Descartado"),
}

# Gate name -> plain reason.
REASON_TEXT: dict[str, str] = {
    "min_sharpness_score": "se ve borroso",
    "max_jitter_px": "tiembla demasiado",
    "max_black_clip": "está demasiado oscuro",
    "max_white_clip": "tiene zonas quemadas",
    "max_instability": "cambia mucho dentro del plano",
    "min_shot_duration": "es demasiado corto",
    "max_shot_duration": "es demasiado largo",
}

FLOOR_REASON = "no llega al mínimo de calidad"

# Dimension -> plain noun used in the "why" sentence.
DIMENSION_NOUNS: dict[str, str] = {
    "sharpness": "nitidez",
    "exposure": "exposición",
    "contrast": "contraste",
    "stability": "estabilidad",
    "motion": "movimiento",
    "color": "color",
    "texture": "detalle fino",
    "duration": "duración",
}

GLOSSARY: dict[str, str] = {
    "Plano": "Un trozo de vídeo sin cortes: desde que empieza hasta que cambia la escena.",
    "Nitidez": "Cuánto detalle se distingue. Un plano borroso puntúa bajo.",
    "Exposición": "Si la imagen está ni muy oscura ni quemada.",
    "Estabilidad": "Si la cámara se movió o tembló durante el plano.",
    "Movimiento": "Cuánto se mueve lo que sale en pantalla.",
    "Diversidad": "Evita que las fotos elegidas se parezcan demasiado entre sí.",
    "Recomendado": "Pasó todos los filtros y entró en el Top-N.",
    "Descartado": "No pasó un filtro técnico. El motivo aparece en la tarjeta.",
}


def status_chip(status: str) -> tuple[str, str]:
    return STATUS_CHIPS.get(status, ("·", status))


def discard_reason(shot: dict[str, Any]) -> str:
    """Plain-language reason for a rejected shot."""
    if shot.get("status") == "rejected_floor":
        return FLOOR_REASON
    failures = shot.get("failed_gates") or []
    if not failures:
        return "no cumple los filtros activos"
    return REASON_TEXT.get(failures[0]["gate"], "no cumple los filtros activos")


def why_sentence(shot: dict[str, Any], weights: dict[str, float]) -> str:
    """Deterministic, jargon-free explanation built from the dimension scores.

    Strength is ranked by contribution (weight × score) and leaves ``duration`` out: it is
    a fit to the target, not a merit of the frame.
    """
    scores = shot.get("dimension_scores") or {}
    if not scores:
        return "Sin datos suficientes para explicarlo."

    merit = [
        name
        for name in scores
        if name != "duration" and float(weights.get(name, 0.0)) > 0.0
    ]
    ranked = sorted(
        merit,
        key=lambda name: (
            -(float(weights.get(name, 0.0)) * float(scores[name])),
            name,
        ),
    )
    if not ranked:
        return "Sin pesos activos que expliquen la elección."

    strong = [name for name in ranked if float(scores[name]) >= 0.55][:2]
    chosen = strong or ranked[:2]
    parts = [DIMENSION_NOUNS.get(name, name) for name in chosen]
    if len(parts) == 1:
        headline = f"Destaca por su {parts[0]}."
    else:
        headline = f"Destaca por su {parts[0]} y su {parts[1]}."

    weighted = [name for name in ranked if float(weights.get(name, 0.0)) >= 0.10]
    weak = min(weighted, key=lambda name: float(scores[name])) if weighted else None
    if weak is not None and float(scores[weak]) < 0.45 and weak not in chosen:
        headline += f" Lo más flojo: {DIMENSION_NOUNS.get(weak, weak)}."
    return headline


def clock(seconds: float) -> str:
    """`78.4` -> `1:18` (minutes:seconds, no jargon)."""
    total = max(0, int(round(float(seconds))))
    return f"{total // 60}:{total % 60:02d}"


def duration_label(seconds: float) -> str:
    """`3.6` -> `3,6 s` (Spanish decimal comma)."""
    return f"{float(seconds):.1f}".replace(".", ",") + " s"

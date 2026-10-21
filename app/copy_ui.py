"""Plain-language copy for the simplified view.

Everything a non-photographer reads lives here so the wording can be reviewed in one place.
The technical mode keeps using the catalogs from ``video_dsp.metrics_spec``.
"""

from __future__ import annotations

from typing import Any

# Preset name -> (short label, one-sentence explanation).
PRESET_CHOICES: dict[str, tuple[str, str]] = {
    "balanced_v2": ("Balanced", "A bit of everything: sharp, well exposed and stable."),
    "portrait": ("People", "Prioritises faces and well-exposed skin with natural colour."),
    "landscape": ("Landscapes", "Rewards detail, colour and unhurried shots."),
    "action": ("Action", "Accepts motion as long as the shot stays sharp."),
    "low_light": ("Low light", "Tuned for dark or indoor scenes."),
    "shorts": ("Short clips", "Favours brief, energetic shots."),
    "balanced_v1": ("Classic (v0.1)", "Legacy formula, for comparison only."),
}

# Status -> (icon, text). Never colour alone.
STATUS_CHIPS: dict[str, tuple[str, str]] = {
    "selected": ("✅", "Recommended"),
    "passing_unselected": ("⚪", "Passes, not chosen"),
    "rejected_gate": ("⛔", "Discarded"),
    "rejected_floor": ("⛔", "Discarded"),
}

# Gate name -> plain reason.
REASON_TEXT: dict[str, str] = {
    "min_sharpness_score": "looks blurry",
    "max_jitter_px": "shakes too much",
    "max_black_clip": "is too dark",
    "max_white_clip": "has burnt highlights",
    "max_instability": "changes too much within the shot",
    "min_shot_duration": "is too short",
    "max_shot_duration": "is too long",
}

FLOOR_REASON = "does not reach the quality floor"

# Dimension -> plain noun used in the "why" sentence.
DIMENSION_NOUNS: dict[str, str] = {
    "sharpness": "sharpness",
    "exposure": "exposure",
    "contrast": "contrast",
    "stability": "stability",
    "motion": "motion",
    "color": "colour",
    "texture": "fine detail",
    "duration": "duration",
}

GLOSSARY: dict[str, str] = {
    "Shot": "A stretch of video with no cuts: from the start until the scene changes.",
    "Sharpness": "How much detail is visible. A blurry shot scores low.",
    "Exposure": "Whether the image is neither too dark nor burnt out.",
    "Stability": "Whether the camera moved or shook during the shot.",
    "Motion": "How much moves on screen.",
    "Diversity": "Keeps the chosen photos from looking too similar.",
    "Recommended": "Passed every filter and made the Top-N.",
    "Discarded": "Failed a technical filter. The reason is shown on the card.",
}


def status_chip(status: str) -> tuple[str, str]:
    return STATUS_CHIPS.get(status, ("·", status))


def discard_reason(shot: dict[str, Any]) -> str:
    """Plain-language reason for a rejected shot."""
    if shot.get("status") == "rejected_floor":
        return FLOOR_REASON
    failures = shot.get("failed_gates") or []
    if not failures:
        return "does not pass the active filters"
    return REASON_TEXT.get(failures[0]["gate"], "does not pass the active filters")


def why_sentence(shot: dict[str, Any], weights: dict[str, float]) -> str:
    """Deterministic, jargon-free explanation built from the dimension scores.

    Strength is ranked by contribution (weight × score) and leaves ``duration`` out: it is
    a fit to the target, not a merit of the frame.
    """
    scores = shot.get("dimension_scores") or {}
    if not scores:
        return "Not enough data to explain this one."

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
        return "No active weights explain this choice."

    strong = [name for name in ranked if float(scores[name]) >= 0.55][:2]
    chosen = strong or ranked[:2]
    parts = [DIMENSION_NOUNS.get(name, name) for name in chosen]
    if len(parts) == 1:
        headline = f"Stands out for its {parts[0]}."
    else:
        headline = f"Stands out for its {parts[0]} and its {parts[1]}."

    weighted = [name for name in ranked if float(weights.get(name, 0.0)) >= 0.10]
    weak = min(weighted, key=lambda name: float(scores[name])) if weighted else None
    if weak is not None and float(scores[weak]) < 0.45 and weak not in chosen:
        headline += f" Weakest point: {DIMENSION_NOUNS.get(weak, weak)}."
    return headline


def clock(seconds: float) -> str:
    """`78.4` -> `1:18` (minutes:seconds, no jargon)."""
    total = max(0, int(round(float(seconds))))
    return f"{total // 60}:{total % 60:02d}"


def duration_label(seconds: float) -> str:
    """`3.6` -> `3.6 s`."""
    return f"{float(seconds):.1f} s"

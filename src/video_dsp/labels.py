"""Human annotation store (level A verdicts and level B pairwise comparisons).

The file is intentionally boring: a versioned JSON document that a human can edit and a
program can validate. Nothing here feeds the pipeline automatically. Labels are
*evaluation* data; weights are only ever changed by a person.

Level A (minimum viable annotation)
    One verdict per shot plus one closed-set technical reason and an optional duplicate
    group. Roughly 15-20 minutes for a 90-shot video.

Level B (pairwise, optional per shot)
    "Which of these two is better?" over a small sample. This is what reveals that a
    weight is wrong, without fitting an opaque model.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LABELS_SCHEMA_VERSION = "1.0"

SHOT_VERDICTS: tuple[str, ...] = ("keep", "reject", "unsure")

# Closed set: technical only, so the annotation stays inside the DSP constitution.
REJECT_REASONS: tuple[str, ...] = (
    "blur",
    "shake",
    "bad_exposure",
    "blocked_view",
    "transition",
    "too_short",
    "duplicate",
    "other",
)

BOUNDARY_VERDICTS: tuple[str, ...] = ("real_cut", "false_positive", "unsure")
PAIR_WINNERS: tuple[str, ...] = ("a", "b", "tie")


class LabelsError(ValueError):
    """Raised when a labels document is invalid."""


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_labels(*, annotator: str = "", video: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": LABELS_SCHEMA_VERSION,
        "annotator": annotator,
        "created_at_utc": utc_now_iso(),
        "updated_at_utc": utc_now_iso(),
        "video": dict(video or {}),
        "shots": [],
        "boundaries": [],
        "pairs": [],
    }


def load_labels(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise LabelsError(f"labels file not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LabelsError(f"invalid labels JSON: {exc}") from exc
    errors = validate_labels(document)
    if errors:
        raise LabelsError("; ".join(errors))
    return document


def save_labels(labels: dict[str, Any], path: Path) -> Path:
    errors = validate_labels(labels)
    if errors:
        raise LabelsError("; ".join(errors))
    labels["updated_at_utc"] = utc_now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path


def validate_labels(labels: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(labels, dict):
        return ["labels document must be an object"]
    if labels.get("schema_version") != LABELS_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {LABELS_SCHEMA_VERSION!r}, "
            f"got {labels.get('schema_version')!r}"
        )
    seen: set[str] = set()
    for index, entry in enumerate(labels.get("shots", [])):
        shot_id = entry.get("shot_id")
        if not shot_id:
            errors.append(f"shots[{index}] missing shot_id")
            continue
        if shot_id in seen:
            errors.append(f"duplicate shot label: {shot_id}")
        seen.add(shot_id)
        verdict = entry.get("verdict")
        if verdict not in SHOT_VERDICTS:
            errors.append(f"{shot_id}: invalid verdict {verdict!r}")
        reason = entry.get("reason")
        if reason is not None and reason not in REJECT_REASONS:
            errors.append(f"{shot_id}: invalid reason {reason!r}")
        duplicate_group = entry.get("duplicate_group")
        if duplicate_group is not None and not isinstance(duplicate_group, int):
            errors.append(f"{shot_id}: duplicate_group must be an integer or null")
    for index, entry in enumerate(labels.get("boundaries", [])):
        verdict = entry.get("verdict")
        if verdict not in BOUNDARY_VERDICTS:
            errors.append(f"boundaries[{index}]: invalid verdict {verdict!r}")
    for index, entry in enumerate(labels.get("pairs", [])):
        if not entry.get("a") or not entry.get("b"):
            errors.append(f"pairs[{index}]: needs both 'a' and 'b'")
        if entry.get("winner") not in PAIR_WINNERS:
            errors.append(f"pairs[{index}]: invalid winner {entry.get('winner')!r}")
    return errors


def shot_labels(labels: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["shot_id"]: entry for entry in labels.get("shots", [])}


def boundary_labels(labels: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["boundary_id"]: entry for entry in labels.get("boundaries", [])}


def coverage(labels: dict[str, Any], shot_ids: list[str]) -> dict[str, Any]:
    labeled = set(shot_labels(labels))
    relevant = [shot_id for shot_id in shot_ids if shot_id in labeled]
    return {
        "shots_total": len(shot_ids),
        "shots_labeled": len(relevant),
        "fraction": (len(relevant) / len(shot_ids)) if shot_ids else 0.0,
        "missing": [shot_id for shot_id in shot_ids if shot_id not in labeled],
        "pairs": len(labels.get("pairs", [])),
        "boundaries_labeled": len(labels.get("boundaries", [])),
    }


def record_shot_label(
    labels: dict[str, Any],
    *,
    shot_id: str,
    verdict: str,
    reason: str | None = None,
    duplicate_group: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Upsert one shot label and return the document (mutated in place)."""
    if verdict not in SHOT_VERDICTS:
        raise LabelsError(f"invalid verdict {verdict!r}")
    if reason is not None and reason not in REJECT_REASONS:
        raise LabelsError(f"invalid reason {reason!r}")
    entries = labels.setdefault("shots", [])
    for entry in entries:
        if entry["shot_id"] == shot_id:
            entry.update(
                {
                    "verdict": verdict,
                    "reason": reason,
                    "duplicate_group": duplicate_group,
                    "notes": notes,
                    "labeled_at_utc": utc_now_iso(),
                }
            )
            return labels
    entries.append(
        {
            "shot_id": shot_id,
            "verdict": verdict,
            "reason": reason,
            "duplicate_group": duplicate_group,
            "notes": notes,
            "labeled_at_utc": utc_now_iso(),
        }
    )
    return labels


def record_boundary_label(
    labels: dict[str, Any], *, boundary_id: str, verdict: str, notes: str = ""
) -> dict[str, Any]:
    if verdict not in BOUNDARY_VERDICTS:
        raise LabelsError(f"invalid boundary verdict {verdict!r}")
    entries = labels.setdefault("boundaries", [])
    for entry in entries:
        if entry["boundary_id"] == boundary_id:
            entry.update(
                {"verdict": verdict, "notes": notes, "labeled_at_utc": utc_now_iso()}
            )
            return labels
    entries.append(
        {
            "boundary_id": boundary_id,
            "verdict": verdict,
            "notes": notes,
            "labeled_at_utc": utc_now_iso(),
        }
    )
    return labels


def record_pair_label(
    labels: dict[str, Any], *, a: str, b: str, winner: str, notes: str = ""
) -> dict[str, Any]:
    if winner not in PAIR_WINNERS:
        raise LabelsError(f"invalid pair winner {winner!r}")
    labels.setdefault("pairs", []).append(
        {
            "a": a,
            "b": b,
            "winner": winner,
            "notes": notes,
            "labeled_at_utc": utc_now_iso(),
        }
    )
    return labels

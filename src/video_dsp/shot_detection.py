"""Shot boundary detection: distances, MAD threshold, local maxima, and min gap.

Translation between consecutive samples is estimated with phase correlation on a small
luminance thumbnail. It is classical DSP, deterministic, and gives two things the
histogram distance cannot: pan speed (how much the camera moved) and translation
coherence (whether it moved in one direction or shook).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

MAD_CONSISTENCY = 1.4826
MIN_THRESHOLD = 1e-3
RELATIVE_FALLBACK_RATIO = 0.10
MIN_PHASE_PIXELS = 1e-9
DEFAULT_PROMINENCE_RATIO = 2.0
DEFAULT_PROMINENCE_RADIUS = 5
DEFAULT_PROMINENCE_GUARD = 1


@dataclass
class FrameDistance:
    left_index: int
    right_index: int
    time_mid_seconds: float
    histogram: float
    gradient: float
    edge: float
    combined: float
    translation_x: float = 0.0
    translation_y: float = 0.0
    phase_response: float = 0.0

    def to_dict(self) -> dict:
        return {
            "left_index": self.left_index,
            "right_index": self.right_index,
            "time_mid_seconds": self.time_mid_seconds,
            "histogram": self.histogram,
            "gradient": self.gradient,
            "edge": self.edge,
            "combined": self.combined,
            "translation_x": self.translation_x,
            "translation_y": self.translation_y,
            "phase_response": self.phase_response,
        }


def chi_square_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Chi-square distance between two normalized histograms."""
    denominator = a + b
    mask = denominator > 0
    if not np.any(mask):
        return 0.0
    return float(np.sum(((a[mask] - b[mask]) ** 2) / denominator[mask]))


def bhattacharyya_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Bhattacharyya coefficient between two normalized histograms, in ``[0, 1]``.

    1.0 means identical distributions, 0.0 means disjoint support. Used for the
    diversity penalty because, unlike chi-square, it is bounded and comparable.
    """
    left = np.asarray(a, dtype=np.float64)
    right = np.asarray(b, dtype=np.float64)
    if left.shape != right.shape:
        raise ValueError("histograms must have the same shape")
    left_total = left.sum()
    right_total = right.sum()
    if left_total <= 0 or right_total <= 0:
        return 0.0
    coefficient = float(np.sum(np.sqrt((left / left_total) * (right / right_total))))
    return float(np.clip(coefficient, 0.0, 1.0))


def gradient_log_distance(a: float, b: float, eps: float = 1e-6) -> float:
    """Absolute log-ratio between two gradient energies."""
    return float(abs(math.log(a + eps) - math.log(b + eps)))


def edge_distance(a: float, b: float) -> float:
    """Absolute difference between two edge-density values."""
    return float(abs(a - b))


def estimate_translation(
    previous: np.ndarray | None, current: np.ndarray | None
) -> tuple[float, float, float]:
    """Estimate inter-frame translation with phase correlation.

    Returns ``(dx, dy, response)`` in thumbnail pixels. ``response`` is OpenCV's phase
    correlation confidence: near 0 for textureless or fully changed frames. When the
    thumbnails are missing or mismatched, returns zeros, which downstream code detects
    through ``phase_response`` and records as a fallback.
    """
    if previous is None or current is None:
        return 0.0, 0.0, 0.0
    if previous.shape != current.shape:
        return 0.0, 0.0, 0.0
    window = cv2.createHanningWindow(
        (current.shape[1], current.shape[0]), cv2.CV_32F
    )
    left = current.astype(np.float32) / 255.0
    right = previous.astype(np.float32) / 255.0
    try:
        (dx, dy), response = cv2.phaseCorrelate(right, left, window)
    except cv2.error:  # pragma: no cover - defensive, malformed input
        return 0.0, 0.0, 0.0
    if not (math.isfinite(dx) and math.isfinite(dy) and math.isfinite(response)):
        return 0.0, 0.0, 0.0
    return float(dx), float(dy), float(np.clip(response, 0.0, 1.0))


def compute_distances(
    samples: list[dict],
    weights: dict[str, float],
    motion_key: str = "motion_gray",
) -> list[FrameDistance]:
    """Compute combined frame-to-frame distances for consecutive samples."""
    distances: list[FrameDistance] = []
    for left, right in zip(samples, samples[1:], strict=False):
        hist = chi_square_distance(
            left["metrics"]["histogram"], right["metrics"]["histogram"]
        )
        grad = gradient_log_distance(
            left["metrics"]["tenengrad"], right["metrics"]["tenengrad"]
        )
        edge = edge_distance(
            left["metrics"]["edge_density"], right["metrics"]["edge_density"]
        )
        combined = (
            weights["histogram"] * hist
            + weights["gradient"] * grad
            + weights["edge"] * edge
        )
        dx, dy, response = estimate_translation(
            left.get(motion_key), right.get(motion_key)
        )
        distances.append(
            FrameDistance(
                left_index=left["frame_index"],
                right_index=right["frame_index"],
                time_mid_seconds=(
                    left["timestamp_seconds"] + right["timestamp_seconds"]
                )
                / 2.0,
                histogram=hist,
                gradient=grad,
                edge=edge,
                combined=combined,
                translation_x=dx,
                translation_y=dy,
                phase_response=response,
            )
        )
    return distances


def distances_from_dicts(records: list[dict]) -> list[FrameDistance]:
    """Rebuild :class:`FrameDistance` objects from the UI document's serialized pairs.

    The UI needs this to re-run shot construction after a user changes the merge
    similarity, without decoding the video again.
    """
    return [
        FrameDistance(
            left_index=int(record["left_index"]),
            right_index=int(record["right_index"]),
            time_mid_seconds=float(record["time_mid_seconds"]),
            histogram=float(record["histogram"]),
            gradient=float(record["gradient"]),
            edge=float(record["edge"]),
            combined=float(record["combined"]),
            translation_x=float(record.get("translation_x", 0.0)),
            translation_y=float(record.get("translation_y", 0.0)),
            phase_response=float(record.get("phase_response", 0.0)),
        )
        for record in records
    ]


def robust_mad(values: np.ndarray) -> tuple[float, float]:
    """Return the median and the raw median absolute deviation."""
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return median, mad


def mad_threshold(
    values: np.ndarray, multiplier: float
) -> tuple[float, float, float, str]:
    """Return ``(median, scaled_dispersion, threshold, dispersion_source)``.

    The MAD is scaled by 1.4826 so that it is a consistent estimator of the standard
    deviation for normally distributed data. When the MAD is zero (for example, many
    identical frames in static shots) it falls back to a fraction of the strongest
    distance, which keeps cuts of different magnitudes detectable instead of collapsing
    them onto a single global gap.
    """
    median, mad = robust_mad(values)
    scaled = mad * MAD_CONSISTENCY
    source = "mad"
    if scaled <= 1e-12:
        threshold = RELATIVE_FALLBACK_RATIO * float(np.max(values))
        source = "relative_max_fallback"
    else:
        threshold = median + multiplier * scaled
    threshold = max(threshold, MIN_THRESHOLD)
    return median, scaled, threshold, source


def find_local_maxima(values: np.ndarray, threshold: float, window: int) -> list[int]:
    """Indices that exceed ``threshold``, are maximal within ``+/- window``, and are
    strictly higher than at least one immeante neighbor (so flat plateaus yield a
    single candidate rather than one per frame)."""
    count = len(values)
    peaks: list[int] = []
    for index in range(count):
        if values[index] <= threshold:
            continue
        low = max(0, index - window)
        high = min(count, index + window + 1)
        is_window_max = values[index] >= float(np.max(values[low:high])) - 1e-12
        left = values[index - 1] if index > 0 else values[index]
        right = values[index + 1] if index + 1 < count else values[index]
        if is_window_max and (values[index] > left or values[index] > right):
            peaks.append(index)
    return peaks


def enforce_min_gap(peaks: list[int], values: np.ndarray, min_gap: int) -> list[int]:
    """Keep the strongest peak in any window narrower than ``min_gap``."""
    ordered = sorted(peaks, key=lambda i: values[i], reverse=True)
    kept: list[int] = []
    for index in ordered:
        if all(abs(index - other) >= min_gap for other in kept):
            kept.append(index)
    return sorted(kept)


def _finite_or_none(value: float) -> float | None:
    """JSON-safe ratio: an infinite reference report is stored as ``null``."""
    return float(value) if math.isfinite(value) else None


def peak_prominence(
    values: np.ndarray, index: int, radius: int, guard: int
) -> tuple[float, float]:
    """Return ``(ratio, local_reference)`` for the peak at ``index``.

    The reference is the median distance of the samples around the peak, excluding a
    guard band of ``guard`` samples on each side so the peak's own shoulder does not
    raise the baseline. A real cut stands far above its neighbourhood; a local maximum
    inside sustained motion (a pan, a shake) does not.
    """
    count = len(values)
    low = max(0, index - radius)
    high = min(count, index + radius + 1)
    guard_low = max(low, index - guard)
    guard_high = min(high, index + guard + 1)
    neighbours = np.concatenate([values[low:guard_low], values[guard_high:high]])
    value = float(values[index])
    if neighbours.size == 0:
        return float("inf"), 0.0
    reference = float(np.median(neighbours))
    if reference <= 1e-12:
        return (float("inf") if value > 1e-12 else 0.0), reference
    return value / reference, reference


def filter_low_prominence(
    values: np.ndarray,
    peaks: list[int],
    min_ratio: float,
    radius: int = DEFAULT_PROMINENCE_RADIUS,
    guard: int = DEFAULT_PROMINENCE_GUARD,
) -> tuple[list[int], list[dict]]:
    """Split peaks into kept and rejected by local prominence.

    ``min_ratio <= 0`` disables the filter and keeps every peak, which is the behaviour
    of versions before the prominence test existed. Every rejected peak is returned with
    its value and local reference so the audit shows why it was discarded.
    """
    if min_ratio <= 0 or not peaks:
        return list(peaks), []
    kept: list[int] = []
    rejected: list[dict] = []
    for index in peaks:
        ratio, reference = peak_prominence(values, index, radius, guard)
        if ratio >= min_ratio:
            kept.append(index)
            continue
        rejected.append(
            {
                "position": index + 1,
                "right_index": index + 1,
                "combined": float(values[index]),
                "local_reference": reference,
                "prominence_ratio": _finite_or_none(ratio),
                "reason": "low_prominence",
            }
        )
    return kept, rejected


def detect_boundaries(
    distances: list[FrameDistance],
    multiplier: float,
    min_gap_samples: int,
    *,
    prominence_ratio: float = DEFAULT_PROMINENCE_RATIO,
    prominence_radius: int = DEFAULT_PROMINENCE_RADIUS,
    prominence_guard: int = DEFAULT_PROMINENCE_GUARD,
) -> tuple[list[int], dict]:
    """Detect shot boundaries.

    Returns sample positions where a new shot begins (for :func:`build_shots`), plus
    threshold evidence and the raw frame index / timestamp of every boundary for audit.
    Peaks that do not stand out from their local neighbourhood are recorded as rejected
    instead of silently dropped.
    """
    if not distances:
        return [], {
            "median": 0.0,
            "scaled_dispersion": 0.0,
            "dispersion_source": "none",
            "threshold": 0.0,
            "mad_multiplier": multiplier,
            "prominence_ratio": prominence_ratio,
            "prominence_radius": prominence_radius,
            "prominence_guard": prominence_guard,
            "peaks_before_prominence": 0,
            "peaks_rejected_by_prominence": 0,
            "rejected_peaks": [],
            "peaks": [],
        }
    values = np.array([d.combined for d in distances], dtype=np.float64)
    median, dispersion, threshold, source = mad_threshold(values, multiplier)
    candidates = find_local_maxima(values, threshold, min_gap_samples)
    candidates = enforce_min_gap(candidates, values, min_gap_samples)
    peaks, rejected = filter_low_prominence(
        values, candidates, prominence_ratio, prominence_radius, prominence_guard
    )
    for record in rejected:
        record["time_mid_seconds"] = distances[int(record["position"]) - 1].time_mid_seconds
    positions = [index + 1 for index in peaks]
    peak_records = []
    for index in peaks:
        ratio, reference = peak_prominence(
            values, index, prominence_radius, prominence_guard
        )
        peak_records.append(
            {
                "position": index + 1,
                "right_index": distances[index].right_index,
                "time_mid_seconds": distances[index].time_mid_seconds,
                "combined": float(values[index]),
                "local_reference": reference,
                "prominence_ratio": _finite_or_none(ratio),
            }
        )
    evidence = {
        "median": median,
        "scaled_dispersion": dispersion,
        "dispersion_source": source,
        "threshold": threshold,
        "mad_multiplier": multiplier,
        "prominence_ratio": prominence_ratio,
        "prominence_radius": prominence_radius,
        "prominence_guard": prominence_guard,
        "peaks_before_prominence": len(candidates),
        "peaks_rejected_by_prominence": len(rejected),
        "rejected_peaks": rejected,
        "distance_count": len(distances),
        "peaks": peak_records,
    }
    return positions, evidence


def build_shots(samples: list[dict], boundary_indices: list[int]) -> list[list[dict]]:
    """Split samples into shots at the given boundary frame indices."""
    if not samples:
        return []
    shots: list[list[dict]] = []
    start = 0
    for boundary in sorted(set(boundary_indices)):
        if boundary <= start or boundary >= len(samples):
            continue
        shots.append(samples[start:boundary])
        start = boundary
    shots.append(samples[start:])
    return [shot for shot in shots if shot]


def shot_duration(shot: list[dict]) -> float:
    return float(shot[-1]["timestamp_seconds"] - shot[0]["timestamp_seconds"])


def shot_histogram_signature(shot: list[dict]) -> np.ndarray:
    """Mean normalized histogram over the samples of a shot.

    Averaging histograms (not concatenating) keeps the signature comparable between
    shots with different sample counts.
    """
    histograms = np.array(
        [sample["metrics"]["histogram"] for sample in shot], dtype=np.float64
    )
    signature = histograms.mean(axis=0)
    total = signature.sum()
    return signature / total if total > 0 else np.full_like(signature, 1.0 / len(signature))


def merge_similar_shots(
    shots: list[list[dict]], similarity_threshold: float
) -> list[list[dict]]:
    """Merge adjacent shots whose averaged histograms are near-identical.

    This is the explicit counter to over-segmentation: a flash, a whip pan, or a
    compression spike can split one visual plane into several shots. The threshold is
    recorded in the audit, and 1.0 disables merging entirely.
    """
    if similarity_threshold >= 1.0 or len(shots) < 2:
        return [list(shot) for shot in shots]
    merged: list[list[dict]] = [list(shots[0])]
    for shot in shots[1:]:
        previous_signature = shot_histogram_signature(merged[-1])
        current_signature = shot_histogram_signature(shot)
        similarity = bhattacharyya_similarity(previous_signature, current_signature)
        if similarity >= similarity_threshold:
            merged[-1].extend(shot)
        else:
            merged.append(list(shot))
    return merged


def enforce_min_duration(
    shots: list[list[dict]], min_duration: float
) -> list[list[dict]]:
    """Merge shots shorter than ``min_duration`` into the previous shot."""
    merged: list[list[dict]] = []
    for shot in shots:
        if merged and shot_duration(shot) < min_duration:
            merged[-1].extend(shot)
        else:
            merged.append(list(shot))
    # A leading short shot cannot merge backwards, so fold it forward instead.
    if len(merged) >= 2 and shot_duration(merged[0]) < min_duration:
        merged[1] = merged[0] + merged[1]
        merged.pop(0)
    return merged


def split_long_shots(
    shots: list[list[dict]], max_duration: float
) -> list[list[dict]]:
    """Split shots longer than ``max_duration`` into roughly equal chunks."""
    result: list[list[dict]] = []
    for shot in shots:
        duration = shot_duration(shot)
        if duration <= max_duration or len(shot) < 2:
            result.append(shot)
            continue
        pieces = max(2, int(math.ceil(duration / max_duration)))
        size = max(1, int(math.ceil(len(shot) / pieces)))
        for offset in range(0, len(shot), size):
            chunk = shot[offset : offset + size]
            if chunk:
                result.append(chunk)
    return result


def rebuild_shots(
    samples: list[dict],
    boundary_positions: list[int],
    *,
    merge_similarity: float = 1.0,
    min_duration: float = 1.0,
    max_duration: float = 15.0,
) -> tuple[list[list[dict]], dict]:
    """Rebuild shots from raw samples and boundary positions, with recorded counts.

    This is the single entry point used by the boundary-calibration view: it applies
    the same merge/split rules as the pipeline so a manual boundary edit is scored
    exactly like an automatic one.
    """
    built = build_shots(samples, boundary_positions)
    after_merge = merge_similar_shots(built, merge_similarity)
    after_min = enforce_min_duration(after_merge, min_duration)
    final = split_long_shots(after_min, max_duration)
    evidence = {
        "boundary_positions": len(boundary_positions),
        "shots_built": len(built),
        "shots_after_similarity_merge": len(after_merge),
        "shots_after_min_duration": len(after_min),
        "shots_final": len(final),
        "merge_similarity": merge_similarity,
        "min_duration_s": min_duration,
        "max_duration_s": max_duration,
    }
    return final, evidence

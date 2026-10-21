import numpy as np
import pytest

from video_dsp.shot_detection import (
    FrameDistance,
    build_shots,
    chi_square_distance,
    compute_distances,
    detect_boundaries,
    enforce_min_duration,
    filter_low_prominence,
    peak_prominence,
    split_long_shots,
)


def test_identical_histograms_have_zero_distance():
    histogram = np.array([0.5, 0.5])
    assert chi_square_distance(histogram, histogram) == 0.0


def test_different_histograms_have_positive_distance():
    assert chi_square_distance(np.array([1.0, 0.0]), np.array([0.0, 1.0])) > 0.0


def test_chi_square_is_symmetric():
    a = np.array([0.7, 0.3])
    b = np.array([0.2, 0.8])
    assert chi_square_distance(a, b) == chi_square_distance(b, a)


def _samples(histograms, tenengrads, edges):
    return [
        {
            "frame_index": index,
            "timestamp_seconds": float(index),
            "metrics": {
                "histogram": np.asarray(histogram, dtype=float),
                "tenengrad": float(tenengrad),
                "edge_density": float(edge),
            },
        }
        for index, (histogram, tenengrad, edge) in enumerate(
            zip(histograms, tenengrads, edges, strict=False)
        )
    ]


def test_compute_distances_combines_components():
    samples = _samples(
        [np.array([1.0, 0.0]), np.array([0.0, 1.0])],
        [100.0, 400.0],
        [0.1, 0.3],
    )
    distances = compute_distances(
        samples, {"histogram": 0.5, "gradient": 0.25, "edge": 0.25}
    )
    assert len(distances) == 1
    assert distances[0].histogram > 0
    assert distances[0].gradient > 0
    assert distances[0].edge > 0
    assert distances[0].combined > 0


def _distances(values):
    return [
        FrameDistance(
            left_index=index,
            right_index=index + 1,
            time_mid_seconds=index + 0.5,
            histogram=0.0,
            gradient=0.0,
            edge=0.0,
            combined=float(value),
        )
        for index, value in enumerate(values)
    ]


def test_mad_threshold_detects_injected_peak():
    values = [0.1] * 10 + [5.0] + [0.1] * 10
    positions, evidence = detect_boundaries(
        _distances(values), multiplier=3.0, min_gap_samples=2
    )
    assert positions == [11]
    assert evidence["peaks"][0]["right_index"] == 11


def test_local_maxima_and_min_gap():
    values = [0.1, 0.1, 4.0, 0.1, 3.9, 0.1, 0.1]
    positions, _ = detect_boundaries(
        _distances(values), multiplier=3.0, min_gap_samples=3
    )
    assert positions == [3]


def test_no_boundaries_for_flat_distances():
    positions, _ = detect_boundaries(
        _distances([0.2] * 20), multiplier=3.0, min_gap_samples=2
    )
    assert positions == []


def test_mad_zero_falls_back_to_relative_max():
    values = [0.0] * 20 + [1.0] + [0.0] * 20
    positions, evidence = detect_boundaries(
        _distances(values), multiplier=3.0, min_gap_samples=2
    )
    assert positions == [21]
    assert evidence["dispersion_source"] == "relative_max_fallback"
    # An isolated spike above an empty baseline has no neighbourhood to be compared
    # with, so the ratio is reported as null instead of an infinite number.
    assert evidence["peaks"][0]["prominence_ratio"] is None
    assert evidence["peaks"][0]["local_reference"] == 0.0


def test_prominence_rejects_peak_inside_sustained_motion():
    values = [0.30] * 6 + [0.55] + [0.30] * 6 + [3.0] + [0.30] * 6
    positions, evidence = detect_boundaries(
        _distances(values), multiplier=3.0, min_gap_samples=2
    )
    # The 0.55 bump only reaches 1.83x its neighbourhood: motion, not a cut.
    assert positions == [14]
    assert evidence["peaks_before_prominence"] == 2
    assert evidence["peaks_rejected_by_prominence"] == 1
    rejected = evidence["rejected_peaks"][0]
    assert rejected["position"] == 7
    assert rejected["reason"] == "low_prominence"
    assert rejected["prominence_ratio"] == pytest.approx(0.55 / 0.30)
    assert rejected["local_reference"] == pytest.approx(0.30)
    assert rejected["time_mid_seconds"] == pytest.approx(6.5)
    assert evidence["peaks"][0]["prominence_ratio"] == pytest.approx(10.0)


def test_prominence_zero_disables_the_filter():
    values = [0.30] * 6 + [0.55] + [0.30] * 6 + [3.0] + [0.30] * 6
    positions, evidence = detect_boundaries(
        _distances(values), multiplier=3.0, min_gap_samples=2, prominence_ratio=0.0
    )
    assert positions == [7, 14]
    assert evidence["peaks_rejected_by_prominence"] == 0


def test_peak_prominence_uses_a_guard_band():
    values = np.array([0.10, 1.00, 1.00, 1.00, 0.10])
    ratio, reference = peak_prominence(values, index=2, radius=2, guard=1)
    assert reference == pytest.approx(0.10)
    assert ratio == pytest.approx(10.0)
    # Without the guard the peak's own shoulder would raise the reference.
    wide_ratio, wide_reference = peak_prominence(values, index=2, radius=2, guard=0)
    assert wide_reference == pytest.approx(0.55)
    assert wide_ratio == pytest.approx(1.0 / 0.55)


def test_filter_low_prominence_is_a_pure_split():
    values = np.array([0.10, 0.10, 1.00, 0.10, 0.15, 0.10])
    kept, rejected = filter_low_prominence(values, [2, 4], min_ratio=2.0)
    assert kept == [2]
    assert [record["position"] for record in rejected] == [5]


def _shot(frame_indices, fps=10.0):
    return [
        {"frame_index": index, "timestamp_seconds": index / fps, "metrics": {}}
        for index in frame_indices
    ]


def test_build_shots_splits_at_positions():
    samples = [
        {"frame_index": index, "timestamp_seconds": float(index), "metrics": {}}
        for index in range(6)
    ]
    shots = build_shots(samples, [2, 4])
    assert [len(shot) for shot in shots] == [2, 2, 2]


def test_enforce_min_duration_merges_short_shots():
    shots = [_shot([0]), _shot([1]), _shot(list(range(2, 10)))]
    merged = enforce_min_duration(shots, min_duration=0.5)
    assert len(merged) == 1
    assert len(merged[0]) == 10


def test_split_long_shots():
    pieces = split_long_shots([_shot(list(range(30)))], max_duration=1.0)
    assert len(pieces) == 3
    assert sum(len(piece) for piece in pieces) == 30


def test_bhattacharyya_bounds():
    from video_dsp.shot_detection import bhattacharyya_similarity

    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert bhattacharyya_similarity(a, a) == 1.0
    assert bhattacharyya_similarity(a, b) == 0.0
    assert bhattacharyya_similarity(a, np.array([0.5, 0.5])) == pytest.approx(
        0.7071, abs=1e-4
    )
    assert bhattacharyya_similarity(a, np.array([0.5, 0.5])) == bhattacharyya_similarity(
        np.array([0.5, 0.5]), a
    )


def test_estimate_translation_recovers_a_known_shift():
    from video_dsp.shot_detection import estimate_translation

    rng = np.random.default_rng(7)
    base = rng.integers(0, 255, size=(96, 96), dtype=np.uint8)
    shifted = np.roll(base, shift=(3, 5), axis=(0, 1))
    dx, dy, response = estimate_translation(base, shifted)
    assert abs(abs(dx) - 5) < 1.0
    assert abs(abs(dy) - 3) < 1.0
    assert response > 0.0


def test_estimate_translation_handles_missing_thumbnails():
    from video_dsp.shot_detection import estimate_translation

    assert estimate_translation(None, None) == (0.0, 0.0, 0.0)
    base = np.zeros((8, 8), dtype=np.uint8)
    assert estimate_translation(base, np.zeros((4, 4), dtype=np.uint8)) == (0.0, 0.0, 0.0)


def test_compute_distances_records_translation_when_thumbnails_exist():
    rng = np.random.default_rng(3)
    samples = _samples(
        [np.array([1.0, 0.0]), np.array([1.0, 0.0])],
        [100.0, 100.0],
        [0.1, 0.1],
    )
    base = rng.integers(0, 255, size=(48, 48), dtype=np.uint8)
    samples[0]["motion_gray"] = base
    samples[1]["motion_gray"] = np.roll(base, 4, axis=1)
    distances = compute_distances(
        samples, {"histogram": 0.5, "gradient": 0.25, "edge": 0.25}
    )
    assert abs(abs(distances[0].translation_x) - 4) < 1.0
    assert distances[0].phase_response > 0.0


def _histogram_shot(frame_indices, value: float, fps=10.0):
    histogram = np.zeros(8)
    histogram[int(value)] = 1.0
    return [
        {
            "frame_index": index,
            "timestamp_seconds": index / fps,
            "metrics": {"histogram": histogram, "tenengrad": 100.0, "edge_density": 0.1},
        }
        for index in frame_indices
    ]


def test_shot_histogram_signature_sums_to_one():
    from video_dsp.shot_detection import shot_histogram_signature

    signature = shot_histogram_signature(_histogram_shot([0, 1, 2], 2.0))
    assert float(signature.sum()) == pytest.approx(1.0)


def test_merge_similar_shots_joins_near_identical_neighbours():
    from video_dsp.shot_detection import merge_similar_shots

    shots = [
        _histogram_shot([0, 1], 1.0),
        _histogram_shot([2, 3], 1.0),
        _histogram_shot([4, 5], 6.0),
    ]
    merged = merge_similar_shots(shots, similarity_threshold=0.95)
    assert len(merged) == 2
    assert len(merged[0]) == 4


def test_merge_similar_shots_is_disabled_at_one():
    from video_dsp.shot_detection import merge_similar_shots

    shots = [
        _histogram_shot([0, 1], 1.0),
        _histogram_shot([2, 3], 1.0),
    ]
    assert len(merge_similar_shots(shots, similarity_threshold=1.0)) == 2


def test_rebuild_shots_reports_each_stage():
    from video_dsp.shot_detection import rebuild_shots

    samples = [
        {"frame_index": index, "timestamp_seconds": index / 10.0, "metrics": {}}
        for index in range(40)
    ]
    shots, evidence = rebuild_shots(
        samples,
        [10, 20, 30],
        merge_similarity=1.0,
        min_duration=0.5,
        max_duration=1.0,
    )
    assert evidence["shots_built"] == 4
    assert evidence["shots_final"] == len(shots)
    assert evidence["merge_similarity"] == 1.0
    assert evidence["boundary_positions"] == 3

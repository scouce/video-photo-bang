"""Pure per-frame technical DSP metrics.

All functions are deterministic and operate on a float luminance plane in ``[0, 1]``.
No enhancement (sharpening, denoising, tone mapping, upscaling) is applied.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

EPS = 1e-12
LOCAL_CONTRAST_BLOCK = 8
MOTION_THUMB_MAX_DIM = 96


def to_luminance(bgr: np.ndarray) -> np.ndarray:
    """Convert a BGR uint8 frame to float32 luminance in ``[0, 1]`` (BT.601 weights)."""
    blue = bgr[:, :, 0].astype(np.float32)
    green = bgr[:, :, 1].astype(np.float32)
    red = bgr[:, :, 2].astype(np.float32)
    luminance = 0.114 * blue + 0.587 * green + 0.299 * red
    return np.clip(luminance / 255.0, 0.0, 1.0)


def compute_variance_laplacian(gray: np.ndarray) -> float:
    """Variance of the Laplacian — a classic sharpness proxy."""
    laplacian = cv2.Laplacian(gray, cv2.CV_32F)
    return float(laplacian.var())


def compute_tenengrad(gray: np.ndarray) -> float:
    """Mean squared Sobel gradient magnitude — a classic focus measure."""
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return float(np.mean(gx * gx + gy * gy))


def compute_edge_density(gray: np.ndarray, low: float = 100.0, high: float = 200.0) -> float:
    """Fraction of pixels flagged as edges by the Canny detector."""
    edges = cv2.Canny((gray * 255.0).astype(np.uint8), low, high)
    return float(np.count_nonzero(edges) / edges.size)


def compute_luminance_stats(
    gray: np.ndarray, clip_low: float = 0.02, clip_high: float = 0.98
) -> dict[str, float]:
    """Mean, standard deviation, percentiles, and black/white clipping ratios."""
    flat = gray.ravel()
    percentiles = np.percentile(flat, [1, 5, 25, 50, 75, 95, 99])
    return {
        "mean": float(np.mean(flat)),
        "std": float(np.std(flat)),
        "p01": float(percentiles[0]),
        "p05": float(percentiles[1]),
        "p25": float(percentiles[2]),
        "p50": float(percentiles[3]),
        "p75": float(percentiles[4]),
        "p95": float(percentiles[5]),
        "p99": float(percentiles[6]),
        "black_clip": float(np.mean(flat <= clip_low)),
        "white_clip": float(np.mean(flat >= clip_high)),
    }


def compute_normalized_histogram(gray: np.ndarray, bins: int = 64) -> np.ndarray:
    """Normalized luminance histogram (sums to 1)."""
    histogram, _ = np.histogram(gray, bins=bins, range=(0.0, 1.0))
    total = histogram.sum()
    if total == 0:
        return np.full(bins, 1.0 / bins, dtype=np.float64)
    return (histogram / total).astype(np.float64)


def compute_histogram_entropy(histogram: np.ndarray) -> float:
    """Shannon entropy of a normalized histogram, scaled to ``[0, 1]`` by log2(bins).

    A perfectly flat luminance distribution scores 1.0; a single occupied bin scores 0.
    """
    probabilities = np.asarray(histogram, dtype=np.float64)
    probabilities = probabilities[probabilities > 0]
    if probabilities.size == 0:
        return 0.0
    max_entropy = math.log2(len(histogram)) if len(histogram) > 1 else 1.0
    entropy = -float(np.sum(probabilities * np.log2(probabilities)))
    return float(np.clip(entropy / max_entropy, 0.0, 1.0))


def compute_local_contrast(gray: np.ndarray, block: int = LOCAL_CONTRAST_BLOCK) -> float:
    """Mean within-block luminance standard deviation (microcontrast / texture proxy).

    Uses box filters so the cost is independent of the block size and the result is
    deterministic. Unit: luminance std inside an ``block x block`` window.
    """
    single = gray.astype(np.float32)
    mean = cv2.blur(single, (block, block))
    mean_squares = cv2.blur(single * single, (block, block))
    variance = np.maximum(mean_squares - mean * mean, 0.0)
    return float(np.mean(np.sqrt(variance)))


def compute_color_stats(bgr: np.ndarray) -> dict[str, float]:
    """Saturation and colourfulness statistics on the analysis-resolution frame.

    ``colorfulness`` is the Hasler-Süsstrunk index normalised by 255, so it stays on a
    roughly ``0.0-0.5`` scale. ``channel_cast`` is the maximum absolute difference
    between channel means divided by 255; 0 means a neutral balance.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1].astype(np.float32) / 255.0

    blue = bgr[:, :, 0].astype(np.float32)
    green = bgr[:, :, 1].astype(np.float32)
    red = bgr[:, :, 2].astype(np.float32)
    red_green = red - green
    yellow_blue = 0.5 * (red + green) - blue
    std_rg = float(np.std(red_green))
    std_yb = float(np.std(yellow_blue))
    mean_rg = float(np.mean(red_green))
    mean_yb = float(np.mean(yellow_blue))
    colorfulness = (
        math.sqrt(std_rg**2 + std_yb**2) + 0.3 * math.sqrt(mean_rg**2 + mean_yb**2)
    ) / 255.0

    channel_means = [float(np.mean(blue)), float(np.mean(green)), float(np.mean(red))]
    channel_cast = (
        max(channel_means) - min(channel_means)
    ) / 255.0
    return {
        "saturation_mean": float(np.mean(saturation)),
        "saturation_std": float(np.std(saturation)),
        "colorfulness": float(colorfulness),
        "channel_cast": float(channel_cast),
    }


def resize_for_analysis(bgr: np.ndarray, config: dict) -> np.ndarray:
    """Downscale to the documented analysis resolution (never upscales).

    This is a measurement-resolution choice, not an enhancement: it is recorded in the
    output JSON and can be disabled with ``analysis_resize.enabled = false``.
    """
    resize = config.get("analysis_resize", {})
    if not resize.get("enabled"):
        return bgr
    max_dimension = int(resize.get("max_dimension", 1280))
    height, width = bgr.shape[:2]
    longest = max(height, width)
    if max_dimension <= 0 or longest <= max_dimension:
        return bgr
    scale = max_dimension / longest
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    interpolation = (
        cv2.INTER_AREA if resize.get("interpolation") == "area" else cv2.INTER_LINEAR
    )
    return cv2.resize(bgr, size, interpolation=interpolation)


def motion_thumbnail(bgr: np.ndarray, max_dimension: int = MOTION_THUMB_MAX_DIM) -> np.ndarray:
    """Small luminance thumbnail used only for inter-frame translation estimation.

    The frame is downscaled *before* the luminance conversion so a 4K frame costs one
    area-resize instead of a full-resolution float pass.
    """
    height, width = bgr.shape[:2]
    longest = max(height, width)
    if max_dimension > 0 and longest > max_dimension:
        scale = max_dimension / longest
        size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        bgr = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
    gray = to_luminance(bgr)
    return np.clip(gray * 255.0, 0.0, 255.0).astype(np.uint8)


def compute_frame_metrics(bgr: np.ndarray, config: dict) -> dict:
    """Compute all per-frame metrics for one BGR frame.

    Statistics, clipping, and histograms use luminance in ``[0, 1]``. Gradient-based
    sharpness metrics use the same plane scaled to ``[0, 255]`` so their normalization
    ranges are expressed in conventional 8-bit units. Colour metrics are computed on
    the same analysis-resolution frame, never on an enhanced one.
    """
    analysis = resize_for_analysis(bgr, config)
    gray = to_luminance(analysis)
    gray_255 = gray * 255.0
    canny = config["canny"]
    bins = int(config["histogram_bins"])
    histogram = compute_normalized_histogram(gray, bins)
    metrics: dict = {
        "variance_laplacian": compute_variance_laplacian(gray_255),
        "tenengrad": compute_tenengrad(gray_255),
        "edge_density": compute_edge_density(gray, canny["low"], canny["high"]),
        "entropy": compute_histogram_entropy(histogram),
        "local_contrast": compute_local_contrast(gray),
        "histogram": histogram,
    }
    metrics.update(
        compute_luminance_stats(gray, config["clip_low"], config["clip_high"])
    )
    metrics.update(compute_color_stats(analysis))
    return metrics

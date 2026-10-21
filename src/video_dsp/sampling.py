"""Frame sampling at a configurable analysis FPS.

Frames are decoded sequentially so that frame indices and timestamps are exact and the
pipeline stays deterministic. Only metrics are retained; decoded pixels are released
immeantely to keep memory bounded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class VideoDecodeError(RuntimeError):
    """Raised when frames cannot be decoded."""


@dataclass
class SampledFrame:
    frame_index: int
    timestamp_seconds: float
    bgr: np.ndarray


def open_capture(path: Path) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise VideoDecodeError(f"could not open video: {path}")
    return capture


def decoder_fps(path: Path) -> float:
    """Return the decoder-reported FPS, raising if it is unavailable."""
    capture = open_capture(path)
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
    finally:
        capture.release()
    if not math.isfinite(fps) or fps <= 0:
        raise VideoDecodeError("decoder did not report a usable FPS")
    return fps


def iter_sampled_frames(path: Path, analysis_fps: float):
    """Yield sampled frames at ``analysis_fps`` using exact frame indices.

    The decoder FPS is used to compute the sampling step. This assumes a constant frame
    rate; VFR inputs are detected upstream and recorded as a warning.
    """
    if analysis_fps <= 0:
        raise ValueError("analysis_fps must be positive")

    capture = open_capture(path)
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise VideoDecodeError("decoder did not report a usable FPS")
        step = max(1, int(round(fps / analysis_fps)))
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            if index % step == 0:
                yield SampledFrame(frame_index=index, timestamp_seconds=index / fps, bgr=frame)
            index += 1
    finally:
        capture.release()


def read_frame_at_index(path: Path, frame_index: int) -> np.ndarray | None:
    """Read a single frame by index (used to export representative frames)."""
    capture = open_capture(path)
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = capture.read()
        return frame if ok and frame is not None else None
    finally:
        capture.release()


class FrameReader:
    """Reusable random-access frame reader.

    Exporting ten representative frames and several hundred boundary frames through
    :func:`read_frame_at_index` reopens the container each time, which dominates the
    runtime on a 1 GB file. This keeps one decoder open for the whole export phase.
    """

    def __init__(self, path: Path, fps: float | None = None) -> None:
        self.path = path
        self.capture = open_capture(path)
        self.fps = fps if fps and fps > 0 else float(self.capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(self.fps) or self.fps <= 0:
            self.capture.release()
            raise VideoDecodeError("decoder did not report a usable FPS")
        self._last_index: int | None = None

    def read_index(self, frame_index: int) -> np.ndarray | None:
        index = max(0, int(frame_index))
        # A sequential read is faster than seeking when the exporter is already there.
        if self._last_index is not None and index == self._last_index + 1:
            ok, frame = self.capture.read()
            self._last_index = index if ok else None
            return frame if ok and frame is not None else None
        self.capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self.capture.read()
        self._last_index = index if ok else None
        return frame if ok and frame is not None else None

    def read_time(self, seconds: float) -> np.ndarray | None:
        return self.read_index(int(round(max(0.0, seconds) * self.fps)))

    def close(self) -> None:
        self.capture.release()

    def __enter__(self) -> FrameReader:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

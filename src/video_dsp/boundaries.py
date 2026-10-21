"""Boundary evidence montages.

For every detected boundary this module renders a strip of frames at fixed offsets
around the cut. A still frame cannot prove a cut is real, but five frames can: a true
cut changes content, while a flash, a whip pan or a compression spike does not.

This replaces clip export for the MVP: no ffmpeg dependency, no re-encoding, no extra
disk beyond a few hundred PNG strips, and the frames come from the source at full
quality before being downscaled.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .sampling import FrameReader

STRIP_BACKGROUND = (18, 18, 18)
STRIP_TEXT = (240, 240, 240)
STRIP_ACCENT = (90, 200, 255)
STRIP_MISSING = (40, 40, 120)


def _label(frame: np.ndarray, text: str, colour: tuple[int, int, int]) -> np.ndarray:
    """Draw a label on a dark bar at the bottom of the frame."""
    bar_height = max(18, int(frame.shape[0] * 0.10))
    canvas = frame.copy()
    cv2.rectangle(
        canvas,
        (0, canvas.shape[0] - bar_height),
        (canvas.shape[1], canvas.shape[0]),
        STRIP_BACKGROUND,
        thickness=-1,
    )
    scale = max(0.35, bar_height / 40.0)
    cv2.putText(
        canvas,
        text,
        (6, canvas.shape[0] - max(4, bar_height // 4)),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        colour,
        1,
        cv2.LINE_AA,
    )
    return canvas


def _missing_frame(size: tuple[int, int], text: str) -> np.ndarray:
    frame = np.full((size[1], size[0], 3), STRIP_MISSING, dtype=np.uint8)
    return _label(frame, text, STRIP_TEXT)


def _thumbnail(frame: np.ndarray, width: int) -> np.ndarray:
    height, original_width = frame.shape[:2]
    if original_width <= width:
        return frame
    scale = width / original_width
    return cv2.resize(
        frame,
        (width, max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def render_boundary_montages(
    input_path: Path,
    boundaries: list[dict[str, Any]],
    output_dir: Path,
    config: dict,
    fps: float | None = None,
) -> list[dict[str, Any]]:
    """Write one strip per boundary and return an index record per boundary.

    ``boundaries`` entries need ``time_mid_seconds`` and may carry ``combined`` (the
    detection strength) and ``position``. The returned records are what the UI lists;
    missing frames are recorded per offset instead of being hidden.
    """
    settings = config.get("boundary_montage", {})
    if not settings.get("enabled", True) or not boundaries:
        return []

    offsets = [
        float(value)
        for value in settings.get("offsets_seconds", [-0.4, -0.2, 0.0, 0.2, 0.4])
    ]
    width = int(settings.get("thumb_width", 320))
    max_boundaries = int(settings.get("max_boundaries", 0))
    selected = boundaries[:max_boundaries] if max_boundaries > 0 else boundaries

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("boundary_*.png"):
        stale.unlink()

    records: list[dict[str, Any]] = []
    with FrameReader(input_path, fps) as reader:
        for index, boundary in enumerate(selected, start=1):
            time_mid = float(boundary["time_mid_seconds"])
            frames: list[np.ndarray] = []
            present: list[bool] = []
            timestamps: list[float] = []
            for offset in offsets:
                target_time = time_mid + offset
                timestamps.append(target_time)
                frame = None
                if target_time >= 0.0:
                    frame = reader.read_time(target_time)
                if frame is None:
                    frames.append(None)  # type: ignore[arg-type]
                    present.append(False)
                    continue
                frames.append(_thumbnail(frame, width))
                present.append(True)

            reference = next((frame for frame in frames if frame is not None), None)
            if reference is None:
                size = (width, max(1, int(round(width * 9 / 16))))
            else:
                size = (reference.shape[1], reference.shape[0])

            strips: list[np.ndarray] = []
            for offset, frame in zip(offsets, frames, strict=False):
                label = f"{offset:+.1f}s  {time_mid + offset:.2f}s"
                if frame is None:
                    strips.append(_missing_frame(size, f"{label}  N/D"))
                else:
                    strips.append(_label(frame, label, STRIP_TEXT))

            strip = cv2.hconcat(strips)
            header_height = max(22, int(size[1] * 0.12))
            header = np.full((header_height, strip.shape[1], 3), STRIP_BACKGROUND, dtype=np.uint8)
            strength = boundary.get("combined")
            if isinstance(strength, (int, float)):
                strength_text = f"  strength={strength:.4f}"
            else:
                strength_text = ""
            cv2.putText(
                header,
                f"boundary {index:03d}  t={time_mid:.2f}s{strength_text}",
                (6, header_height - max(5, header_height // 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.4, header_height / 40.0),
                STRIP_ACCENT,
                1,
                cv2.LINE_AA,
            )
            montage = cv2.vconcat([header, strip])

            filename = f"boundary_{index:03d}_t{time_mid:08.3f}.png"
            target = output_dir / filename
            written = cv2.imwrite(str(target), montage)
            records.append(
                {
                    "boundary_id": f"boundary_{index:04d}",
                    "time_mid_seconds": time_mid,
                    "combined": strength if isinstance(strength, (int, float)) else None,
                    "offsets_seconds": offsets,
                    "frame_timestamps": timestamps,
                    "frames_present": present,
                    "path": target.as_posix() if written else None,
                    "written": bool(written),
                }
            )
    return records

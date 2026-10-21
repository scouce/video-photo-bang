from video_dsp.config import load_config
from video_dsp.ingest import VideoMetadata, parse_fps, validate_metadata


def test_parse_fps():
    assert parse_fps("25/1") == 25.0
    assert parse_fps("30000/1001") == 30000 / 1001
    assert parse_fps("0/0") == 0.0
    assert parse_fps("") == 0.0


def _metadata(**overrides):
    base = {
        "path": "x.mov",
        "file_hash_sha256": "h",
        "container": "mov",
        "codec": "h264",
        "width": 1920,
        "height": 1080,
        "fps": 25.0,
        "avg_fps": 25.0,
        "duration_seconds": 10.0,
        "pix_fmt": "yuv420p",
        "color_range": "tv",
        "color_space": "bt709",
        "rotation_degrees": 0,
        "nb_frames": 250,
        "vfr": False,
        "warnings": [],
    }
    base.update(overrides)
    return VideoMetadata(**base)


def test_validation_passes_for_good_metadata():
    result = validate_metadata(_metadata(), load_config())
    assert result.ok
    assert not result.errors


def test_validation_fails_for_tiny_resolution():
    result = validate_metadata(_metadata(width=100, height=100), load_config())
    assert not result.ok
    assert any("resolution_below_minimum" in error for error in result.errors)


def test_validation_fails_without_video_stream():
    result = validate_metadata(
        _metadata(codec="unknown", width=0, height=0), load_config()
    )
    assert not result.ok
    assert "missing_video_stream" in result.errors

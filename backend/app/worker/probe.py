"""Video inspection with ffprobe (read-only: it never modifies the file)."""
import json
import subprocess
from pathlib import Path


class ProbeError(Exception):
    """The file is unreadable or not a usable video. The message is safe to show to users."""


class ToolMissing(Exception):
    """ffprobe is not installed where the worker runs."""


def _num(value, cast=float):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _fps(rate: str | None) -> float | None:
    try:
        num, den = (rate or "").split("/")
        return round(float(num) / float(den), 2) if float(den) else None
    except ValueError:
        return None


def summarize(data: dict, allow_audio_only: bool = False) -> dict:
    """Turn ffprobe's JSON into a small, validated summary. Raises ProbeError if it is not a playable video."""
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None and not (allow_audio_only and audio is not None):
        raise ProbeError("The file contains no video stream.")
    video = video or {}
    fmt = data.get("format") or {}
    duration = _num(fmt.get("duration")) or _num(video.get("duration"))
    if not duration or duration <= 0:
        raise ProbeError("The video has no readable duration (the file may be incomplete or corrupt).")
    return {
        "duration_seconds": round(duration, 2),
        "audio_only": not video,
        "format": fmt.get("format_name"),
        "video_codec": video.get("codec_name"),
        "width": _num(video.get("width"), int),
        "height": _num(video.get("height"), int),
        "fps": _fps(video.get("avg_frame_rate")),
        "audio_codec": audio.get("codec_name") if audio else None,
        "has_audio": audio is not None,
        "bit_rate": _num(fmt.get("bit_rate"), int),
        "size_bytes": _num(fmt.get("size"), int),
    }


def probe_video(path: Path, timeout: int = 60, allow_audio_only: bool = False) -> dict:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ToolMissing("ffprobe is not installed on the worker.")
    except subprocess.TimeoutExpired:
        raise ProbeError("Analysing the file took too long.")
    if proc.returncode != 0:
        reason = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        cleaned = reason[0].replace(f"{path}: ", "").replace(str(path), "the file")
        raise ProbeError("The file could not be read as a video: " + cleaned[:200])
    try:
        return summarize(json.loads(proc.stdout or "{}"), allow_audio_only)
    except json.JSONDecodeError:
        raise ProbeError("ffprobe returned unreadable output for this file.")

"""Timeline validation and FFmpeg rendering (PRD Phase 7-8: Trim, Split, Merge, reorder, export to MP4).

Pure Python, standard library only: no FastAPI, SQLAlchemy or Celery imports, so it is easy to test with real ffmpeg.

Timeline format (stored as JSON on the project):
    {"clips": [{"recording_id": 3, "start": 0.0, "end": 12.5}, ...]}
Clips play one after another in list order. "Trim" = change start/end; "Split" = two clips of the same source with
touching start/end; "Merge" = clips from different recordings; "Reorder" = change the list order.
"""
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

MAX_CLIPS = 100
MIN_CLIP_SECONDS = 0.1
RESOLUTIONS = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}
QUALITY_CRF = {"low": 30, "medium": 25, "high": 20}
ALLOWED_FPS = (24, 25, 30, 60)
MAX_AUDIO_TRACKS = 20
FILTERS = {
    "none": "",
    "grayscale": "hue=s=0",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "blur": "gblur=sigma=4",
    "sharpen": "unsharp=5:5:1.0:5:5:0.0",
    "vignette": "vignette=PI/4",
}
TRANSITIONS = {"none": None, "fade_black": "black", "fade_white": "white"}  # a dip to a colour between two clips; the total length does not change
MAX_TEXTS = 200
POSITIONS = ("top", "center", "bottom")
FONT_CANDIDATES = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")  # DejaVu covers Latin, Cyrillic, Armenian


class TimelineError(Exception):
    """The timeline is not valid. The message is safe to show to users."""


class RenderError(Exception):
    """FFmpeg failed. The message is safe to show to users."""


@dataclass(frozen=True)
class Clip:
    recording_id: int
    start: float
    end: float
    path: Path
    has_audio: bool
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    vfx: dict | None = None  # picture effects, see clip_video_settings()

    @property
    def duration(self) -> float:
        return self.end - self.start


def validate_timeline(timeline: dict, sources: dict[int, dict]) -> list[tuple[int, float, float]]:
    """Check clips against the real recordings. `sources` maps recording_id -> {"duration": float, ...}.
    Returns normalized (recording_id, start, end) tuples or raises TimelineError."""
    clips = (timeline or {}).get("clips")
    if not isinstance(clips, list) or not clips:
        raise TimelineError("The timeline is empty. Add at least one clip.")
    if len(clips) > MAX_CLIPS:
        raise TimelineError(f"A timeline can have at most {MAX_CLIPS} clips.")
    out = []
    for i, c in enumerate(clips, start=1):
        if not isinstance(c, dict):
            raise TimelineError(f"Clip {i} is not valid.")
        rid, start, end = c.get("recording_id"), c.get("start"), c.get("end")
        if isinstance(rid, bool) or not isinstance(rid, int):
            raise TimelineError(f"Clip {i} has no recording.")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (start, end)):
            raise TimelineError(f"Clip {i} needs numeric start and end times.")
        src = sources.get(rid)
        if src is None:
            raise TimelineError(f"Clip {i} uses a recording that does not exist or has no video file.")
        start, end = float(start), float(end)
        if start < 0 or end <= start:
            raise TimelineError(f"Clip {i}: the end must be after the start (start cannot be negative).")
        if end > src["duration"] + 0.05:
            raise TimelineError(f"Clip {i}: ends at {end:.1f} s but the video is only {src['duration']:.1f} s long.")
        end = min(end, float(src["duration"]))
        if end - start < MIN_CLIP_SECONDS:
            raise TimelineError(f"Clip {i} is shorter than {MIN_CLIP_SECONDS} s.")
        out.append((rid, round(start, 3), round(end, 3)))
    return out


def _num_in(value, default: float, low: float, high: float, label: str) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise TimelineError(f"{label} must be a number between {low:g} and {high:g}.")
    return float(value)


def clip_audio_settings(timeline: dict, normalized: list[tuple[int, float, float]]) -> list[tuple[float, float, float]]:
    """(volume, fade_in, fade_out) for each clip, in the same order as `normalized`. Volume 1.0 = unchanged, 0 = muted."""
    raw = timeline.get("clips") or []
    out = []
    for i, (c, (_, start, end)) in enumerate(zip(raw, normalized), start=1):
        volume = _num_in(c.get("volume"), 1.0, 0, 2, f"Clip {i}: volume")
        fi = _num_in(c.get("fade_in"), 0.0, 0, 30, f"Clip {i}: fade in")
        fo = _num_in(c.get("fade_out"), 0.0, 0, 30, f"Clip {i}: fade out")
        if fi + fo > (end - start) + 0.001:
            raise TimelineError(f"Clip {i}: fade in + fade out is longer than the clip.")
        out.append((volume, fi, fo))
    return out


def clip_video_settings(timeline: dict, normalized: list[tuple[int, float, float]]) -> list[dict]:
    """Picture settings per clip, same order as `normalized`: filter, brightness, contrast, saturation and the transition to the next clip.
    Returns dicts with: filter, brightness, contrast, saturation, tin=(colour, seconds)|None, tout=(colour, seconds)|None."""
    raw = timeline.get("clips") or []
    out = []
    for i, (c, (_, start, end)) in enumerate(zip(raw, normalized), start=1):
        flt = c.get("filter", "none")
        if flt not in FILTERS:
            raise TimelineError(f"Clip {i}: unknown filter. Use one of: {', '.join(FILTERS)}.")
        tr = c.get("transition", "none")
        if tr not in TRANSITIONS:
            raise TimelineError(f"Clip {i}: unknown transition. Use one of: {', '.join(TRANSITIONS)}.")
        out.append({"filter": flt,
                    "brightness": _num_in(c.get("brightness"), 0.0, -0.5, 0.5, f"Clip {i}: brightness"),
                    "contrast": _num_in(c.get("contrast"), 1.0, 0.5, 2.0, f"Clip {i}: contrast"),
                    "saturation": _num_in(c.get("saturation"), 1.0, 0.0, 3.0, f"Clip {i}: saturation"),
                    "transition": tr, "duration": _num_in(c.get("transition_duration"), 0.5, 0.1, 2.0, f"Clip {i}: transition length"),
                    "tin": None, "tout": None})
    for i, fx in enumerate(out):
        colour = TRANSITIONS[fx["transition"]]
        if colour is None:
            continue
        d = fx["duration"]
        length = normalized[i][2] - normalized[i][1]
        nxt = normalized[i + 1][2] - normalized[i + 1][1] if i + 1 < len(out) else None
        if d > length / 2 + 0.001 or (nxt is not None and d > nxt / 2 + 0.001):
            raise TimelineError(f"Clip {i + 1}: the transition is longer than half of the clip. Shorten it.")
        fx["tout"] = (colour, d)
        if i + 1 < len(out):
            out[i + 1]["tin"] = (colour, d)
    for fx in out:
        fx.pop("transition"); fx.pop("duration")
    return out


def validate_audio_tracks(tracks: list, sources: dict[int, dict], total_seconds: float) -> list[dict]:
    """Background music / extra audio. start/end = part of the source file; at = where it begins on the timeline."""
    if not tracks:
        return []
    if not isinstance(tracks, list) or len(tracks) > MAX_AUDIO_TRACKS:
        raise TimelineError(f"At most {MAX_AUDIO_TRACKS} audio tracks are allowed.")
    out = []
    for i, t in enumerate(tracks, start=1):
        if not isinstance(t, dict):
            raise TimelineError(f"Audio {i} is not valid.")
        rid = t.get("recording_id")
        src = sources.get(rid) if isinstance(rid, int) and not isinstance(rid, bool) else None
        if src is None:
            raise TimelineError(f"Audio {i} uses a file that does not exist.")
        if not src.get("has_audio"):
            raise TimelineError(f"Audio {i}: the file has no sound.")
        start = _num_in(t.get("start"), 0.0, 0, 1e6, f"Audio {i}: start")
        end = _num_in(t.get("end"), src["duration"], 0, 1e6, f"Audio {i}: end")
        at = _num_in(t.get("at"), 0.0, 0, 1e6, f"Audio {i}: position")
        if end <= start or end - start < MIN_CLIP_SECONDS:
            raise TimelineError(f"Audio {i}: the end must be after the start.")
        if end > src["duration"] + 0.05:
            raise TimelineError(f"Audio {i}: ends at {end:.1f} s but the file is only {src['duration']:.1f} s long.")
        end = min(end, float(src["duration"]))
        if at >= total_seconds:
            raise TimelineError(f"Audio {i} starts after the end of the video ({total_seconds:.1f} s).")
        volume = _num_in(t.get("volume"), 1.0, 0, 2, f"Audio {i}: volume")
        fi = _num_in(t.get("fade_in"), 0.0, 0, 30, f"Audio {i}: fade in")
        fo = _num_in(t.get("fade_out"), 0.0, 0, 30, f"Audio {i}: fade out")
        length = min(end - start, total_seconds - at)  # the part that is actually heard
        if fi + fo > length + 0.001:
            raise TimelineError(f"Audio {i}: fade in + fade out is longer than the part that plays.")
        out.append({"recording_id": rid, "start": round(start, 3), "end": round(end, 3), "at": round(at, 3), "volume": volume,
                    "fade_in": fi, "fade_out": fo, "path": src["path"]})
    return out


def _fades(duration: float, fade_in: float, fade_out: float) -> str:
    f = ""
    if fade_in > 0:
        f += f",afade=t=in:st=0:d={fade_in:.3f}"
    if fade_out > 0:
        f += f",afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}"
    return f


def validate_texts(texts: list, total_seconds: float) -> list[dict]:
    """Check text/subtitle overlays (times are on the timeline, in seconds). Returns normalized dicts or raises TimelineError."""
    if not texts:
        return []
    if not isinstance(texts, list) or len(texts) > MAX_TEXTS:
        raise TimelineError(f"At most {MAX_TEXTS} text items are allowed.")
    out = []
    for i, t in enumerate(texts, start=1):
        if not isinstance(t, dict):
            raise TimelineError(f"Text {i} is not valid.")
        text = t.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 300:
            raise TimelineError(f"Text {i} must have 1-300 characters.")
        start, end = t.get("start"), t.get("end")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (start, end)):
            raise TimelineError(f"Text {i} needs numeric start and end times.")
        start, end = float(start), float(end)
        if start < 0 or end <= start:
            raise TimelineError(f"Text {i}: the end must be after the start.")
        if start >= total_seconds:
            raise TimelineError(f"Text {i} starts after the end of the video ({total_seconds:.1f} s).")
        position = t.get("position", "bottom")
        if position not in POSITIONS:
            raise TimelineError(f"Text {i}: position must be top, center or bottom.")
        size = t.get("size", 36)
        if isinstance(size, bool) or not isinstance(size, int) or not 12 <= size <= 120:
            raise TimelineError(f"Text {i}: size must be between 12 and 120.")
        color = t.get("color", "#ffffff")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise TimelineError(f"Text {i}: color must look like #ffffff.")
        out.append({"text": text.strip(), "start": round(start, 3), "end": round(min(end, total_seconds), 3), "position": position,
                    "size": size, "color": color, "box": bool(t.get("box", True))})
    return out


def find_font() -> str:
    override = os.getenv("FONT_FILE")
    for candidate in ([override] if override else []) + list(FONT_CANDIDATES):
        if candidate and Path(candidate).is_file():
            return candidate
    raise RenderError("No font is installed on the worker, so text cannot be drawn.")


def normalize_settings(resolution: str = "720p", fps: int = 30, quality: str = "medium") -> dict:
    if resolution not in RESOLUTIONS:
        raise TimelineError(f"Resolution must be one of: {', '.join(RESOLUTIONS)}.")
    if fps not in ALLOWED_FPS:
        raise TimelineError(f"Frame rate must be one of: {', '.join(map(str, ALLOWED_FPS))}.")
    if quality not in QUALITY_CRF:
        raise TimelineError(f"Quality must be one of: {', '.join(QUALITY_CRF)}.")
    return {"resolution": resolution, "fps": fps, "quality": quality}


def _filter_path(path: Path | str) -> str:
    """Quote a file path for use inside an ffmpeg filter option."""
    return "'" + str(path).replace("\\", "/").replace("'", "").replace(":", "\\:") + "'"


def build_command(clips: list[Clip], output: Path, settings: dict, preset: str = "veryfast",
                  text_files: list[tuple[Path, dict]] | None = None, font_file: str | None = None,
                  audio_tracks: list[dict] | None = None) -> list[str]:
    """Build the ffmpeg argument list (never a shell string, so file names cannot inject anything)."""
    width, height = RESOLUTIONS[settings["resolution"]]
    fps, crf = settings["fps"], QUALITY_CRF[settings["quality"]]
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-progress", "pipe:1", "-nostats"]
    for clip in clips:
        cmd += ["-i", str(clip.path)]
    tracks = audio_tracks or []
    for t in tracks:
        cmd += ["-i", str(t["path"])]
    parts, labels = [], []
    for i, c in enumerate(clips):
        s, e = f"{c.start:.3f}", f"{c.end:.3f}"
        fx = c.vfx or {}
        look = []  # colour work happens on the picture only, before the black bars are added
        if FILTERS.get(fx.get("filter", "none")):
            look.append(FILTERS[fx["filter"]])
        b, ct, sat = fx.get("brightness", 0.0), fx.get("contrast", 1.0), fx.get("saturation", 1.0)
        if abs(b) > 1e-6 or abs(ct - 1.0) > 1e-6 or abs(sat - 1.0) > 1e-6:
            look.append(f"eq=brightness={b:.3f}:contrast={ct:.3f}:saturation={sat:.3f}")
        dips = ""
        if fx.get("tin"):
            dips += f",fade=t=in:st=0:d={fx['tin'][1]:.3f}:color={fx['tin'][0]}"
        if fx.get("tout"):
            dips += f",fade=t=out:st={max(0.0, c.duration - fx['tout'][1]):.3f}:d={fx['tout'][1]:.3f}:color={fx['tout'][0]}"
        parts.append(
            f"[{i}:v:0]trim=start={s}:end={e},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease{''.join(',' + x for x in look)},"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{dips},fps={fps},format=yuv420p[v{i}]")
        if c.has_audio:
            vol = f",volume={c.volume:.3f}" if abs(c.volume - 1.0) > 1e-6 else ""
            parts.append(f"[{i}:a:0]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,aresample=48000,"
                         f"aformat=sample_fmts=fltp:channel_layouts=stereo{vol}{_fades(c.duration, max(c.fade_in, (fx.get('tin') or (0, 0))[1]), max(c.fade_out, (fx.get('tout') or (0, 0))[1]))}[a{i}]")
        else:  # silent clip so concat still gets an audio stream for every segment
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={c.duration:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    texts = text_files or []
    parts.append(f"{''.join(labels)}concat=n={len(clips)}:v=1:a=1[{'cv' if texts else 'outv'}][{'ca' if tracks else 'outa'}]")
    if tracks:
        mix = ["[ca]"]
        for j, t in enumerate(tracks):
            idx, dur = len(clips) + j, t["end"] - t["start"]
            vol = f",volume={t['volume']:.3f}" if abs(t["volume"] - 1.0) > 1e-6 else ""
            delay = int(round(t["at"] * 1000))
            parts.append(f"[{idx}:a:0]atrim=start={t['start']:.3f}:end={t['end']:.3f},asetpts=PTS-STARTPTS,aresample=48000,"
                         f"aformat=sample_fmts=fltp:channel_layouts=stereo{vol}{_fades(dur, t['fade_in'], t['fade_out'])},adelay=delays={delay}:all=1[m{j}]")
            mix.append(f"[m{j}]")
        # duration=first: the sound ends with the video; normalize=0 keeps the volumes exactly as set; alimiter prevents clipping.
        parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.95[outa]")
    if texts:
        draws = []
        for path, t in texts:
            y = {"top": "h*0.06", "center": "(h-text_h)/2", "bottom": "h-text_h-h*0.07"}[t["position"]]
            fsize = max(8, round(t["size"] * height / 720))
            box = f":box=1:boxcolor=black@0.55:boxborderw={max(4, fsize // 3)}" if t["box"] else ""
            draws.append(f"drawtext=fontfile={_filter_path(font_file or '')}:textfile={_filter_path(path)}:expansion=none:fontcolor={t['color']}"
                         f":fontsize={fsize}:x=(w-text_w)/2:y={y}{box}:enable='between(t,{t['start']:.3f},{t['end']:.3f})'")
        parts.append(f"[cv]{','.join(draws)}[outv]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-f", "mp4", str(output)]
    return cmd


def render(clips: list[Clip], output: Path, settings: dict, report: Callable[[int], None] | None = None, timeout: int = 900,
           texts: list[dict] | None = None, audio_tracks: list[dict] | None = None) -> None:
    """Run ffmpeg and report progress 0-95. Raises RenderError with a short, safe message."""
    total = sum(c.duration for c in clips)
    if texts:
        font = find_font()
        with tempfile.TemporaryDirectory(prefix="reel-text-") as tmpdir:  # text goes through files, so quotes/colons in it cannot break the filter
            files = []
            for i, t in enumerate(texts):
                f = Path(tmpdir) / f"t{i}.txt"
                f.write_text(t["text"], encoding="utf-8")
                files.append((f, t))
            _run(build_command(clips, output, settings, text_files=files, font_file=font, audio_tracks=audio_tracks), total, output, report, timeout)
        return
    _run(build_command(clips, output, settings, audio_tracks=audio_tracks), total, output, report, timeout)


def _run(cmd: list[str], total: float, output: Path, report: Callable[[int], None] | None, timeout: int) -> None:
    import time
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise RenderError("ffmpeg is not installed on the worker.")
    deadline = time.monotonic() + timeout
    try:
        for line in proc.stdout:  # "-progress pipe:1" prints key=value lines
            if time.monotonic() > deadline:
                proc.kill()
                raise RenderError("Rendering took too long and was stopped.")
            if line.startswith("out_time_us=") and report and total > 0:
                try:
                    done = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                report(max(0, min(95, int(done / total * 95))))
        proc.wait(timeout=30)
    except BaseException:
        proc.kill()
        proc.wait()
        output.unlink(missing_ok=True)
        raise
    if proc.returncode != 0:
        tail = (proc.stderr.read() or "").strip().splitlines()[-1:] or ["unknown error"]
        output.unlink(missing_ok=True)
        raise RenderError("Rendering failed: " + tail[0][:200])

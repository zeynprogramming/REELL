import shutil
import subprocess
import pytest
from app.worker.probe import ProbeError, probe_video, summarize

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg is not installed")

def test_summarize_accepts_a_normal_video():
    info = summarize({"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001"}, {"codec_type": "audio", "codec_name": "aac"}],
                      "format": {"duration": "61.5", "format_name": "mov,mp4", "bit_rate": "4000000", "size": "123"}})
    assert info["duration_seconds"] == 61.5 and info["fps"] == 29.97 and info["has_audio"] and info["video_codec"] == "h264"

def test_summarize_rejects_unusable_files():
    with pytest.raises(ProbeError):
        summarize({"streams": [{"codec_type": "audio"}], "format": {"duration": "3"}})
    with pytest.raises(ProbeError):
        summarize({"streams": [{"codec_type": "video"}], "format": {}})
    with pytest.raises(ProbeError):
        summarize({"streams": [{"codec_type": "video"}], "format": {"duration": "0"}})
    with pytest.raises(ProbeError):  # cover art is not a video
        summarize({"streams": [{"codec_type": "video", "disposition": {"attached_pic": 1}}], "format": {"duration": "3"}})

@needs_ffmpeg
def test_real_ffprobe_on_generated_video(tmp_path):
    path = tmp_path / "t.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15", "-pix_fmt", "yuv420p", str(path)], check=True)
    info = probe_video(path)
    assert (info["width"], info["height"]) == (320, 240) and 1.9 < info["duration_seconds"] < 2.2 and not info["has_audio"]

@needs_ffmpeg
def test_real_ffprobe_rejects_corrupt_file_without_leaking_path(tmp_path):
    path = tmp_path / "bad.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x01" * 500)
    with pytest.raises(ProbeError) as info:
        probe_video(path)
    assert str(tmp_path) not in str(info.value)

def test_summarize_audio_only_needs_permission():
    data = {"streams": [{"codec_type": "audio", "codec_name": "mp3"}], "format": {"duration": "30.5", "format_name": "mp3"}}
    with pytest.raises(ProbeError):
        summarize(data)
    info = summarize(data, allow_audio_only=True)
    assert info["audio_only"] and info["has_audio"] and info["duration_seconds"] == 30.5 and info["width"] is None

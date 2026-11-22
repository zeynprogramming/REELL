import shutil
import subprocess
import pytest
from conftest import make_user, login
from app.editing import render
from test_jobs import real_video, upload

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg is not installed")


def validated(client, headers, tmp_path, seconds=4):
    rec = upload(client, headers, real_video(tmp_path, seconds), name=f"s{seconds}.mp4")
    client.post("/api/jobs", json={"recording_id": rec["id"], "job_type": "video_validation"}, headers=headers)
    return rec["id"]


def test_validate_timeline_rules():
    src = {1: {"duration": 6.0}}
    assert render.validate_timeline({"clips": [{"recording_id": 1, "start": 0, "end": 2}]}, src) == [(1, 0.0, 2.0)]
    for bad in ({"clips": []}, {"clips": [{"recording_id": 1, "start": 5, "end": 9}]}, {"clips": [{"recording_id": 2, "start": 0, "end": 1}]},
                {"clips": [{"recording_id": 1, "start": 3, "end": 3}]}, {"clips": [{"recording_id": 1, "start": -1, "end": 2}]}):
        with pytest.raises(render.TimelineError):
            render.validate_timeline(bad, src)


def test_build_command_is_an_argument_list():
    from pathlib import Path
    clips = [render.Clip(1, 0, 2, Path("/x/a b; rm -rf.mp4"), True), render.Clip(2, 1, 3, Path("/x/b.mp4"), False)]
    cmd = render.build_command(clips, Path("/x/out.mp4"), render.normalize_settings("720p", 30, "medium"))
    assert isinstance(cmd, list) and "/x/a b; rm -rf.mp4" in cmd and "concat=n=2:v=1:a=1" in " ".join(cmd) and "anullsrc" in " ".join(cmd)


def test_viewer_cannot_change_projects(client, admin_headers, viewer_headers):
    assert client.post("/api/projects", json={"name": "x"}, headers=viewer_headers).status_code == 403
    assert client.get("/api/projects", headers=viewer_headers).status_code == 200
    assert client.get("/api/projects").status_code == 401


def test_project_crud_and_validation(client, admin_headers, tmp_path):
    rid = validated(client, admin_headers, tmp_path)
    created = client.post("/api/projects", json={"name": "Lesson cut", "timeline": {"clips": [{"recording_id": rid, "start": 0, "end": 2}]}}, headers=admin_headers)
    assert created.status_code == 201 and created.json()["duration_seconds"] == 2
    pid = created.json()["id"]
    assert client.put(f"/api/projects/{pid}", json={"name": "Cut 2", "timeline": {"clips": [{"recording_id": rid, "start": 1, "end": 99}]}}, headers=admin_headers).status_code == 422
    assert client.put(f"/api/projects/{pid}", json={"name": "Cut 2", "timeline": {"clips": [{"recording_id": 999, "start": 0, "end": 1}]}}, headers=admin_headers).status_code == 422
    saved = client.put(f"/api/projects/{pid}", json={"name": "Cut 2", "timeline": {"clips": [{"recording_id": rid, "start": 0, "end": 1}, {"recording_id": rid, "start": 2, "end": 3}]}}, headers=admin_headers).json()
    assert saved["name"] == "Cut 2" and saved["duration_seconds"] == 2
    assert [p["clip_count"] for p in client.get("/api/projects", headers=admin_headers).json()] == [2]
    assert client.delete(f"/api/projects/{pid}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=admin_headers).status_code == 404


def test_export_rejects_empty_and_bad_settings(client, admin_headers):
    pid = client.post("/api/projects", json={"name": "Empty"}, headers=admin_headers).json()["id"]
    assert client.post(f"/api/projects/{pid}/export", json={}, headers=admin_headers).status_code == 422


@needs_ffmpeg
def test_export_end_to_end(client, admin_headers, tmp_path):
    rid = validated(client, admin_headers, tmp_path, seconds=4)
    tl = {"clips": [{"recording_id": rid, "start": 0, "end": 1.5}, {"recording_id": rid, "start": 2.5, "end": 4}]}
    pid = client.post("/api/projects", json={"name": "Two parts", "timeline": tl}, headers=admin_headers).json()["id"]
    bad = client.post(f"/api/projects/{pid}/export", json={"resolution": "8k"}, headers=admin_headers)
    assert bad.status_code == 422
    job = client.post(f"/api/projects/{pid}/export", json={"resolution": "480p", "fps": 25, "quality": "low"}, headers=admin_headers).json()  # inline mode: already ran
    assert job["status"] == "completed", job
    out = job["result"]
    assert out["height"] == 480 and 2.5 < out["duration_seconds"] < 3.6
    rec = client.get(f"/api/recordings/{out['recording_id']}", headers=admin_headers).json()
    assert rec["status"] == "ready" and rec["filename"] == "Two parts (export).mp4"


def test_validate_texts_rules():
    ok = render.validate_texts([{"text": " Hello ", "start": 0, "end": 99, "position": "top"}], 5.0)
    assert ok[0]["text"] == "Hello" and ok[0]["end"] == 5.0 and ok[0]["color"] == "#ffffff"
    for bad in ([{"text": "x", "start": 6, "end": 7}], [{"text": "x", "start": 0, "end": 1, "color": "red"}], [{"text": "", "start": 0, "end": 1}],
                [{"text": "x", "start": 1, "end": 1}], [{"text": "x", "start": 0, "end": 1, "size": 500}], [{"text": "x", "start": 0, "end": 1, "position": "left"}]):
        with pytest.raises(render.TimelineError):
            render.validate_texts(bad, 5.0)


def test_project_rejects_bad_text(client, admin_headers, tmp_path):
    rid = validated(client, admin_headers, tmp_path)
    clip = {"recording_id": rid, "start": 0, "end": 2}
    r = client.post("/api/projects", json={"name": "T", "timeline": {"clips": [clip], "texts": [{"text": "hi", "start": 0, "end": 1, "color": "red"}]}}, headers=admin_headers)
    assert r.status_code == 422
    r = client.post("/api/projects", json={"name": "T", "timeline": {"clips": [clip], "texts": [{"text": "hi", "start": 0, "end": 1}]}}, headers=admin_headers)
    assert r.status_code == 201 and r.json()["timeline"]["texts"][0]["position"] == "bottom"


@needs_ffmpeg
def test_export_with_text_end_to_end(client, admin_headers, tmp_path):
    rid = validated(client, admin_headers, tmp_path, seconds=4)
    tl = {"clips": [{"recording_id": rid, "start": 0, "end": 3}], "texts": [{"text": "Բարև — it's \"quoted\": 100%", "start": 0.5, "end": 2, "position": "center"}]}
    pid = client.post("/api/projects", json={"name": "With text", "timeline": tl}, headers=admin_headers).json()["id"]
    job = client.post(f"/api/projects/{pid}/export", json={"resolution": "480p", "fps": 25, "quality": "low"}, headers=admin_headers).json()
    assert job["status"] == "completed", job
    assert job["result"]["texts"] == 1


def test_clip_audio_and_track_rules():
    tl = {"clips": [{"recording_id": 1, "start": 0, "end": 4, "volume": 0.5, "fade_in": 1, "fade_out": 1}]}
    norm = render.validate_timeline(tl, {1: {"duration": 6.0}})
    assert render.clip_audio_settings(tl, norm) == [(0.5, 1.0, 1.0)]
    for bad in ({"volume": 3}, {"volume": -1}, {"fade_in": 3, "fade_out": 3}, {"fade_in": "x"}):
        t2 = {"clips": [{"recording_id": 1, "start": 0, "end": 4, **bad}]}
        with pytest.raises(render.TimelineError):
            render.clip_audio_settings(t2, render.validate_timeline(t2, {1: {"duration": 6.0}}))
    src = {3: {"duration": 10.0, "has_audio": True, "path": "/x/m.mp3"}, 4: {"duration": 10.0, "has_audio": False, "path": "/x/s.mp4"}}
    ok = render.validate_audio_tracks([{"recording_id": 3, "start": 0, "end": 99 - 89, "at": 1, "volume": 0.5}], src, 5.0)
    assert ok[0]["at"] == 1.0 and ok[0]["volume"] == 0.5
    for bad in ({"recording_id": 9, "end": 2}, {"recording_id": 4, "end": 2}, {"recording_id": 3, "end": 50}, {"recording_id": 3, "end": 5, "at": 9},
                {"recording_id": 3, "end": 5, "volume": 5}, {"recording_id": 3, "end": 5, "fade_in": 4, "fade_out": 4}):
        with pytest.raises(render.TimelineError):
            render.validate_audio_tracks([bad], src, 5.0)


def test_build_command_mixes_audio_track():
    from pathlib import Path
    clip = render.Clip(1, 0, 3, Path("/x/a.mp4"), True, volume=0.5, fade_in=0.5, fade_out=0.5)
    track = {"recording_id": 3, "start": 1.0, "end": 9.0, "at": 1.0, "volume": 0.8, "fade_in": 1.0, "fade_out": 1.0, "path": Path("/x/m.mp3")}
    cmd = render.build_command([clip], Path("/x/o.mp4"), render.normalize_settings(), audio_tracks=[track])
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert cmd.count("-i") == 2 and "amix=inputs=2:duration=first:normalize=0" in graph and "adelay=delays=1000:all=1" in graph and "volume=0.500" in graph and "afade=t=in" in graph


@needs_ffmpeg
def test_export_with_clip_volume_and_music(client, admin_headers, tmp_path):
    vid = validated(client, admin_headers, tmp_path, seconds=4)
    wav = tmp_path / "music.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-ar", "44100", str(wav)], check=True)
    music = upload(client, admin_headers, wav.read_bytes(), name="music.wav")
    assert music["id"]
    assert client.post("/api/jobs", json={"recording_id": music["id"], "job_type": "video_validation"}, headers=admin_headers).json()["status"] == "completed"
    tl = {"clips": [{"recording_id": vid, "start": 0, "end": 3, "volume": 0.5, "fade_in": 0.5, "fade_out": 0.5}],
          "audio": [{"recording_id": music["id"], "start": 0, "end": 6, "at": 0.5, "volume": 0.7, "fade_in": 1, "fade_out": 1}]}
    pid = client.post("/api/projects", json={"name": "Music", "timeline": tl}, headers=admin_headers).json()["id"]
    job = client.post(f"/api/projects/{pid}/export", json={"resolution": "480p", "fps": 25, "quality": "low"}, headers=admin_headers).json()
    assert job["status"] == "completed", job
    assert job["result"]["audio_tracks"] == 1 and 2.5 < job["result"]["duration_seconds"] < 3.6


def test_audio_files_can_be_uploaded_but_garbage_cannot(client, admin_headers):
    assert upload(client, admin_headers, b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 64, name="a.wav")["id"]
    r = client.post("/api/recordings/upload", params={"filename": "b.mp3"}, content=b"MZ\x90\x00" + b"\x00" * 40, headers={**admin_headers, "Content-Type": "application/octet-stream"})
    assert r.status_code == 415


def _fx(clips, durations=(6.0, 4.0)):
    src = {1: {"duration": durations[0]}, 2: {"duration": durations[1]}}
    tl = {"clips": clips}
    norm = render.validate_timeline(tl, src)
    return render.clip_video_settings(tl, norm)


def test_picture_effect_rules():
    fx = _fx([{"recording_id": 1, "start": 0, "end": 3, "filter": "sepia", "brightness": 0.2, "transition": "fade_black", "transition_duration": 0.5},
              {"recording_id": 2, "start": 0, "end": 2}])
    assert fx[0]["filter"] == "sepia" and fx[0]["tout"] == ("black", 0.5) and fx[1]["tin"] == ("black", 0.5) and fx[1]["tout"] is None
    assert _fx([{"recording_id": 1, "start": 0, "end": 3}])[0] == {"filter": "none", "brightness": 0.0, "contrast": 1.0, "saturation": 1.0, "tin": None, "tout": None}
    for bad in ({"filter": "x"}, {"brightness": 2}, {"contrast": 0}, {"saturation": 9}, {"transition": "zoom"}, {"transition": "fade_black", "transition_duration": 2.0}):
        with pytest.raises(render.TimelineError):
            _fx([{"recording_id": 1, "start": 0, "end": 3, **bad}])
    with pytest.raises(render.TimelineError):  # the next clip is too short for the dip
        _fx([{"recording_id": 1, "start": 0, "end": 3, "transition": "fade_white", "transition_duration": 1.0}, {"recording_id": 2, "start": 0, "end": 1.5}])


def test_build_command_applies_effects():
    from pathlib import Path
    clips = [render.Clip(1, 0, 3, Path("/x/a.mp4"), True, vfx={"filter": "grayscale", "brightness": 0.1, "contrast": 1.2, "saturation": 1.0, "tin": None, "tout": ("black", 0.5)}),
             render.Clip(2, 0, 2, Path("/x/b.mp4"), True, vfx={"tin": ("black", 0.5), "tout": None})]
    graph = (lambda c: c[c.index("-filter_complex") + 1])(render.build_command(clips, Path("/x/o.mp4"), render.normalize_settings()))
    assert "hue=s=0" in graph and "eq=brightness=0.100:contrast=1.200" in graph and "fade=t=out:st=2.500:d=0.500:color=black" in graph and "fade=t=in:st=0:d=0.500:color=black" in graph


def test_project_rejects_unknown_filter(client, admin_headers, tmp_path):
    rid = validated(client, admin_headers, tmp_path)
    r = client.post("/api/projects", json={"name": "F", "timeline": {"clips": [{"recording_id": rid, "start": 0, "end": 2, "filter": "glitch"}]}}, headers=admin_headers)
    assert r.status_code == 422


@needs_ffmpeg
def test_export_with_filters_and_transition(client, admin_headers, tmp_path):
    rid = validated(client, admin_headers, tmp_path, seconds=4)
    tl = {"clips": [{"recording_id": rid, "start": 0, "end": 2, "filter": "sepia", "brightness": 0.1, "contrast": 1.2, "transition": "fade_black", "transition_duration": 0.5},
                    {"recording_id": rid, "start": 2, "end": 4, "filter": "blur", "saturation": 0.5}]}
    pid = client.post("/api/projects", json={"name": "Look", "timeline": tl}, headers=admin_headers).json()["id"]
    job = client.post(f"/api/projects/{pid}/export", json={"resolution": "480p", "fps": 25, "quality": "low"}, headers=admin_headers).json()
    assert job["status"] == "completed", job
    assert 3.6 < job["result"]["duration_seconds"] < 4.4  # transitions never change the length


def test_project_history_and_restore(client, admin_headers, tmp_path):
    rid = validated(client, admin_headers, tmp_path)
    one = {"clips": [{"recording_id": rid, "start": 0, "end": 2}]}
    two = {"clips": [{"recording_id": rid, "start": 0, "end": 1}, {"recording_id": rid, "start": 2, "end": 3}]}
    pid = client.post("/api/projects", json={"name": "H", "timeline": one}, headers=admin_headers).json()["id"]
    assert [v["label"] for v in client.get(f"/api/projects/{pid}/versions", headers=admin_headers).json()] == ["Created"]
    client.put(f"/api/projects/{pid}", json={"name": "H2", "timeline": two}, headers=admin_headers)
    client.put(f"/api/projects/{pid}", json={"name": "H2", "timeline": two}, headers=admin_headers)  # same content: no new version
    versions = client.get(f"/api/projects/{pid}/versions", headers=admin_headers).json()
    assert [v["clip_count"] for v in versions] == [2, 1]
    # autosave changes the project but adds no history entry
    client.put(f"/api/projects/{pid}?autosave=true", json={"name": "H3", "timeline": one}, headers=admin_headers)
    assert len(client.get(f"/api/projects/{pid}/versions", headers=admin_headers).json()) == 2
    assert client.get(f"/api/projects/{pid}", headers=admin_headers).json()["name"] == "H3"
    # restore the first version; the state before the restore is kept
    restored = client.post(f"/api/projects/{pid}/versions/{versions[1]['id']}/restore", headers=admin_headers).json()
    assert restored["name"] == "H" and len(restored["timeline"]["clips"]) == 1
    labels = [v["label"] for v in client.get(f"/api/projects/{pid}/versions", headers=admin_headers).json()]
    assert labels[0] == "Before restore"
    other = client.post("/api/projects", json={"name": "O"}, headers=admin_headers).json()["id"]
    assert client.post(f"/api/projects/{other}/versions/{versions[0]['id']}/restore", headers=admin_headers).status_code == 404


def test_history_is_trimmed_and_viewers_cannot_use_it(client, admin_headers, viewer_headers):
    pid = client.post("/api/projects", json={"name": "T0"}, headers=admin_headers).json()["id"]
    for i in range(1, 36):
        client.put(f"/api/projects/{pid}", json={"name": f"T{i}"}, headers=admin_headers)
    versions = client.get(f"/api/projects/{pid}/versions", headers=admin_headers).json()
    assert len(versions) == 30 and versions[0]["name"] == "T35"
    assert client.post(f"/api/projects/{pid}/versions/{versions[0]['id']}/restore", headers=viewer_headers).status_code == 403

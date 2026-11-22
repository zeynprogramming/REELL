import os
import time
from pathlib import Path
from app.storage import LocalStorage, display_name, looks_like

def test_sniffing():
    assert looks_like(".mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4)
    assert looks_like(".webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 12)
    assert looks_like(".avi", b"RIFF\x00\x00\x00\x00AVI LIST")
    assert not looks_like(".mp4", b"MZ\x90\x00" + b"\x00" * 12)
    assert not looks_like(".exe", b"\x00" * 16)

def test_display_name_strips_paths_and_control_chars():
    assert display_name("../../etc/passwd.mp4") == "passwd.mp4"
    assert display_name("C:\\videos\\lesson.mp4") == "lesson.mp4"
    assert display_name("a\x00b\n.mp4") == "ab.mp4"
    assert len(display_name("x" * 400 + ".mp4")) <= 255

def test_path_for_blocks_traversal(tmp_path):
    s = LocalStorage(tmp_path); s.ensure()
    assert s.path_for("../../etc/passwd") is None
    assert s.path_for("/etc/passwd") is None
    assert s.path_for("tmp/x.part") is None
    assert s.path_for(None) is None
    assert s.path_for("recordings/a.mp4") == (tmp_path / "recordings" / "a.mp4").resolve()

def test_commit_delete_and_purge(tmp_path):
    s = LocalStorage(tmp_path); s.ensure()
    tmp = s.tmp_path(); tmp.write_bytes(b"data")
    key = s.new_key(".mp4"); s.commit(tmp, key)
    assert not tmp.exists() and (tmp_path / key).read_bytes() == b"data"
    assert s.delete(key) and not s.delete(key)
    old = s.tmp_path(); old.write_bytes(b"x"); os.utime(old, (time.time() - 90000,) * 2)
    fresh = s.tmp_path(); fresh.write_bytes(b"x")
    assert s.purge_stale_tmp() == 1 and fresh.exists() and not old.exists()

def test_sniffing_audio():
    assert looks_like(".mp3", b"ID3\x04\x00" + b"\x00" * 11) and looks_like(".mp3", b"\xff\xfb\x90\x00" + b"\x00" * 12)
    assert looks_like(".wav", b"RIFF\x00\x00\x00\x00WAVEfmt ")
    assert not looks_like(".wav", b"RIFF\x00\x00\x00\x00AVI LIST")
    assert looks_like(".m4a", b"\x00\x00\x00\x20ftypM4A ") and looks_like(".ogg", b"OggS" + b"\x00" * 12) and looks_like(".aac", b"\xff\xf1" + b"\x00" * 14)
    assert not looks_like(".mp3", b"MZ\x90\x00" + b"\x00" * 12)

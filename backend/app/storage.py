"""File storage for uploaded recordings (Phase 5).

Files live under UPLOAD_DIR using server-generated names; the user's filename is only
ever stored as display text. `LocalStorage` is the single place that touches the disk, so a
cloud backend (S3, GCS) can replace it in a later phase without changing the routers.
"""
import os
import shutil
import time
import uuid
from pathlib import Path

AUDIO_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg"}
VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/x-m4v",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}
ALLOWED_TYPES = {**VIDEO_TYPES, **AUDIO_TYPES}
_QT_ATOMS = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"}
HEAD_BYTES = 16


def looks_like(ext: str, head: bytes) -> bool:
    """Check the file's leading bytes against its extension (content sniffing, not trust in the name)."""
    if ext in (".mp4", ".m4v", ".mov"):
        return head[4:8] in _QT_ATOMS
    if ext in (".webm", ".mkv"):
        return head[:4] == b"\x1a\x45\xdf\xa3"
    if ext == ".avi":
        return head[:4] == b"RIFF" and head[8:12] == b"AVI "
    if ext == ".mp3":
        return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
    if ext == ".wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if ext == ".m4a":
        return head[4:8] == b"ftyp"
    if ext == ".aac":
        return len(head) > 1 and head[0] == 0xFF and head[1] & 0xF0 == 0xF0
    if ext == ".ogg":
        return head[:4] == b"OggS"
    return False


def max_upload_bytes() -> int:
    try:
        return max(1, int(os.getenv("MAX_UPLOAD_MB", "2048"))) * 1024 * 1024
    except ValueError:
        return 2048 * 1024 * 1024


def display_name(raw: str) -> str:
    """Reduce a client-supplied name to a safe display string (no directories, no control characters)."""
    name = raw.replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip().strip(".")
    return name[:255]


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def ensure(self) -> None:
        (self.root / "recordings").mkdir(parents=True, exist_ok=True)
        (self.root / "tmp").mkdir(parents=True, exist_ok=True)

    def new_key(self, ext: str) -> str:
        return f"recordings/{uuid.uuid4().hex}{ext}"

    def tmp_path(self) -> Path:
        return self.root / "tmp" / f"{uuid.uuid4().hex}.part"

    def path_for(self, key: str | None) -> Path | None:
        """Resolve a storage key to a file path, or None if it would leave the storage root."""
        if not key:
            return None
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root / "recordings"):
            return None
        return candidate

    def commit(self, tmp: Path, key: str) -> None:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, target)  # same filesystem (tmp lives under root), so this is atomic

    def delete(self, key: str | None) -> bool:
        path = self.path_for(key)
        if path is None or not path.is_file():
            return False
        path.unlink()
        return True

    def disk_free_bytes(self) -> int | None:
        try:
            return shutil.disk_usage(self.root).free
        except OSError:
            return None

    def purge_stale_tmp(self, older_than_seconds: int = 24 * 3600) -> int:
        removed = 0
        tmp_dir = self.root / "tmp"
        if not tmp_dir.is_dir():
            return 0
        cutoff = time.time() - older_than_seconds
        for item in tmp_dir.glob("*.part"):
            try:
                if item.stat().st_mtime < cutoff:
                    item.unlink(); removed += 1
            except OSError:
                pass
        return removed


def get_storage() -> LocalStorage:
    return LocalStorage(Path(os.getenv("UPLOAD_DIR", "./data/uploads")))

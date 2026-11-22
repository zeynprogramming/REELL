import hashlib
import logging
from pathlib import Path
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from .. import audit, models, schemas
from ..auth import get_current_user, require_write_access
from ..database import get_db
from ..security import create_download_token, decode_download_token
from ..storage import ALLOWED_TYPES, HEAD_BYTES, display_name, get_storage, looks_like, max_upload_bytes

log = logging.getLogger("reel.files")

# Signed-in users: reading is open to every role, uploading needs admin/editor (require_write_access).
router = APIRouter(prefix="/api", tags=["Files"], dependencies=[Depends(require_write_access)])
# Token-authorised file delivery (browsers cannot send an Authorization header from <video>/<a>).
public_router = APIRouter(prefix="/api/files", tags=["Files"])

CHUNK_LOG = 1024 * 1024


@router.get("/storage/summary", response_model=schemas.StorageSummary)
def storage_summary(db: Session = Depends(get_db)):
    files, total = db.query(func.count(models.Recording.id), func.coalesce(func.sum(models.Recording.file_size_bytes), 0)).filter(models.Recording.file_path.isnot(None)).one()
    return {
        "files": files or 0,
        "total_bytes": int(total or 0),
        "max_upload_bytes": max_upload_bytes(),
        "allowed_extensions": sorted(ALLOWED_TYPES),
        "disk_free_bytes": get_storage().disk_free_bytes(),
    }


@router.post("/recordings/upload", response_model=schemas.RecordingOut, status_code=201)
async def upload_recording(
    request: Request,
    filename: str = Query(..., min_length=1, max_length=255),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Receive a raw video body (not multipart) and stream it to disk, enforcing the size limit while reading."""
    name = display_name(filename)
    ext = Path(name).suffix.lower()
    if not name or ext not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_TYPES))}.")

    limit = max_upload_bytes()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail=f"File is larger than the {limit // (1024 * 1024)} MB limit.")

    storage = get_storage()
    storage.ensure()
    free = storage.disk_free_bytes()
    if declared and declared.isdigit() and free is not None and int(declared) > free:
        raise HTTPException(status_code=507, detail="Not enough free disk space on the server.")

    tmp = storage.tmp_path()
    digest = hashlib.sha256()
    size = 0
    head = b""
    stored_key: str | None = None
    try:
        with open(tmp, "wb") as out:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"File is larger than the {limit // (1024 * 1024)} MB limit.")
                if len(head) < HEAD_BYTES:
                    head = (head + chunk)[:HEAD_BYTES]
                digest.update(chunk)
                await run_in_threadpool(out.write, chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if not looks_like(ext, head):
            raise HTTPException(status_code=415, detail="The file content does not match its extension, so it was rejected.")

        checksum = digest.hexdigest()
        duplicate = db.query(models.Recording).filter(models.Recording.checksum_sha256 == checksum, models.Recording.file_path.isnot(None)).first()
        if duplicate:
            raise HTTPException(status_code=409, detail=f"This exact file was already uploaded as recording #{duplicate.id} ({duplicate.filename}).")

        stored_key = storage.new_key(ext)
        storage.commit(tmp, stored_key)
        recording = models.Recording(filename=name, status="uploaded", file_path=stored_key, file_size_bytes=size, content_type=ALLOWED_TYPES[ext], checksum_sha256=checksum)
        db.add(recording)
        try:
            db.commit()
        except Exception:
            db.rollback()
            storage.delete(stored_key)
            raise
        db.refresh(recording)
    finally:
        tmp.unlink(missing_ok=True)  # no-op after a successful commit (the file was moved)
    audit.record(db, "recording_uploaded", request, user_id=user.id, detail=f"recording_id={recording.id} bytes={size}")
    return recording


@router.get("/recordings/{item_id}/file-link", response_model=schemas.FileLink)
def file_link(item_id: int, download: bool = False, db: Session = Depends(get_db)):
    recording = db.get(models.Recording, item_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    path = get_storage().path_for(recording.file_path)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="No file is stored for this recording.")
    token, expires_in = create_download_token(recording.id, download)
    return {"url": f"/api/files/{token}", "expires_in": expires_in, "filename": recording.filename}


@public_router.get("/{token}")
def serve_file(token: str, db: Session = Depends(get_db)):
    try:
        payload = decode_download_token(token)
        recording_id = int(payload["rid"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status_code=403, detail="This link has expired or is invalid. Request a new one.")
    recording = db.get(models.Recording, recording_id)
    path = get_storage().path_for(recording.file_path) if recording else None
    if recording is None or path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    attachment = bool(payload.get("att"))
    # FileResponse supports HTTP Range requests, so the browser can seek inside a video.
    return FileResponse(
        path,
        media_type=recording.content_type or "application/octet-stream",
        filename=recording.filename,
        content_disposition_type="attachment" if attachment else "inline",
    )

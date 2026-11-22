"""Manual workspace: everything an editor can do by hand, without any AI service.

Typed metadata, chapters, tags, transcript and a log of where a video was published (recorded by a person;
REEL itself publishes nothing). Reading is open to every signed-in user, changes need admin/editor.
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from .. import audit, models, schemas
from ..auth import get_current_user, require_write_access
from ..database import get_db

router = APIRouter(prefix="/api", tags=["Manual workspace"], dependencies=[Depends(require_write_access)])


def _recording(db: Session, rid: int) -> models.Recording:
    rec = db.get(models.Recording, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return rec

def _loads(raw: str | None) -> list:
    try:
        data = json.loads(raw) if raw else []
    except ValueError:
        return []
    return data if isinstance(data, list) else []

def _latest(db: Session, model, rid: int):
    return db.query(model).filter(model.recording_id == rid).order_by(model.id.desc()).first()

def _meta_out(m: models.VideoMetadata | None) -> dict | None:
    if m is None:
        return None
    chapters = [c for c in _loads(m.chapters_json) if isinstance(c, dict) and isinstance(c.get("time_seconds"), int) and isinstance(c.get("title"), str) and c["title"].strip()]
    tags = [t for t in _loads(m.tags_json) if isinstance(t, str)]
    return {"id": m.id, "recording_id": m.recording_id, "title": m.title, "description": m.description, "tags": tags, "chapters": chapters}

def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="The change conflicts with existing data.")


@router.get("/recordings/{rid}/workspace", response_model=schemas.WorkspaceOut)
def workspace(rid: int, db: Session = Depends(get_db)):
    rec = _recording(db, rid)
    pubs = db.query(models.PublishedVideo).filter(models.PublishedVideo.recording_id == rid).order_by(models.PublishedVideo.id.desc()).all()
    return {"recording": rec, "metadata": _meta_out(_latest(db, models.VideoMetadata, rid)), "transcript": _latest(db, models.Transcript, rid), "publications": pubs}


@router.put("/recordings/{rid}/metadata", response_model=schemas.MetadataOut)
def save_metadata(rid: int, payload: schemas.MetadataSave, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = _recording(db, rid)
    chapters = sorted(payload.chapters, key=lambda c: c.time_seconds)
    times = [c.time_seconds for c in chapters]
    if len(times) != len(set(times)):
        raise HTTPException(status_code=422, detail="Two chapters have the same time. Give each chapter its own time.")
    if rec.duration_seconds is not None:
        late = next((c for c in chapters if c.time_seconds > rec.duration_seconds), None)
        if late is not None:
            raise HTTPException(status_code=422, detail=f"Chapter “{late.title}” starts after the end of the video ({rec.duration_seconds} s).")
    item = _latest(db, models.VideoMetadata, rid) or models.VideoMetadata(recording_id=rid)
    item.title = (payload.title or "").strip() or None
    item.description = (payload.description or "").strip() or None
    item.tags_json = json.dumps(payload.tags) if payload.tags else None
    item.chapters_json = json.dumps([c.model_dump() for c in chapters]) if chapters else None
    db.add(item); _commit(db); db.refresh(item)
    audit.record(db, "metadata_saved", request, user_id=user.id, detail=f"recording_id={rid}")
    return _meta_out(item)


@router.put("/recordings/{rid}/transcript", response_model=schemas.TranscriptOut)
def save_transcript(rid: int, payload: schemas.TranscriptSave, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    _recording(db, rid)
    item = _latest(db, models.Transcript, rid) or models.Transcript(recording_id=rid)
    item.language = (payload.language or "").strip() or None
    item.content = payload.content
    db.add(item); _commit(db); db.refresh(item)
    audit.record(db, "transcript_saved", request, user_id=user.id, detail=f"recording_id={rid} chars={len(item.content)}")
    return item


@router.post("/recordings/{rid}/publications", response_model=schemas.PublicationOut, status_code=201)
def log_publication(rid: int, payload: schemas.ManualPublication, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Records that a person published the video somewhere. REEL does not upload anything."""
    _recording(db, rid)
    item = models.PublishedVideo(recording_id=rid, platform=payload.platform, url=payload.url, visibility=payload.visibility, published_at=datetime.now(timezone.utc))
    db.add(item); _commit(db); db.refresh(item)
    audit.record(db, "publication_logged", request, user_id=user.id, detail=f"recording_id={rid} platform={payload.platform}")
    return item


@router.delete("/publications/{pid}", status_code=204)
def delete_publication(pid: int, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(models.PublishedVideo, pid)
    if item is None:
        raise HTTPException(status_code=404, detail="Publication record not found")
    db.delete(item); _commit(db)
    audit.record(db, "publication_deleted", request, user_id=user.id, detail=f"publication_id={pid}")
    return Response(status_code=204)


@router.patch("/consents/{cid}", response_model=schemas.ConsentOut)
def update_consent(cid: int, payload: schemas.ConsentUpdate, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(models.StudentConsent, cid)
    if item is None:
        raise HTTPException(status_code=404, detail="Consent record not found")
    item.photo_video_allowed = payload.photo_video_allowed
    item.checked_at = datetime.now(timezone.utc)
    _commit(db); db.refresh(item)
    audit.record(db, "consent_updated", request, user_id=user.id, detail=f"consent_id={cid} allowed={payload.photo_video_allowed}")
    return item


@router.delete("/consents/{cid}", status_code=204)
def delete_consent(cid: int, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(models.StudentConsent, cid)
    if item is None:
        raise HTTPException(status_code=404, detail="Consent record not found")
    db.delete(item); _commit(db)
    audit.record(db, "consent_deleted", request, user_id=user.id, detail=f"consent_id={cid}")
    return Response(status_code=204)

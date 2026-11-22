"""Editing projects (PRD Phase 7-8): save a timeline, reopen it, export it to MP4 in the background.

Reading is open to every signed-in user; changes need admin/editor (same rule as the rest of the API).
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from .. import audit, models, schemas
from ..auth import get_current_user, require_write_access
from ..database import get_db
from ..editing import render as editing
from ..queueing import QueueUnavailable, enqueue_job

router = APIRouter(prefix="/api/projects", tags=["Editing projects"], dependencies=[Depends(require_write_access)])


def _project(db: Session, pid: int) -> models.EditProject:
    item = db.get(models.EditProject, pid)
    if item is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return item


def _timeline(item: models.EditProject) -> dict:
    try:
        data = json.loads(item.timeline_json or "{}")
    except ValueError:
        data = {}
    clips = data.get("clips") if isinstance(data, dict) else None
    texts = data.get("texts") if isinstance(data, dict) else None
    audio = data.get("audio") if isinstance(data, dict) else None
    return {"clips": clips if isinstance(clips, list) else [], "texts": texts if isinstance(texts, list) else [], "audio": audio if isinstance(audio, list) else []}


MAX_VERSIONS = 30


def _snapshot(db: Session, item: models.EditProject, label: str) -> None:
    """Keep the current state as a version (skipped when it equals the latest one); only the newest MAX_VERSIONS are kept."""
    last = db.query(models.ProjectVersion).filter(models.ProjectVersion.project_id == item.id).order_by(models.ProjectVersion.id.desc()).first()
    if last and last.timeline_json == item.timeline_json and last.name == item.name:
        return
    db.add(models.ProjectVersion(project_id=item.id, label=label, name=item.name, timeline_json=item.timeline_json))
    db.flush()
    old = db.query(models.ProjectVersion.id).filter(models.ProjectVersion.project_id == item.id).order_by(models.ProjectVersion.id.desc()).offset(MAX_VERSIONS).all()
    if old:
        db.query(models.ProjectVersion).filter(models.ProjectVersion.id.in_([i for (i,) in old])).delete(synchronize_session=False)


def _duration(timeline: dict) -> float:
    return round(sum(max(0.0, float(c.get("end", 0)) - float(c.get("start", 0))) for c in timeline["clips"] if isinstance(c, dict)), 2)


def _out(item: models.EditProject) -> dict:
    tl = _timeline(item)
    total = sum(max(0.0, float(c.get("end", 0)) - float(c.get("start", 0))) for c in tl["clips"] if isinstance(c, dict))
    return {"id": item.id, "name": item.name, "timeline": tl, "duration_seconds": round(total, 2), "created_at": item.created_at, "updated_at": item.updated_at}


def _check_audio(db: Session, tracks: list[schemas.AudioTrack]) -> None:
    ids = {t.recording_id for t in tracks}
    found = {r.id: r for r in db.query(models.Recording).filter(models.Recording.id.in_(ids)).all()} if ids else {}
    for i, t in enumerate(tracks, start=1):
        rec = found.get(t.recording_id)
        if rec is None or not rec.file_path:
            raise HTTPException(status_code=422, detail=f"Audio {i} uses a file that does not exist.")
        if t.end <= t.start:
            raise HTTPException(status_code=422, detail=f"Audio {i}: the end must be after the start.")
        if rec.duration_seconds is not None and t.end > rec.duration_seconds + 1:
            raise HTTPException(status_code=422, detail=f"Audio {i}: ends at {t.end:.1f} s but the file is only {rec.duration_seconds} s long.")


def _check_clips(db: Session, clips: list[schemas.TimelineClip]) -> None:
    """Reject clips that point to missing recordings or go beyond the real video length (when it is known)."""
    ids = {c.recording_id for c in clips}
    found = {r.id: r for r in db.query(models.Recording).filter(models.Recording.id.in_(ids)).all()} if ids else {}
    for i, c in enumerate(clips, start=1):
        rec = found.get(c.recording_id)
        if rec is None or not rec.file_path:
            raise HTTPException(status_code=422, detail=f"Clip {i} uses a recording that does not exist or has no video file.")
        if c.end <= c.start:
            raise HTTPException(status_code=422, detail=f"Clip {i}: the end must be after the start.")
        if rec.duration_seconds is not None and c.end > rec.duration_seconds + 1:  # duration is stored in whole seconds
            raise HTTPException(status_code=422, detail=f"Clip {i}: ends at {c.end:.1f} s but the video is only {rec.duration_seconds} s long.")


@router.get("", response_model=list[schemas.ProjectSummary])
def list_projects(db: Session = Depends(get_db)):
    items = db.query(models.EditProject).order_by(models.EditProject.updated_at.desc(), models.EditProject.id.desc()).limit(200).all()
    return [{"id": p.id, "name": p.name, "clip_count": len(_timeline(p)["clips"]), "updated_at": p.updated_at} for p in items]


@router.post("", response_model=schemas.ProjectOut, status_code=201)
def create_project(payload: schemas.ProjectSave, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_clips(db, payload.timeline.clips)
    _check_audio(db, payload.timeline.audio)
    item = models.EditProject(name=payload.name.strip(), timeline_json=payload.timeline.model_dump_json(), created_by=user.id)
    db.add(item); db.flush()
    _snapshot(db, item, "Created")
    db.commit(); db.refresh(item)
    audit.record(db, "project_created", request, user_id=user.id, detail=f"project_id={item.id}")
    return _out(item)


@router.get("/{pid}", response_model=schemas.ProjectOut)
def get_project(pid: int, db: Session = Depends(get_db)):
    return _out(_project(db, pid))


@router.put("/{pid}", response_model=schemas.ProjectOut)
def save_project(pid: int, payload: schemas.ProjectSave, request: Request, autosave: bool = Query(False), user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """autosave=true overwrites the project quietly; it does not add a history entry (manual saves, exports and restores do)."""
    item = _project(db, pid)
    _check_clips(db, payload.timeline.clips)
    _check_audio(db, payload.timeline.audio)
    item.name = payload.name.strip()
    item.timeline_json = payload.timeline.model_dump_json()
    if not autosave:
        _snapshot(db, item, "Saved")
    db.commit(); db.refresh(item)
    if not autosave:
        audit.record(db, "project_saved", request, user_id=user.id, detail=f"project_id={pid} clips={len(payload.timeline.clips)}")
    return _out(item)


@router.get("/{pid}/versions", response_model=list[schemas.ProjectVersionOut])
def list_versions(pid: int, db: Session = Depends(get_db)):
    _project(db, pid)
    rows = db.query(models.ProjectVersion).filter(models.ProjectVersion.project_id == pid).order_by(models.ProjectVersion.id.desc()).limit(MAX_VERSIONS).all()
    out = []
    for v in rows:
        try:
            tl = json.loads(v.timeline_json)
        except ValueError:
            tl = {}
        clips = tl.get("clips") if isinstance(tl, dict) and isinstance(tl.get("clips"), list) else []
        out.append({"id": v.id, "label": v.label, "name": v.name, "clip_count": len(clips), "duration_seconds": _duration({"clips": clips}), "created_at": v.created_at})
    return out


@router.post("/{pid}/versions/{vid}/restore", response_model=schemas.ProjectOut)
def restore_version(pid: int, vid: int, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Put an older version back. The state before the restore is kept as a new version, so a restore can be undone."""
    item = _project(db, pid)
    version = db.get(models.ProjectVersion, vid)
    if version is None or version.project_id != pid:
        raise HTTPException(status_code=404, detail="Version not found")
    _snapshot(db, item, "Before restore")
    item.name, item.timeline_json = version.name, version.timeline_json
    db.commit(); db.refresh(item)
    audit.record(db, "project_restored", request, user_id=user.id, detail=f"project_id={pid} version_id={vid}")
    return _out(item)


@router.delete("/{pid}", status_code=204)
def delete_project(pid: int, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = _project(db, pid)
    db.delete(item); db.commit()
    audit.record(db, "project_deleted", request, user_id=user.id, detail=f"project_id={pid}")
    return Response(status_code=204)


@router.post("/{pid}/export", response_model=schemas.JobOut, status_code=201)
def export_project(pid: int, payload: schemas.ExportRequest, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Queue a background render. The finished MP4 appears as a new recording; progress is visible in the Processing Queue."""
    item = _project(db, pid)
    if not _timeline(item)["clips"]:
        raise HTTPException(status_code=422, detail="The timeline is empty. Add at least one clip before exporting.")
    try:
        settings = editing.normalize_settings(payload.resolution, payload.fps, payload.quality)
    except editing.TimelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    active = db.query(models.ProcessingJob).filter(models.ProcessingJob.project_id == pid, models.ProcessingJob.job_type == "export_project",
                                                   models.ProcessingJob.status.in_(("queued", "processing"))).first()
    if active:
        raise HTTPException(status_code=409, detail=f"An export of this project is already {active.status} (job #{active.id}).")
    _snapshot(db, item, "Exported"); db.commit()
    job = models.ProcessingJob(project_id=pid, job_type="export_project", status="queued", progress=0, params=settings)
    db.add(job); db.commit()
    try:
        enqueue_job(job.id)
    except QueueUnavailable:
        db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job.id, models.ProcessingJob.status == "queued").update(
            {"status": "failed", "finished_at": models.utcnow(), "error_message": "The job queue (Redis) is not reachable. Start it and use Retry."}, synchronize_session=False)
        db.commit()
    db.refresh(job)
    audit.record(db, "export_started", request, user_id=user.id, detail=f"project_id={pid} job_id={job.id}")
    return job

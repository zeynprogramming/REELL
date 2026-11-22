import logging
import os
from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI, Depends, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import get_current_user, require_write_access
from . import audit
from .bootstrap import bootstrap_admin
from .database import get_db
from .routers import auth as auth_router, files as files_router, manual as manual_router, projects as projects_router, users as users_router
from .queueing import QueueUnavailable, enqueue_job, queue_status
from .storage import get_storage
from .worker.processing import IMPLEMENTED_TYPES
from .security import get_secret_key
from . import models, schemas

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(_: FastAPI):
    get_secret_key()  # fail fast when SECRET_KEY is missing or weak
    storage = get_storage()
    storage.ensure()
    storage.purge_stale_tmp()
    bootstrap_admin()
    yield

# Interactive API docs are handy in development and unnecessary on a public server (set ENABLE_DOCS=false there).
_docs_on = os.getenv("ENABLE_DOCS", "true").lower() in {"1", "true", "yes"}
app = FastAPI(
    title="REEL API",
    description="Core API for the REEL video automation platform.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_on else None,
    redoc_url="/redoc" if _docs_on else None,
    openapi_url="/openapi.json" if _docs_on else None,
)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # Bearer tokens are sent in the Authorization header, not cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response

# Every data endpoint requires a signed-in user; changes additionally require the admin or editor role.
api = APIRouter(dependencies=[Depends(require_write_access)])

def get_or_404(db: Session, model, item_id: int, label: str):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item

def commit_or_conflict(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The request conflicts with existing data or a related record.")

@app.get("/api/health", response_model=schemas.HealthResponse, tags=["System"])
def health(db: Session = Depends(get_db)):
    """Used by Docker and uptime monitors: answers 200 only when the database really responds."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ok", "service": "reel-api", "version": app.version, "database": "ok"}

@api.get("/api/dashboard/summary", response_model=schemas.DashboardSummary, tags=["Dashboard"])
def dashboard_summary(db: Session = Depends(get_db)):
    return {
        "total_recordings": db.query(func.count(models.Recording.id)).scalar() or 0,
        "published_videos": db.query(func.count(models.PublishedVideo.id)).scalar() or 0,
        "processing": db.query(func.count(models.ProcessingJob.id)).filter(models.ProcessingJob.status == "processing").scalar() or 0,
        "failed_jobs": db.query(func.count(models.ProcessingJob.id)).filter(models.ProcessingJob.status == "failed").scalar() or 0,
    }

@api.get("/api/recordings", response_model=list[schemas.RecordingOut], tags=["Recordings"])
def list_recordings(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return db.query(models.Recording).order_by(models.Recording.created_at.desc(), models.Recording.id.desc()).offset(offset).limit(limit).all()

@api.post("/api/recordings", response_model=schemas.RecordingOut, status_code=201, tags=["Recordings"])
def create_recording(payload: schemas.RecordingCreate, db: Session = Depends(get_db)):
    item = models.Recording(**payload.model_dump())
    db.add(item)
    commit_or_conflict(db)
    db.refresh(item)
    return item

@api.get("/api/recordings/{item_id}", response_model=schemas.RecordingOut, tags=["Recordings"])
def get_recording(item_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, models.Recording, item_id, "Recording")

@api.patch("/api/recordings/{item_id}", response_model=schemas.RecordingOut, tags=["Recordings"])
def update_recording(item_id: int, payload: schemas.RecordingUpdate, db: Session = Depends(get_db)):
    item = get_or_404(db, models.Recording, item_id, "Recording")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    commit_or_conflict(db)
    db.refresh(item)
    return item

@api.delete("/api/recordings/{item_id}", status_code=204, tags=["Recordings"])
def delete_recording(item_id: int, db: Session = Depends(get_db)):
    item = get_or_404(db, models.Recording, item_id, "Recording")
    file_key = item.file_path
    db.delete(item)
    commit_or_conflict(db)
    get_storage().delete(file_key)  # remove the stored file only after the database record is gone
    return Response(status_code=204)

@api.get("/api/jobs", response_model=list[schemas.JobOut], tags=["Processing Jobs"])
def list_jobs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.ProcessingJob)
    if status:
        query = query.filter(models.ProcessingJob.status == status)
    return query.order_by(models.ProcessingJob.created_at.desc(), models.ProcessingJob.id.desc()).offset(offset).limit(limit).all()

def _enqueue_or_fail(db: Session, job: models.ProcessingJob) -> None:
    """Hand the job to the queue; if the queue is down, record that honestly instead of pretending it is queued."""
    try:
        enqueue_job(job.id)
    except QueueUnavailable:
        db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job.id, models.ProcessingJob.status == "queued").update(
            {"status": "failed", "finished_at": models.utcnow(), "error_message": "The job queue (Redis) is not reachable. Start it and use Retry."}, synchronize_session=False)
        db.commit()

@api.post("/api/jobs", response_model=schemas.JobOut, status_code=201, tags=["Processing Jobs"])
def create_job(payload: schemas.JobCreate, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.job_type not in IMPLEMENTED_TYPES:
        raise HTTPException(status_code=400, detail=f"Job type “{payload.job_type}” is not available yet. Available: {', '.join(IMPLEMENTED_TYPES)}.")
    recording = db.get(models.Recording, payload.recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    if not recording.file_path:
        raise HTTPException(status_code=400, detail="This recording has no uploaded file, so there is nothing to process.")
    active = db.query(models.ProcessingJob).filter(models.ProcessingJob.recording_id == recording.id, models.ProcessingJob.job_type == payload.job_type,
                                                   models.ProcessingJob.status.in_(("queued", "processing"))).first()
    if active:
        raise HTTPException(status_code=409, detail=f"A {payload.job_type.replace('_', ' ')} job for this recording is already {active.status} (job #{active.id}).")
    item = models.ProcessingJob(recording_id=recording.id, job_type=payload.job_type, status="queued", progress=0)
    db.add(item)
    commit_or_conflict(db)
    _enqueue_or_fail(db, item)
    db.refresh(item)
    audit.record(db, "job_created", request, user_id=user.id, detail=f"job_id={item.id} type={item.job_type} recording_id={recording.id}")
    return item

@api.post("/api/jobs/{item_id}/retry", response_model=schemas.JobOut, tags=["Processing Jobs"])
def retry_job(item_id: int, db: Session = Depends(get_db)):
    item = get_or_404(db, models.ProcessingJob, item_id, "Processing job")
    reset = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == item_id, models.ProcessingJob.status.in_(("failed", "cancelled"))).update(
        {"status": "queued", "progress": 0, "error_message": None, "result": None, "started_at": None, "finished_at": None}, synchronize_session=False)
    db.commit()
    if reset != 1:
        raise HTTPException(status_code=409, detail=f"Only failed or cancelled jobs can be retried (this one is {item.status}).")
    _enqueue_or_fail(db, item)
    db.refresh(item)
    return item

@api.post("/api/jobs/{item_id}/cancel", response_model=schemas.JobOut, tags=["Processing Jobs"])
def cancel_job(item_id: int, db: Session = Depends(get_db)):
    item = get_or_404(db, models.ProcessingJob, item_id, "Processing job")
    changed = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == item_id, models.ProcessingJob.status.in_(("queued", "processing"))).update(
        {"status": "cancelled", "finished_at": models.utcnow(), "error_message": "Cancelled by a user."}, synchronize_session=False)
    db.commit()
    if changed != 1:
        raise HTTPException(status_code=409, detail=f"Only queued or processing jobs can be cancelled (this one is {item.status}).")
    db.refresh(item)
    return item

@app.get("/api/system/status", response_model=schemas.QueueStatus, tags=["System"], dependencies=[Depends(get_current_user)])
def system_status():
    return {**queue_status(), "job_types": list(IMPLEMENTED_TYPES)}

@api.delete("/api/jobs/{item_id}", status_code=204, tags=["Processing Jobs"])
def delete_job(item_id: int, db: Session = Depends(get_db)):
    item = get_or_404(db, models.ProcessingJob, item_id, "Processing job")
    db.delete(item)
    commit_or_conflict(db)
    return Response(status_code=204)

@api.get("/api/transcripts", response_model=list[schemas.TranscriptOut], tags=["Transcripts"])
def list_transcripts(recording_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Transcript)
    if recording_id is not None:
        query = query.filter(models.Transcript.recording_id == recording_id)
    return query.order_by(models.Transcript.created_at.desc()).all()

@api.post("/api/transcripts", response_model=schemas.TranscriptOut, status_code=201, tags=["Transcripts"])
def create_transcript(payload: schemas.TranscriptCreate, db: Session = Depends(get_db)):
    if db.get(models.Recording, payload.recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    item = models.Transcript(**payload.model_dump())
    db.add(item); commit_or_conflict(db); db.refresh(item)
    return item

@api.get("/api/video-metadata", response_model=list[schemas.VideoMetadataOut], tags=["Video Metadata"])
def list_video_metadata(recording_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(models.VideoMetadata)
    if recording_id is not None:
        query = query.filter(models.VideoMetadata.recording_id == recording_id)
    return query.order_by(models.VideoMetadata.id.desc()).all()

@api.post("/api/video-metadata", response_model=schemas.VideoMetadataOut, status_code=201, tags=["Video Metadata"])
def create_video_metadata(payload: schemas.VideoMetadataCreate, db: Session = Depends(get_db)):
    if db.get(models.Recording, payload.recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    item = models.VideoMetadata(**payload.model_dump())
    db.add(item); commit_or_conflict(db); db.refresh(item)
    return item

@api.get("/api/publications", response_model=list[schemas.PublicationOut], tags=["Publications"])
def list_publications(db: Session = Depends(get_db)):
    return db.query(models.PublishedVideo).order_by(models.PublishedVideo.id.desc()).all()

@api.post("/api/publications", response_model=schemas.PublicationOut, status_code=201, tags=["Publications"])
def create_publication(payload: schemas.PublicationCreate, db: Session = Depends(get_db)):
    if db.get(models.Recording, payload.recording_id) is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    item = models.PublishedVideo(**payload.model_dump())
    db.add(item); commit_or_conflict(db); db.refresh(item)
    return item

@api.get("/api/integrations", response_model=list[schemas.IntegrationOut], tags=["Integrations"])
def list_integrations(db: Session = Depends(get_db)):
    return db.query(models.Integration).order_by(models.Integration.provider.asc()).all()

@api.post("/api/integrations", response_model=schemas.IntegrationOut, status_code=201, tags=["Integrations"])
def create_integration(payload: schemas.IntegrationCreate, db: Session = Depends(get_db)):
    item = models.Integration(**payload.model_dump())
    db.add(item); commit_or_conflict(db); db.refresh(item)
    return item

@api.get("/api/consents", response_model=list[schemas.ConsentOut], tags=["Consent Management"])
def list_consents(db: Session = Depends(get_db)):
    return db.query(models.StudentConsent).order_by(models.StudentConsent.checked_at.desc()).all()

@api.post("/api/consents", response_model=schemas.ConsentOut, status_code=201, tags=["Consent Management"])
def create_consent(payload: schemas.ConsentCreate, db: Session = Depends(get_db)):
    item = models.StudentConsent(**payload.model_dump())
    db.add(item); commit_or_conflict(db); db.refresh(item)
    return item

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(users_router.audit_router)
app.include_router(files_router.router)
app.include_router(files_router.public_router)
app.include_router(manual_router.router)
app.include_router(projects_router.router)
app.include_router(api)

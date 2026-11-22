"""Job execution. Pure Python: no Celery import, so it can be tested and reused by any queue.

State machine (owned by the worker, never edited by hand):
    queued -> processing -> completed | failed        cancelled can happen from queued/processing
The claim is an atomic UPDATE, so a job that is delivered twice is executed only once.
"""
import logging
import os
from datetime import timedelta
from typing import Callable

from sqlalchemy import or_
from sqlalchemy.orm import sessionmaker

from .. import models
from ..database import SessionLocal
from ..editing import render as editing
from ..storage import AUDIO_TYPES, get_storage
from .probe import ProbeError, ToolMissing, probe_video

log = logging.getLogger("reel.worker")
Progress = Callable[[int], None]


class JobFailure(Exception):
    """A failure with a message that is safe to show in the UI."""


class JobCancelled(Exception):
    pass


def job_timeout_seconds() -> int:
    try:
        return max(30, int(os.getenv("JOB_TIMEOUT_SECONDS", "900")))
    except ValueError:
        return 900


def validate_video(recording: models.Recording, report: Progress) -> dict:
    report(10)
    path = get_storage().path_for(recording.file_path)
    if path is None or not path.is_file():
        raise JobFailure("The stored file for this recording is missing on the worker's disk.")
    try:
        info = probe_video(path, timeout=min(120, job_timeout_seconds()), allow_audio_only=path.suffix.lower() in AUDIO_TYPES)
    except ProbeError as exc:
        raise JobFailure(str(exc))
    except ToolMissing as exc:
        raise JobFailure(str(exc))
    report(80)
    return info


def export_project(db, project: models.EditProject, params: dict, report: Progress) -> dict:
    """Render a project's timeline to a new MP4 recording (ffmpeg). Returns a summary stored as the job result."""
    import hashlib, json
    report(2)
    try:
        timeline = json.loads(project.timeline_json or "{}")
    except ValueError:
        raise JobFailure("The project timeline is damaged.")
    storage = get_storage()
    ids = {c.get("recording_id") for c in (timeline.get("clips") or []) if isinstance(c, dict) and isinstance(c.get("recording_id"), int)}
    audio_ids = {a.get("recording_id") for a in (timeline.get("audio") or []) if isinstance(a, dict) and isinstance(a.get("recording_id"), int)}
    audio_sources: dict[int, dict] = {}
    for rec in db.query(models.Recording).filter(models.Recording.id.in_(audio_ids)).all() if audio_ids else []:
        path = storage.path_for(rec.file_path)
        if path is None or not path.is_file():
            continue
        try:
            info = probe_video(path, timeout=min(120, job_timeout_seconds()), allow_audio_only=True)
        except (ProbeError, ToolMissing) as exc:
            raise JobFailure(f"Audio file “{rec.filename}” cannot be used: {exc}")
        audio_sources[rec.id] = {"duration": info["duration_seconds"], "has_audio": info["has_audio"], "path": path}
    sources: dict[int, dict] = {}
    for rec in db.query(models.Recording).filter(models.Recording.id.in_(ids)).all() if ids else []:
        path = storage.path_for(rec.file_path)
        if path is None or not path.is_file():
            continue
        try:
            info = probe_video(path, timeout=min(120, job_timeout_seconds()))
        except (ProbeError, ToolMissing) as exc:
            raise JobFailure(f"Recording “{rec.filename}” cannot be used: {exc}")
        sources[rec.id] = {"duration": info["duration_seconds"], "has_audio": info["has_audio"], "path": path}
    try:
        normalized = editing.validate_timeline(timeline, sources)
        total_len = sum(e - st for _, st, e in normalized)
        texts = editing.validate_texts(timeline.get("texts") or [], total_len)
        clip_audio = editing.clip_audio_settings(timeline, normalized)
        clip_video = editing.clip_video_settings(timeline, normalized)
        tracks = editing.validate_audio_tracks(timeline.get("audio") or [], audio_sources, total_len)
        settings = editing.normalize_settings(**{k: params[k] for k in ("resolution", "fps", "quality") if k in params})
    except editing.TimelineError as exc:
        raise JobFailure(str(exc))
    clips = [editing.Clip(rid, s, e, sources[rid]["path"], sources[rid]["has_audio"], vol, fi, fo, vfx) for (rid, s, e), (vol, fi, fo), vfx in zip(normalized, clip_audio, clip_video)]
    report(5)
    tmp = storage.tmp_path()
    try:
        editing.render(clips, tmp, settings, report=report, timeout=max(60, job_timeout_seconds() - 30), texts=texts, audio_tracks=tracks)
    except editing.RenderError as exc:
        raise JobFailure(str(exc))
    digest = hashlib.sha256()
    with open(tmp, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    size = tmp.stat().st_size
    try:
        out_info = probe_video(tmp, timeout=60)
    except (ProbeError, ToolMissing) as exc:
        tmp.unlink(missing_ok=True)
        raise JobFailure(f"The rendered file failed validation: {exc}")
    key = storage.new_key(".mp4")
    storage.commit(tmp, key)
    rec = models.Recording(filename=f"{project.name} (export).mp4"[:255], status="ready", duration_seconds=int(round(out_info["duration_seconds"])),
                           file_path=key, file_size_bytes=size, content_type="video/mp4", checksum_sha256=digest.hexdigest())
    db.add(rec)
    db.commit()
    return {"recording_id": rec.id, "duration_seconds": out_info["duration_seconds"], "width": out_info["width"], "height": out_info["height"],
            "size_bytes": size, "settings": settings, "texts": len(texts), "audio_tracks": len(tracks)}


# job_type -> handler. A type appears here only when it really does its work.
HANDLERS: dict[str, Callable[[models.Recording, Progress], dict]] = {"video_validation": validate_video}
IMPLEMENTED_TYPES = tuple(HANDLERS)  # jobs started from a recording via POST /api/jobs
PROJECT_HANDLERS: dict[str, Callable] = {"export_project": export_project}  # jobs started from a project (POST /api/projects/{id}/export)


def run_job(job_id: int, session_factory: sessionmaker = SessionLocal) -> str:
    """Execute one job. Returns 'skipped', 'completed', 'failed' or 'cancelled'."""
    with session_factory() as db:
        claimed = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job_id, models.ProcessingJob.status == "queued").update(
            {"status": "processing", "progress": 0, "started_at": models.utcnow(), "finished_at": None, "error_message": None, "result": None,
             "attempts": models.ProcessingJob.attempts + 1}, synchronize_session=False)
        db.commit()
        if claimed != 1:
            return "skipped"  # unknown, cancelled, already running or already finished

        job = db.get(models.ProcessingJob, job_id)
        recording = db.get(models.Recording, job.recording_id) if job and job.recording_id else None

        def report(percent: int) -> None:
            updated = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job_id, models.ProcessingJob.status == "processing").update(
                {"progress": max(0, min(99, percent))}, synchronize_session=False)
            db.commit()
            if updated != 1:
                raise JobCancelled()

        error: str | None = None
        result: dict | None = None
        try:
            if job and job.job_type in PROJECT_HANDLERS:
                project = db.get(models.EditProject, job.project_id) if job.project_id else None
                if project is None:
                    raise JobFailure("The project for this job no longer exists.")
                result = PROJECT_HANDLERS[job.job_type](db, project, job.params or {}, report)
            else:
                handler = HANDLERS.get(job.job_type) if job else None
                if handler is None:
                    raise JobFailure(f"Job type “{job.job_type if job else '?'}” is not implemented yet.")
                if recording is None:
                    raise JobFailure("The recording for this job no longer exists.")
                result = handler(recording, report)
        except JobCancelled:
            return "cancelled"
        except JobFailure as exc:
            error = str(exc)
        except Exception as exc:  # never leak internals to the UI; the full trace goes to the worker log
            log.exception("Job %s crashed", job_id)
            error = "The job exceeded its time limit." if type(exc).__name__ == "SoftTimeLimitExceeded" else "Unexpected error while processing. See the worker log."

        values = {"status": "failed", "error_message": error, "finished_at": models.utcnow()} if error else \
                 {"status": "completed", "progress": 100, "result": result, "error_message": None, "finished_at": models.utcnow()}
        done = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job_id, models.ProcessingJob.status == "processing").update(values, synchronize_session=False)
        if done == 1 and not error and recording is not None and result and "duration_seconds" in result:
            recording.duration_seconds = int(round(result["duration_seconds"]))
            if recording.status == "uploaded":
                recording.status = "ready"
        db.commit()
        return "failed" if error else ("completed" if done == 1 else "cancelled")


def reap_stale_jobs(session_factory: sessionmaker = SessionLocal) -> int:
    """Fail jobs stuck in 'processing' (for example after a worker crash) so they can be retried."""
    cutoff = models.utcnow() - timedelta(seconds=job_timeout_seconds() + 120)
    with session_factory() as db:
        count = db.query(models.ProcessingJob).filter(
            models.ProcessingJob.status == "processing",
            or_(models.ProcessingJob.started_at.is_(None), models.ProcessingJob.started_at < cutoff),
        ).update({"status": "failed", "finished_at": models.utcnow(), "error_message": "The worker stopped before finishing this job. You can retry it."}, synchronize_session=False)
        db.commit()
    if count:
        log.warning("Marked %s stale job(s) as failed", count)
    return count

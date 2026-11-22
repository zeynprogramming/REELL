import shutil
import subprocess
import pytest
from conftest import make_user, login
from app import models, queueing
from app.database import SessionLocal
from app.worker.processing import reap_stale_jobs, run_job

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg is not installed")

def real_video(tmp_path, seconds=2):
    path = tmp_path / f"real-{seconds}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=15", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path.read_bytes()

def upload(client, headers, body, name="lesson.mp4"):
    return client.post("/api/recordings/upload", params={"filename": name}, content=body, headers={**headers, "Content-Type": "application/octet-stream"}).json()

def make_job(recording_id, status="queued", job_type="video_validation", **extra):
    with SessionLocal() as db:
        job = models.ProcessingJob(recording_id=recording_id, job_type=job_type, status=status, **extra)
        db.add(job); db.commit()
        return job.id

@needs_ffmpeg
def test_validation_job_runs_end_to_end(client, admin_headers, tmp_path):
    rec = upload(client, admin_headers, real_video(tmp_path))
    created = client.post("/api/jobs", json={"recording_id": rec["id"], "job_type": "video_validation"}, headers=admin_headers)
    assert created.status_code == 201
    job = created.json()  # inline mode: the worker has already run
    assert job["status"] == "completed" and job["progress"] == 100 and job["attempts"] == 1
    assert job["result"]["video_codec"] == "h264" and job["result"]["width"] == 320
    after = client.get(f"/api/recordings/{rec['id']}", headers=admin_headers).json()
    assert after["status"] == "ready" and after["duration_seconds"] == 2

def test_corrupt_video_fails_honestly(client, admin_headers):
    fake = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x07" * 4096  # passes the upload sniff, is not a real video
    rec = upload(client, admin_headers, fake)
    job = client.post("/api/jobs", json={"recording_id": rec["id"], "job_type": "video_validation"}, headers=admin_headers).json()
    assert job["status"] == "failed" and job["error_message"] and job["result"] is None
    assert client.get(f"/api/recordings/{rec['id']}", headers=admin_headers).json()["status"] == "uploaded"  # not marked ready

def test_unimplemented_job_type_never_pretends_to_succeed(client, admin_headers):
    rec = upload(client, admin_headers, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x09" * 200)
    job_id = make_job(rec["id"], job_type="transcription")
    assert run_job(job_id) == "failed"
    job = [j for j in client.get("/api/jobs", headers=admin_headers).json() if j["id"] == job_id][0]
    assert job["status"] == "failed" and "not implemented" in job["error_message"]

def test_job_is_executed_only_once(client, admin_headers):
    rec = upload(client, admin_headers, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x03" * 200)
    job_id = make_job(rec["id"])
    assert run_job(job_id) == "failed"   # corrupt file: fails once
    assert run_job(job_id) == "skipped"  # a duplicate delivery does nothing
    assert run_job(424242) == "skipped"  # unknown job

def test_cancel_and_retry(client, admin_headers):
    rec = upload(client, admin_headers, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x04" * 200)
    job_id = make_job(rec["id"])
    cancelled = client.post(f"/api/jobs/{job_id}/cancel", headers=admin_headers)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert run_job(job_id) == "skipped"  # a cancelled job is never started
    assert client.post(f"/api/jobs/{job_id}/cancel", headers=admin_headers).status_code == 409
    retried = client.post(f"/api/jobs/{job_id}/retry", headers=admin_headers)
    assert retried.status_code == 200 and retried.json()["status"] == "failed"  # ran again inline, corrupt file fails again
    assert retried.json()["attempts"] == 1 and retried.json()["error_message"]
    assert client.post(f"/api/jobs/{make_job(rec['id'], status='completed')}/retry", headers=admin_headers).status_code == 409

def test_duplicate_active_job_is_rejected(client, admin_headers):
    rec = upload(client, admin_headers, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x05" * 200)
    make_job(rec["id"], status="processing")
    dup = client.post("/api/jobs", json={"recording_id": rec["id"], "job_type": "video_validation"}, headers=admin_headers)
    assert dup.status_code == 409

def test_queue_outage_is_reported_not_hidden(client, admin_headers, monkeypatch):
    import app.main as main
    def down(_job_id): raise queueing.QueueUnavailable("redis down")
    monkeypatch.setattr(main, "enqueue_job", down)
    rec = upload(client, admin_headers, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x06" * 200)
    job = client.post("/api/jobs", json={"recording_id": rec["id"], "job_type": "video_validation"}, headers=admin_headers).json()
    assert job["status"] == "failed" and "not reachable" in job["error_message"]

def test_stale_processing_jobs_are_reaped(client, admin_headers):
    from datetime import timedelta
    rec = upload(client, admin_headers, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x08" * 200)
    stale = make_job(rec["id"], status="processing", started_at=models.utcnow() - timedelta(hours=3))
    fresh = make_job(rec["id"], status="processing", started_at=models.utcnow())
    assert reap_stale_jobs() == 1
    jobs = {j["id"]: j for j in client.get("/api/jobs", headers=admin_headers).json()}
    assert jobs[stale]["status"] == "failed" and jobs[fresh]["status"] == "processing"

def test_viewer_cannot_manage_jobs(client, admin_headers, viewer_headers):
    rec = upload(client, admin_headers, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x0a" * 200)
    assert client.post("/api/jobs", json={"recording_id": rec["id"], "job_type": "video_validation"}, headers=viewer_headers).status_code == 403
    job_id = make_job(rec["id"], status="failed")
    assert client.post(f"/api/jobs/{job_id}/retry", headers=viewer_headers).status_code == 403
    assert client.post(f"/api/jobs/{job_id}/cancel", headers=viewer_headers).status_code == 403
    assert client.get("/api/jobs", headers=viewer_headers).status_code == 200

def test_system_status(client, admin_headers):
    assert client.get("/api/system/status").status_code == 401
    body = client.get("/api/system/status", headers=admin_headers).json()
    assert body["mode"] == "inline" and body["job_types"] == ["video_validation"]

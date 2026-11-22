"""Create a small, clearly-labelled demo data set so a reviewer sees a working system on first login.

    docker compose exec backend python -m app.seed_demo

It is safe to run twice. Everything it creates is real: the sample video is generated with ffmpeg, stored like an
upload, and validated by the same worker code as any other recording (no invented results)."""
import hashlib
import subprocess
import sys

from . import models
from .database import SessionLocal
from .storage import get_storage
from .worker.processing import run_job

DEMO_NAME = "Demo lesson — sample test video.mp4"


def make_sample_video(path) -> None:
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=duration=20:size=640x360:rate=25",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    subprocess.run(cmd, check=True, timeout=120)


def main() -> int:
    storage = get_storage()
    storage.ensure()
    with SessionLocal() as db:
        if db.query(models.Recording).filter(models.Recording.filename == DEMO_NAME).first():
            print("Demo data already exists. Nothing to do.")
            return 0

        tmp = storage.tmp_path()
        make_sample_video(tmp)
        digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
        size = tmp.stat().st_size
        key = storage.new_key(".mp4")
        storage.commit(tmp, key)
        recording = models.Recording(filename=DEMO_NAME, status="uploaded", file_path=key, file_size_bytes=size, content_type="video/mp4", checksum_sha256=digest)
        db.add(recording)
        db.flush()
        job = models.ProcessingJob(recording_id=recording.id, job_type="video_validation", status="queued", progress=0)
        db.add(job)

        if not db.query(models.Consent).filter(models.Consent.external_student_id == "DEMO-001").first():
            db.add(models.Consent(external_student_id="DEMO-001", photo_video_allowed=True))
            db.add(models.Consent(external_student_id="DEMO-002", photo_video_allowed=False))
        for provider in ("YouTube", "Slack", "Google Classroom"):
            if not db.query(models.Integration).filter(models.Integration.provider == provider).first():
                db.add(models.Integration(provider=provider, is_enabled=False, status="not_connected"))
        db.commit()
        job_id = job.id

    outcome = run_job(job_id)  # the real validation job, run right here instead of through the queue
    print(f"Demo data created. Validation job finished: {outcome}.")
    return 0 if outcome == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())

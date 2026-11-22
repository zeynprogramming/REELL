# REEL — Video Automation Platform (v1.0.0, final)

A web platform for an academy to upload lesson recordings, check them in the background, watch them in a library and manage student photo/video consent. Stack: React + TypeScript + Tailwind, FastAPI, PostgreSQL, Redis + Celery.

## What is in this version
| Area | Status |
|---|---|
| Sign-in, roles (admin / editor / viewer), user management, audit log | Done |
| Dashboard, Recordings (upload, play, download, delete), Processing Queue, Consent Management, Settings | Done |
| Academy Library (watch every uploaded video) | Done |
| Background worker: real video validation with ffprobe | Done |
| Manual workspace (Recordings → **Details**): title, description, tags, chapters (can be set from the current playback time), transcript, publication log | Done, works without any AI |
| Integrations page | **Registry only.** No YouTube, Slack or Google Classroom connection exists; nothing is published anywhere |
| AI Content | **Visible but switched off.** The page is a preview; no recording or text is sent to any AI service and nothing is generated |
| Production deployment (HTTPS, health checks, backups) | Done, see **DEPLOY.md** |

Deliberately not built: transcription and other AI features (Phase 7), external publishing (Phase 8). The code contains no AI provider keys or calls.

## Deploy it
Follow **DEPLOY.md** (Armenian). Short version: a Linux server with Docker, then `./scripts/prod.sh up -d --build`.

## Never share these files
`.env`, `.env.prod`, `.venv/`, `node_modules/`. They hold passwords or are huge. This repository's `.gitignore` already excludes them.

## Requirements
- Ubuntu 22.04/24.04 (or compatible)
- Docker Engine and Docker Compose plugin (recommended)
- For local development: Python 3.11+, Node.js 20+, PostgreSQL 15+

## Run with Docker (recommended)
From this directory:

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD (and the matching password inside DATABASE_URL),
# a random SECRET_KEY, and BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD.
docker compose up --build        # starts db, redis, backend, worker, frontend
```

Open:
- Frontend: http://localhost:5173 (sign in with the bootstrap administrator)
- API documentation: http://localhost:8000/docs
- API health: http://localhost:8000/api/health

Stop the containers:

```bash
docker compose down
```

**Data warning:** `docker compose down -v` deletes the PostgreSQL volume **and the uploaded videos volume**. Do not use it if you want to keep your data.

## Run locally in a Linux terminal (without Docker for the app)
The backend and worker read **real environment variables**, not the `.env` file by itself, so export them in each terminal.
PostgreSQL and Redis can still come from Docker. ffmpeg must be installed on your machine for the worker: `sudo apt install ffmpeg`.

**Terminal 1 — database and queue**
```bash
cd REEL_Phase6
cp .env.example .env                  # then edit .env (see the Docker section above)
docker compose up -d db redis         # PostgreSQL :5432 and Redis :6379 on 127.0.0.1
```

**Terminal 2 — backend**
```bash
cd REEL_Phase6/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+psycopg://reel:YOUR_POSTGRES_PASSWORD@localhost:5432/reel"
export REDIS_URL="redis://localhost:6379/0"
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export BOOTSTRAP_ADMIN_EMAIL="you@example.com"
export BOOTSTRAP_ADMIN_PASSWORD="choose-a-long-password"
export UPLOAD_DIR="$HOME/reel-uploads"
export CORS_ORIGINS="http://localhost:5173"

alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 3 — worker** (same virtualenv; `DATABASE_URL`, `REDIS_URL` and `UPLOAD_DIR` must be identical to the backend's)
```bash
cd REEL_Phase6/backend
source .venv/bin/activate
export DATABASE_URL="postgresql+psycopg://reel:YOUR_POSTGRES_PASSWORD@localhost:5432/reel"
export REDIS_URL="redis://localhost:6379/0"
export UPLOAD_DIR="$HOME/reel-uploads"
celery -A app.worker.celery_app:celery_app worker -B --loglevel=INFO --concurrency=2
```

**Terminal 4 — frontend**
```bash
cd REEL_Phase6/frontend
npm install
npm run dev -- --host 127.0.0.1
```
Open http://localhost:5173 and sign in with the email and password you exported.

*Shortcut for development only:* set `export CELERY_EAGER=1` before starting the backend and skip Terminal 3 and Redis. Jobs then run inside the API process (the Processing Queue page shows "Inline mode"). Not for production.

(`SECRET_KEY` generated this way changes every time you re-run the export, which signs everyone out. Save one value if you want sessions to survive restarts.)
If the API runs elsewhere, create `frontend/.env.local` with `VITE_API_BASE_URL=http://your-api-host:8000`.

## Phase 6 features
- **Redis + Celery worker** run jobs in the background, outside the web request. New services in Docker Compose: `redis` and `worker` (same image as the API; the image now includes ffmpeg/ffprobe).
- **Real job: video validation.** The worker inspects the uploaded file with ffprobe (read-only) and stores duration, codec, resolution, frame rate and audio info. On success the recording gets its real duration and moves from *uploaded* to *ready*. A corrupt, audio-only or unreadable file fails with a clear message and the recording is **not** marked ready.
- **Honest job states, owned by the worker:** queued → processing → completed / failed, plus cancelled. Manual editing of status and progress was removed (the old `PATCH /api/jobs/{id}` no longer exists). Transcription, metadata generation and publication are **rejected at creation** until their phases (7 and 8) instead of pretending to run.
- **Safe execution:** a job claimed by one worker cannot run twice; cancel works for queued jobs and stops a running job at its next progress step; a job stuck in *processing* after a worker crash is failed automatically after the time limit (+2 min) so it can be retried; the time limit is `JOB_TIMEOUT_SECONDS`.
- **If Redis is down** when you start a job, the job is saved as *failed* with the message "queue not reachable" (not left queued forever); use **Retry** once Redis is back.
- **UI:** Processing Queue shows worker status (online / no worker / queue unreachable), per-job result or error, Cancel / Retry / Delete, and updates every 3 seconds while jobs run. Recordings has a **Validate** button. Duplicate active jobs for the same recording and job type are rejected.
- New API: `POST /api/jobs` (recording + type only), `POST /api/jobs/{id}/retry`, `POST /api/jobs/{id}/cancel`, `GET /api/system/status`. Migration `0004_phase6_jobs` adds `started_at`, `finished_at`, `attempts`, `result` to `processing_jobs`.

### Phase 6 limits
- Run exactly **one** worker container with `-B` (it embeds the scheduler). To scale to several workers, run the scheduler separately (`celery ... beat`) — planned for Phase 9.
- A worker crash leaves the job *processing* until the time limit passes; only then can it be retried.
- Cancelling a running validation takes effect at its next progress step, not instantly.
- The worker container still runs as root (the uploads volume is shared with the API); non-root hardening is planned for Phase 9.
- Tests that need Redis are not included: tests run in inline mode (`CELERY_EAGER=1`); a real Redis/worker round trip must be checked manually (see below).

### Checking the worker manually
```bash
docker compose up --build -d
docker compose logs -f worker          # should show "celery@... ready."
```
Upload a video, open **Processing Queue**, choose it and press **Start job**. The status goes queued → processing → completed within seconds and the result shows the resolution and codec. To see the failure path, stop the worker (`docker compose stop worker`): the banner says "No worker is running" and new jobs wait; `docker compose start worker` lets them finish.

## Phase 5 features
- **Upload recordings** (Recordings page): drag and drop or choose one or more files; MP4, MOV, M4V, WebM, MKV, AVI. Progress bar, cancel, and clear error messages.
- The server **streams** the upload to disk and enforces `MAX_UPLOAD_MB` while receiving it (a file over the limit is cut off instead of filling the disk), checks the real file contents against the extension, computes a SHA-256 checksum and rejects an exact duplicate.
- Files are stored under `UPLOAD_DIR` with server-generated names; the user's filename is kept only as display text, so path tricks such as `../../x.mp4` are neutralised. `file_path` can no longer be set through the API (this closes a path-traversal risk from earlier phases).
- **Play and download** use a signed link valid for 5 minutes, issued only to signed-in users (all roles). Seeking in the video works (HTTP Range).
- Deleting a recording also removes its stored file. Interrupted uploads leave no partial files (stale ones are cleaned at start-up).
- Storage overview (files, space used, disk free, size limit) and uploads are recorded in the audit log.
- Migration `0003_phase5_files` adds `file_size_bytes`, `content_type`, `checksum_sha256` to `recordings`.
- **New interface**, inspired by the Picsart Academy website: near-black top bar and hero, white and dark cards that alternate, pill buttons with a circular arrow, plus-icon accordions, light/dark theme (remembered in the browser). The accent colour is one variable, `--accent` in `frontend/src/styles.css`. It is an interpretation of the site's style, not a copy of its assets, logo or exact colours.
- Recent publications are now shown on the Dashboard; write controls are hidden for read-only users.

### Phase 5 limits
- Uploading stores the file only. No transcoding, thumbnails, transcription or publishing yet.
- Storage is the server's local disk (Docker volume `reel_uploads`). It is isolated behind `backend/app/storage.py` so cloud storage can replace it later.
- Signed links appear in server access logs for their 5-minute lifetime.
- Two identical files uploaded at exactly the same moment could both pass the duplicate check.
- Very large uploads go through the API process directly; behind a reverse proxy raise its body-size limit (for nginx: `client_max_body_size`).

## Phase 4 features
- Sign-in with email and password; the API issues a short-lived signed token (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 60).
- Passwords are stored only as salted scrypt hashes. Minimum length is 10 characters.
- All data endpoints now require authentication. `/api/health` and the sign-in endpoint are the only public ones.
- Roles: **admin** (everything, including users and audit log), **editor** (create/change/delete data), **viewer** (read-only). Enforced by the API; the UI also hides write controls for viewers.
- Settings page: change your password; admins can create users, change roles, deactivate/reactivate accounts and read the security audit log.
- Changing a password, changing a role or deactivating an account invalidates that user's existing tokens.
- Failed sign-ins are rate-limited (5 per email and 20 per IP per 15 minutes, then HTTP 429) and recorded in the audit log. Passwords and tokens are never logged.
- Security headers on API responses, restricted CORS methods/headers, and the API refuses to start without a strong `SECRET_KEY`.
- Migration `0002_phase4_auth` adds the `users` and `audit_logs` tables. Existing Phase 3 data is untouched.

### First start / upgrading from Phase 3
1. Add `SECRET_KEY` and the `BOOTSTRAP_ADMIN_*` values to `.env` (see `.env.example`).
2. `docker compose up --build`. The API applies migrations, then creates the first administrator only if no users exist.
3. Sign in, open **Settings**, and change the bootstrap password. You may then remove `BOOTSTRAP_ADMIN_PASSWORD` from `.env`.

### Known limitations of this phase
- The access token is kept in `sessionStorage` (cleared when the tab closes). There is no refresh token and no server-side "sign out everywhere" button; tokens end by expiry, password change, role change or deactivation.
- Sign-in rate limiting is held in memory per API process and resets on restart; it is not shared across multiple workers (a Redis-backed limiter fits Phase 6).
- No password-reset by email, no multi-factor authentication, and the API serves plain HTTP. Put it behind HTTPS (reverse proxy) before any non-local use.
- An attacker who knows an email can temporarily lock that account's sign-in by failing 5 times; the lock expires after 15 minutes.
- `/docs` (Swagger UI) remains publicly reachable; use its Authorize button with a token from `/api/auth/login`.

## Phase 3 features
- Dashboard metrics and recent recordings/jobs are loaded from the API.
- API connection state, loading feedback, error feedback, and manual refresh.
- Recordings: list, create metadata record, update status, and delete.
- Processing Queue: list, create job record, update status/progress, and delete.
- Integrations: list and register provider records.
- Consent Management: list and create photo/video consent records.
- Search for recordings and processing jobs, dark/light theme, responsive navigation.
- API calls are centralized in `frontend/src/api.ts`.

## Important scope boundaries
- Adding a recording in Phase 3 creates a **database metadata record only**. It does not upload a video file. File storage/upload is planned for a later phase.
- Creating a processing job stores a queue record only. No worker executes it yet; Redis/Celery/background processing is planned for a later phase.
- Integration entries are registry records only. OAuth and real YouTube/Slack/Classroom connections are not active.
- Consent records are stored, but this phase does not implement a complete legal consent workflow, identity verification, or access-control policy. Use non-sensitive internal student references in test data.
- AI Content is a switched-off preview page; they are not presented as working modules.
- Consent records are still simple records; the access rules above control who can read or change them, but there is no legal consent workflow yet.
- Do not expose this build publicly over plain HTTP, and do not load real student data until HTTPS and your own security review are in place.

## Backend tests
From `backend/` with dependencies installed (tests use a temporary SQLite file and their own test `SECRET_KEY`):

```bash
pytest -q
```

## Project structure
```text
backend/    FastAPI API, SQLAlchemy models, Alembic migrations, tests
  app/storage.py        file storage layer (local disk)
  app/worker/           Celery app, job runner (processing.py), ffprobe (probe.py)
  app/routers/files.py  upload, storage summary, signed download links
frontend/   React + TypeScript + Vite interface
  src/components/       reusable UI (Button, Alert, Modal, Accordion, layout)
  src/pages/            Dashboard, Recordings, Queue, Integrations, Consents
.env.example
 docker-compose.yml
 README.md
```

Never commit `.env`, database passwords, OAuth credentials, or API keys.


## Manual workspace (no AI needed)
Open **Recordings → Details** (or **Academy Library → Details**) on any recording. An admin or editor can write the title, description, tags and chapters, paste or type the transcript, and record where the video was published. Viewers can read but not change. Chapters must have unique times and cannot start after the end of the video once its duration is known (run **Validate** first). The publication log is a record made by a person: REEL uploads nothing.
New API: `GET /api/recordings/{id}/workspace`, `PUT /api/recordings/{id}/metadata`, `PUT /api/recordings/{id}/transcript`, `POST /api/recordings/{id}/publications`, `DELETE /api/publications/{id}`, `PATCH|DELETE /api/consents/{id}`. Migration `0005_manual_workspace` adds `video_metadata.tags_json`; run `alembic upgrade head` (the Docker backend does this on start if it did before). Tests: `backend/tests/test_manual.py`.

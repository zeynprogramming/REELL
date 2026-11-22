# REEL Development Roadmap

- [x] Phase 1 — Core System & Dashboard foundation
- [x] Phase 2 — Backend & Database Foundation (FastAPI, SQLAlchemy, PostgreSQL, Alembic, REST endpoints, tests)
- [x] Phase 3 — Frontend Integration (API-connected dashboard, recordings, jobs, integrations registry, consent records)
- [x] Phase 4 — Authentication & Security (JWT sign-in, roles, user management, audit log, rate limiting)
- [x] Phase 5 — File Management & Uploads (streamed uploads, storage layer, signed playback/download links, Picsart-Academy-style redesign)
- [x] Phase 6 — Processing Infrastructure (Redis/Celery worker, job state machine, real video validation with ffprobe)
- [~] Phase 7 — AI & Video Automation: AI skipped on purpose (the AI page stays visible as a switched-off preview that says it does not work)
- [x] Phase 7b — Manual workspace (no AI): hand-written title, description, tags, chapters, transcript and a publication log per recording; consent records can be corrected or deleted
- [~] Phase 8 — External Integrations: skipped on purpose (the Integrations page is a registry only)
- [x] Phase 9 — Testing, Monitoring & Production Hardening (health check that verifies the database, API docs off in production, container health checks, log rotation, backup script, tests runnable in Docker)
- [x] Phase 10 — Deployment (production Docker stack with automatic HTTPS, step-by-step guide in DEPLOY.md, demo data script). The actual deployment on a server is done by the owner.

Each phase ZIP is cumulative: it contains the complete project up to that phase.

## PRD v2.0 roadmap (video editor) — started
- [~] PRD Phase 7–8 — Editor backend: `edit_projects` table, `/api/projects` (save/open/delete), background MP4 export via FFmpeg (Trim, Split, Merge, reorder; 480p/720p/1080p, 24–60 fps, quality). Migration `0006_edit_projects`. **Frontend editor (Timeline UI) is the next step.**
- [ ] PRD Phase 9 — Text & subtitles
- [~] PRD Phase 10 — Audio: audio uploads (MP3, WAV, M4A, AAC, OGG), per-clip volume/mute/fades, background music tracks mixed on export (position, trim, volume, fades). Preview plays clip sound only.
- [~] PRD Phase 11 — Effects & filters: per-clip filter (B&W, sepia, blur, sharpen, vignette), brightness, contrast, saturation; transitions (dip to black/white) between clips; CSS-approximate preview, FFmpeg export. Length of the video never changes.
- [~] PRD Phase 12–13 — Autosave (existing projects), version history with restore (migration 0007; latest 30; manual saves, exports, restores), list of exports per project, warning before leaving with unsaved changes.
- [ ] PRD Phase 14–17 — Integrations, security, testing, deployment
- [~] PRD Phase 7–8 frontend — "Video Editor" page: media list, preview, timeline (select, trim by numbers or playhead, split at playhead, reorder, duplicate, delete, merge by adding clips from other recordings), save/open projects, export with progress. Needs a real browser test.
- [~] PRD Phase 9 — Text & subtitles: text overlays (position, size, colour, background, timing) with live preview, .srt import, drawn into the export by FFmpeg (DejaVu font, covers Latin/Cyrillic/Armenian; added to the backend image). Rebuild the backend image after updating.

from datetime import datetime, timezone
from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Recording(Base):
    __tablename__ = "recordings"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(40), default="uploaded", index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # storage key, set only by the upload endpoint
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="recording", cascade="all, delete-orphan")
    transcripts: Mapped[list["Transcript"]] = relationship(back_populates="recording", cascade="all, delete-orphan")
    metadata_items: Mapped[list["VideoMetadata"]] = relationship(back_populates="recording", cascade="all, delete-orphan")
    publications: Mapped[list["PublishedVideo"]] = relationship(back_populates="recording", cascade="all, delete-orphan")

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    recording_id: Mapped[int | None] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # written by the worker only
    project_id: Mapped[int | None] = mapped_column(ForeignKey("edit_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # inputs fixed at creation (e.g. export settings)
    recording: Mapped[Recording | None] = relationship(back_populates="jobs")

class ProjectVersion(Base):
    """A saved snapshot of a project's timeline (history / restore)."""
    __tablename__ = "project_versions"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("edit_projects.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(60), default="Saved")
    name: Mapped[str] = mapped_column(String(200))
    timeline_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class EditProject(Base):
    """A saved editing project (Phase 7-8). The timeline is JSON: {"clips": [{"recording_id", "start", "end"}, ...]}."""
    __tablename__ = "edit_projects"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    timeline_json: Mapped[str] = mapped_column(Text, default='{"clips": []}')
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recording: Mapped[Recording] = relationship(back_populates="transcripts")

class VideoMetadata(Base):
    __tablename__ = "video_metadata"
    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of strings, typed by a person
    recording: Mapped[Recording] = relationship(back_populates="metadata_items")

class PublishedVideo(Base):
    __tablename__ = "published_videos"
    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(40), default="youtube")
    external_video_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    visibility: Mapped[str] = mapped_column(String(40), default="unlisted")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recording: Mapped[Recording] = relationship(back_populates="publications")

class Integration(Base):
    __tablename__ = "integrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="not_connected")

class StudentConsent(Base):
    __tablename__ = "student_consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_student_id: Mapped[str] = mapped_column(String(255), index=True)
    photo_video_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin | editor | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Incremented on password change, role change or deactivation; invalidates issued tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

Index("ix_jobs_status_created", ProcessingJob.status, ProcessingJob.created_at)

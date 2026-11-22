from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str = "ok"

class DashboardSummary(BaseModel):
    total_recordings: int
    published_videos: int
    processing: int
    failed_jobs: int

class RecordingCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    status: str = Field(default="uploaded", max_length=40)
    duration_seconds: int | None = Field(default=None, ge=0)

class RecordingUpdate(BaseModel):
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=40)
    duration_seconds: int | None = Field(default=None, ge=0)

class RecordingOut(ORMModel):
    id: int
    filename: str
    status: str
    duration_seconds: int | None
    file_path: str | None
    file_size_bytes: int | None = None
    content_type: str | None = None
    checksum_sha256: str | None = None
    created_at: datetime

class JobCreate(BaseModel):
    recording_id: int
    job_type: str = Field(min_length=1, max_length=80)

class JobOut(ORMModel):
    id: int
    recording_id: int | None
    job_type: str
    status: str
    progress: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempts: int = 0
    result: dict | None = None
    project_id: int | None = None

class QueueStatus(BaseModel):
    mode: str
    broker_ok: bool
    workers: int
    detail: str | None
    job_types: list[str]

class TranscriptCreate(BaseModel):
    recording_id: int
    language: str | None = Field(default=None, max_length=20)
    content: str = ""

class TranscriptOut(ORMModel):
    id: int
    recording_id: int
    language: str | None
    content: str
    created_at: datetime

class VideoMetadataCreate(BaseModel):
    recording_id: int
    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    chapters_json: str | None = None
    thumbnail_path: str | None = Field(default=None, max_length=1024)

class VideoMetadataOut(ORMModel):
    id: int
    recording_id: int
    title: str | None
    description: str | None
    chapters_json: str | None
    thumbnail_path: str | None

class PublicationCreate(BaseModel):
    recording_id: int
    platform: str = Field(default="youtube", max_length=40)
    external_video_id: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=1024)
    visibility: str = Field(default="unlisted", max_length=40)

class PublicationOut(ORMModel):
    id: int
    recording_id: int
    platform: str
    external_video_id: str | None
    url: str | None
    visibility: str
    published_at: datetime | None

class IntegrationCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    is_enabled: bool = False
    status: str = Field(default="not_connected", max_length=40)

class IntegrationOut(ORMModel):
    id: int
    provider: str
    is_enabled: bool
    status: str

class ConsentCreate(BaseModel):
    external_student_id: str = Field(min_length=1, max_length=255)
    photo_video_allowed: bool

class ConsentOut(ORMModel):
    id: int
    external_student_id: str
    photo_video_allowed: bool
    checked_at: datetime


# ---- Phase 4: authentication & users ----
import re
from typing import Literal
from pydantic import field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
Role = Literal["admin", "editor", "viewer"]

def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address.")
    return value

class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.strip().lower()

class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=128)

class UserCreate(BaseModel):
    email: str = Field(max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=10, max_length=128)
    role: Role = "viewer"

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty.")
        return v

class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    new_password: str | None = Field(default=None, min_length=10, max_length=128)

class AuditLogOut(ORMModel):
    id: int
    user_id: int | None
    action: str
    detail: str | None
    ip_address: str | None
    created_at: datetime


# ---- Phase 5: files ----
class StorageSummary(BaseModel):
    files: int
    total_bytes: int
    max_upload_bytes: int
    allowed_extensions: list[str]
    disk_free_bytes: int | None

class FileLink(BaseModel):
    url: str
    expires_in: int
    filename: str


# ---- Phase 7 (manual track): hand-written metadata, chapters, transcript and publication log ----

class Chapter(BaseModel):
    time_seconds: int = Field(ge=0, le=86400 * 2)
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Chapter title cannot be empty.")
        return v

class MetadataSave(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    chapters: list[Chapter] = Field(default_factory=list, max_length=100)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        seen, out = set(), []
        for t in tags:
            t = t.strip()
            if not t:
                continue
            if len(t) > 50:
                raise ValueError("A tag can be at most 50 characters.")
            if t.lower() not in seen:
                seen.add(t.lower()); out.append(t)
        return out

class MetadataOut(BaseModel):
    id: int
    recording_id: int
    title: str | None
    description: str | None
    tags: list[str]
    chapters: list[Chapter]

class TranscriptSave(BaseModel):
    language: str | None = Field(default=None, max_length=20)
    content: str = Field(default="", max_length=500_000)

class ManualPublication(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    url: str | None = Field(default=None, max_length=1024)
    visibility: Literal["public", "unlisted", "private"] = "unlisted"

    @field_validator("platform")
    @classmethod
    def _strip_platform(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter where the video was published.")
        return v

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if not v:
            return None
        if not re.match(r"^https?://[^\s]+$", v, re.I):
            raise ValueError("The link must start with http:// or https://")
        return v

class ConsentUpdate(BaseModel):
    photo_video_allowed: bool

class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    recording: RecordingOut
    metadata: MetadataOut | None
    transcript: TranscriptOut | None
    publications: list[PublicationOut]


# ---- Editing projects (Phase 7-8) ----
class TimelineClip(BaseModel):
    recording_id: int
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    volume: float = Field(default=1.0, ge=0, le=2)  # 1 = unchanged, 0 = muted, 2 = twice as loud
    fade_in: float = Field(default=0.0, ge=0, le=30)
    fade_out: float = Field(default=0.0, ge=0, le=30)
    # picture look (Phase 11)
    filter: Literal["none", "grayscale", "sepia", "blur", "sharpen", "vignette"] = "none"
    brightness: float = Field(default=0.0, ge=-0.5, le=0.5)
    contrast: float = Field(default=1.0, ge=0.5, le=2.0)
    saturation: float = Field(default=1.0, ge=0, le=3.0)
    transition: Literal["none", "fade_black", "fade_white"] = "none"  # dip between this clip and the next (or fade-out at the very end)
    transition_duration: float = Field(default=0.5, ge=0.1, le=2.0)

class AudioTrack(BaseModel):
    """Background music or extra sound. start/end pick a part of the file; `at` is where it begins on the timeline."""
    recording_id: int
    start: float = Field(default=0.0, ge=0)
    end: float = Field(gt=0)
    at: float = Field(default=0.0, ge=0)
    volume: float = Field(default=1.0, ge=0, le=2)
    fade_in: float = Field(default=0.0, ge=0, le=30)
    fade_out: float = Field(default=0.0, ge=0, le=30)

class TextOverlay(BaseModel):
    """Text or subtitle shown on the exported video. Times are on the timeline (after cutting), in seconds."""
    text: str = Field(min_length=1, max_length=300)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    position: Literal["top", "center", "bottom"] = "bottom"
    size: int = Field(default=36, ge=12, le=120)
    color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    box: bool = True

class Timeline(BaseModel):
    clips: list[TimelineClip] = Field(default_factory=list, max_length=100)
    texts: list[TextOverlay] = Field(default_factory=list, max_length=200)
    audio: list[AudioTrack] = Field(default_factory=list, max_length=20)

class ProjectSave(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timeline: Timeline = Field(default_factory=Timeline)

class ProjectOut(BaseModel):
    id: int
    name: str
    timeline: Timeline
    duration_seconds: float
    created_at: datetime
    updated_at: datetime

class ProjectSummary(BaseModel):
    id: int
    name: str
    clip_count: int
    updated_at: datetime

class ProjectVersionOut(BaseModel):
    id: int
    label: str
    name: str
    clip_count: int
    duration_seconds: float
    created_at: datetime

class ExportRequest(BaseModel):
    resolution: str = "720p"
    fps: int = 30
    quality: str = "medium"

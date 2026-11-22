export type Page = "Dashboard" | "Recordings" | "Video Editor" | "Processing Queue" | "Academy Library" | "AI Content" | "Integrations" | "Consent Management" | "Settings";
export type Recording = { id: number; filename: string; status: string; duration_seconds: number | null; file_path: string | null; file_size_bytes: number | null; content_type: string | null; checksum_sha256: string | null; created_at: string };
export type JobResult = { duration_seconds?: number; width?: number | null; height?: number | null; fps?: number | null; video_codec?: string | null; audio_codec?: string | null; has_audio?: boolean; format?: string | null; recording_id?: number; size_bytes?: number; texts?: number; audio_tracks?: number };
export type Job = { id: number; recording_id: number | null; job_type: string; status: string; progress: number; error_message: string | null; created_at: string; started_at: string | null; finished_at: string | null; attempts: number; result: JobResult | null; project_id?: number | null };
export type QueueStatus = { mode: "redis" | "inline"; broker_ok: boolean; workers: number; detail: string | null; job_types: string[] };
export type Integration = { id: number; provider: string; is_enabled: boolean; status: string };
export type Consent = { id: number; external_student_id: string; photo_video_allowed: boolean; checked_at: string };
export type Publication = { id: number; recording_id: number; platform: string; external_video_id: string | null; url: string | null; visibility: string; published_at: string | null };
export type Summary = { total_recordings: number; published_videos: number; processing: number; failed_jobs: number };
export type StorageSummary = { files: number; total_bytes: number; max_upload_bytes: number; allowed_extensions: string[]; disk_free_bytes: number | null };
export type ApiState = "checking" | "online" | "offline";
export type FileLink = { url: string; expires_in: number; filename: string };
export type Chapter = { time_seconds: number; title: string };
export type WorkspaceData = {
  recording: Recording;
  metadata: { id: number; title: string | null; description: string | null; tags: string[]; chapters: Chapter[] } | null;
  transcript: { id: number; language: string | null; content: string; created_at: string } | null;
  publications: Publication[];
};

export type TimelineClip = { recording_id: number; start: number; end: number; volume?: number; fade_in?: number; fade_out?: number;
  filter?: ClipFilter; brightness?: number; contrast?: number; saturation?: number; transition?: ClipTransition; transition_duration?: number };
export type ClipFilter = "none" | "grayscale" | "sepia" | "blur" | "sharpen" | "vignette";
export type ClipTransition = "none" | "fade_black" | "fade_white";
export type AudioItem = { recording_id: number; start: number; end: number; at: number; volume: number; fade_in: number; fade_out: number };
export type TextItem = { text: string; start: number; end: number; position: "top" | "center" | "bottom"; size: number; color: string; box: boolean };
export type Project = { id: number; name: string; timeline: { clips: TimelineClip[]; texts?: TextItem[]; audio?: AudioItem[] }; duration_seconds: number; created_at: string; updated_at: string };
export type ProjectSummary = { id: number; name: string; clip_count: number; updated_at: string };
export type ProjectVersion = { id: number; label: string; name: string; clip_count: number; duration_seconds: number; created_at: string };

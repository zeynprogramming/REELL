import { FormEvent, useState } from "react";
import { Ban, Plus, Radio, RotateCcw, Trash2 } from "lucide-react";
import { api } from "../api";
import { Button, EmptyState, PageHeader, ProgressBar, StatusBadge } from "../components/ui";
import { dateLabel } from "../format";
import type { Job, QueueStatus, Recording } from "../types";

const JOB_LABELS: Record<string, string> = { video_validation: "Video validation", export_project: "Video export", transcription: "Transcription", metadata_generation: "Metadata generation", publication: "Publication" };
const LATER: Record<string, string> = { transcription: "Phase 7", metadata_generation: "Phase 7", publication: "Phase 8" };

function detail(job: Job) {
  if (job.status === "failed" || job.status === "cancelled") return <div className="job-detail err">{job.error_message || "No details."}</div>;
  const r = job.result;
  if (job.status === "completed" && r) {
    const parts = [r.width && r.height ? `${r.width}×${r.height}` : null, r.video_codec, r.fps ? `${r.fps} fps` : null, r.duration_seconds != null ? `${r.duration_seconds}s` : null, r.has_audio ? `audio ${r.audio_codec ?? ""}`.trim() : "no audio"].filter(Boolean);
    return <div className="job-detail">{parts.join(" · ")}{r.recording_id ? ` · saved as recording #${r.recording_id}` : ""}</div>;
  }
  return <div className="job-detail">{job.status === "processing" ? "Running on the worker…" : "Waiting for a worker…"}</div>;
}

export default function Queue({ jobs, recordings, queue, canEdit, loading, recordingName, runAction }: {
  jobs: Job[]; recordings: Recording[]; queue: QueueStatus | null; canEdit: boolean; loading: boolean; recordingName: (id: number | null) => string;
  runAction: (action: () => Promise<unknown>, message: string) => Promise<void>;
}) {
  const withFile = recordings.filter(r => r.file_path);
  const [recordingId, setRecordingId] = useState("");
  const [jobType, setJobType] = useState("video_validation");

  const create = (e: FormEvent) => { e.preventDefault(); if (!recordingId) return; void runAction(() => api<Job>("/api/jobs", { method: "POST", body: JSON.stringify({ recording_id: Number(recordingId), job_type: jobType }) }), "Job submitted to the queue."); };
  const post = (id: number, verb: "retry" | "cancel", msg: string) => runAction(() => api<Job>(`/api/jobs/${id}/${verb}`, { method: "POST" }), msg);
  const remove = (id: number) => { if (window.confirm("Delete this job record?")) void runAction(() => api<void>(`/api/jobs/${id}`, { method: "DELETE" }), "Job deleted."); };

  const healthy = queue?.broker_ok && (queue.mode === "inline" || queue.workers > 0);
  const banner = !queue ? { cls: "", title: "Checking the job queue…", text: "" }
    : healthy ? { cls: "ok", title: queue.mode === "inline" ? "Inline mode (development)" : `Worker online (${queue.workers})`, text: queue.mode === "inline" ? queue.detail ?? "" : "Jobs are picked up automatically." }
    : { cls: "bad", title: queue.broker_ok ? "No worker is running" : "Job queue unreachable", text: (queue.detail ?? "") + (queue.mode === "redis" ? " Start it with: docker compose up -d redis worker" : "") };

  return <>
    <PageHeader eyebrow="Workspace / Automation" title="Processing Queue" description="Jobs run in the background on a worker. Status and progress are written by the worker and cannot be edited by hand." />
    <div className="worker-banner" role="status"><i className={`worker-dot ${banner.cls}`} /><div><b>{banner.title}</b>{banner.text && <span>{banner.text}</span>}</div></div>

    {canEdit && <section className="panel form-panel"><div className="panel-head"><div><h2>Run a job</h2><p>Only the job types that really work are selectable. Transcription and publishing arrive in later phases.</p></div></div>
      <form className="inline-form" onSubmit={create}>
        <label>Recording (with uploaded file)<select value={recordingId} onChange={e => setRecordingId(e.target.value)} required><option value="">{withFile.length ? "Choose a recording…" : "No uploaded recordings yet"}</option>{withFile.map(r => <option key={r.id} value={r.id}>{r.filename}</option>)}</select></label>
        <label>Job type<select value={jobType} onChange={e => setJobType(e.target.value)}>{Object.keys(JOB_LABELS).map(t => { const ok = queue?.job_types.includes(t) ?? t === "video_validation"; return <option key={t} value={t} disabled={!ok}>{JOB_LABELS[t]}{ok ? "" : ` — ${LATER[t] ?? "later"}`}</option>; })}</select></label>
        <Button type="submit" disabled={!recordingId}><Plus size={16} /> Start job</Button>
      </form></section>}

    <section className="panel data-panel"><div className="panel-head"><div><h2>Jobs</h2><p>{jobs.length} job(s) · updates automatically while jobs are running</p></div></div>
      <div className="table-wrap"><table className="table-compact"><thead><tr><th>Job</th><th>Recording</th><th>Progress</th><th>Status</th><th>Result</th>{canEdit && <th>Actions</th>}</tr></thead><tbody>
        {jobs.map(j => <tr key={j.id}>
          <td><div className="file-cell"><div className="file-icon"><Radio size={18} /></div><div><b>{JOB_LABELS[j.job_type] ?? j.job_type.replace(/_/g, " ")}</b><div className="subtle">#{j.id} · {dateLabel(j.created_at)}{j.attempts > 1 ? ` · attempt ${j.attempts}` : ""}</div></div></div></td>
          <td style={{ maxWidth: 200 }}>{j.project_id ? `Project #${j.project_id}` : recordingName(j.recording_id)}</td>
          <td style={{ minWidth: 140 }}><ProgressBar value={j.progress} /><div className="progress-meta"><b>{j.progress}%</b></div></td>
          <td><StatusBadge status={j.status} /></td>
          <td>{detail(j)}</td>
          {canEdit && <td><div className="row-actions">
            {(j.status === "queued" || j.status === "processing") && <button className="mini-save" onClick={() => void post(j.id, "cancel", "Job cancelled.")}><Ban size={12} /> Cancel</button>}
            {(j.status === "failed" || j.status === "cancelled") && <button className="mini-save" onClick={() => void post(j.id, "retry", "Job re-submitted to the queue.")}><RotateCcw size={12} /> Retry</button>}
            <button className="danger-icon" aria-label="Delete job" onClick={() => remove(j.id)}><Trash2 size={15} /></button></div></td>}
        </tr>)}
        {!jobs.length && <tr><td colSpan={canEdit ? 6 : 5}>{loading ? <div className="empty-cell">Loading jobs…</div> : <EmptyState icon={<Radio size={22} />} title="The queue is empty" text="Upload a recording, then run a validation job to check it." />}</td></tr>}
      </tbody></table></div></section>
  </>;
}

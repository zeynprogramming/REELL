import { DragEvent, FormEvent, useCallback, useRef, useState } from "react";
import { AlertCircle, Download, Film, Pencil, HardDrive, Play, Plus, ShieldCheck, Trash2, Upload } from "lucide-react";
import { ApiError, absoluteUrl, api, uploadFile } from "../api";
import { Accordion, Alert, Button, EmptyState, Modal, PageHeader, ProgressBar, SectionHead, StatusBadge } from "../components/ui";
import { bytesLabel, dateLabel, durationLabel } from "../format";
import type { FileLink, Job, Recording, StorageSummary } from "../types";

type UploadItem = { id: number; name: string; size: number; pct: number; state: "waiting" | "uploading" | "done" | "error"; error?: string };
let nextUploadId = 1;

export default function Recordings({ recordings, filtered, loading, canEdit, storage, onChanged, runAction, onOpen }: {
  onOpen: (id: number) => void;
  recordings: Recording[]; filtered: Recording[]; loading: boolean; canEdit: boolean; storage: StorageSummary | null;
  onChanged: () => Promise<void> | void; runAction: (action: () => Promise<unknown>, message: string) => Promise<void>;
}) {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [over, setOver] = useState(false);
  const [name, setName] = useState("");
  const [fileError, setFileError] = useState("");
  const [playing, setPlaying] = useState<{ title: string; url: string } | null>(null);
  const [playerError, setPlayerError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const abortCurrent = useRef<(() => void) | null>(null);
  const busy = useRef(false);
  const queue = useRef<{ item: UploadItem; file: File }[]>([]);

  const patch = (id: number, change: Partial<UploadItem>) => setUploads(list => list.map(u => (u.id === id ? { ...u, ...change } : u)));

  const pump = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    let uploadedAny = false;
    while (queue.current.length) {
      const { item, file } = queue.current.shift()!;
      patch(item.id, { state: "uploading", pct: 0 });
      const handle = uploadFile<Recording>("/api/recordings/upload?filename=" + encodeURIComponent(file.name), file, pct => patch(item.id, { pct }));
      abortCurrent.current = handle.abort;
      try { await handle.promise; patch(item.id, { state: "done", pct: 100 }); uploadedAny = true; }
      catch (e) { patch(item.id, { state: "error", error: e instanceof Error ? e.message : "Upload failed." }); }
    }
    abortCurrent.current = null;
    busy.current = false;
    if (uploadedAny) await onChanged();
  }, [onChanged]);

  const addFiles = (files: FileList | File[]) => {
    setFileError("");
    const allowed = storage?.allowed_extensions ?? [];
    const limit = storage?.max_upload_bytes ?? Infinity;
    const accepted: UploadItem[] = [];
    for (const file of Array.from(files)) {
      const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
      const item: UploadItem = { id: nextUploadId++, name: file.name, size: file.size, pct: 0, state: "waiting" };
      if (allowed.length && !allowed.includes(ext)) { accepted.push({ ...item, state: "error", error: `Unsupported type. Allowed: ${allowed.join(", ")}` }); continue; }
      if (file.size > limit) { accepted.push({ ...item, state: "error", error: `Larger than the ${bytesLabel(limit)} limit` }); continue; }
      accepted.push(item); queue.current.push({ item, file });
    }
    setUploads(list => [...accepted, ...list].slice(0, 8));
    void pump();
  };

  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); if (canEdit && e.dataTransfer.files.length) addFiles(e.dataTransfer.files); };

  const getLink = (r: Recording, download: boolean) => api<FileLink>(`/api/recordings/${r.id}/file-link${download ? "?download=true" : ""}`);
  const play = async (r: Recording) => {
    setPlayerError("");
    try { const link = await getLink(r, false); setPlaying({ title: r.filename, url: absoluteUrl(link.url) }); }
    catch (e) { setFileError(e instanceof Error ? e.message : "Could not open the file."); }
  };
  const download = async (r: Recording) => {
    try { const link = await getLink(r, true); const a = document.createElement("a"); a.href = absoluteUrl(link.url); a.rel = "noopener"; document.body.appendChild(a); a.click(); a.remove(); }
    catch (e) { setFileError(e instanceof Error ? e.message : "Could not download the file."); }
  };

  const createRecord = (e: FormEvent) => { e.preventDefault(); if (!name.trim()) return; void runAction(() => api<Recording>("/api/recordings", { method: "POST", body: JSON.stringify({ filename: name.trim(), status: "uploaded" }) }), "Metadata-only record created (no file attached)."); setName(""); };
  const setStatus = (id: number, status: string) => runAction(() => api<Recording>(`/api/recordings/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }), "Recording status updated.");
  const validate = (r: Recording) => runAction(() => api<Job>("/api/jobs", { method: "POST", body: JSON.stringify({ recording_id: r.id, job_type: "video_validation" }) }), `Validation job submitted for “${r.filename}”. Follow it on the Processing Queue page.`);
  const remove = (r: Recording) => { if (!window.confirm(`Delete “${r.filename}”${r.file_path ? " and its stored file" : ""}? This cannot be undone.`)) return; void runAction(() => api<void>(`/api/recordings/${r.id}`, { method: "DELETE" }), "Recording deleted."); };

  return <>
    <PageHeader eyebrow="Workspace / Media" title="Recordings" description="Upload lesson videos, play them back and manage their status. Files are stored on the server; details are stored in PostgreSQL." />
    {fileError && <Alert tone="error" onClose={() => setFileError("")}>{fileError}</Alert>}

    <section className="storage-strip" aria-label="Storage">
      <div className="storage-cell"><small>Stored files</small><b>{storage ? storage.files : "—"}</b></div>
      <div className="storage-cell"><small>Space used</small><b>{storage ? bytesLabel(storage.total_bytes) : "—"}</b></div>
      <div className="storage-cell"><small>Server disk free</small><b>{storage ? bytesLabel(storage.disk_free_bytes) : "—"}</b></div>
      <div className="storage-cell"><small>Max file size</small><b>{storage ? bytesLabel(storage.max_upload_bytes) : "—"}</b></div>
    </section>

    {canEdit ? <>
      <div className={`dropzone ${over ? "over" : ""}`} onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
        <div className="drop-icon"><Upload size={26} /></div>
        <h3>Drag a recording here</h3>
        <p>Video: MP4, MOV, M4V, WebM, MKV, AVI. Audio: MP3, WAV, M4A, AAC, OGG{storage ? `, up to ${bytesLabel(storage.max_upload_bytes)} each` : ""}. Files are checked on the server and duplicates are rejected.</p>
        <Button arrow onClick={() => input.current?.click()}>Choose files</Button>
        <input ref={input} type="file" multiple hidden accept={(storage?.allowed_extensions ?? [".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"]).join(",")} onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
      </div>
      {uploads.length > 0 && <div className="upload-list" aria-live="polite">{uploads.map(u => <div key={u.id} className={`upload-item ${u.state}`}>
        <div className="file-icon">{u.state === "error" ? <AlertCircle size={18} /> : <Film size={18} />}</div>
        <div><b>{u.name}</b>{u.state === "uploading" || u.state === "waiting" ? <><ProgressBar value={u.pct} /><small>{u.state === "waiting" ? "Waiting…" : `${u.pct}% of ${bytesLabel(u.size)}`}</small></> : <small>{u.state === "done" ? `Uploaded · ${bytesLabel(u.size)}` : u.error}</small>}</div>
        <div>{u.state === "uploading" && <button className="mini-save" onClick={() => abortCurrent.current?.()}>Cancel</button>}{u.state === "waiting" && <button className="mini-save" onClick={() => { queue.current = queue.current.filter(q => q.item.id !== u.id); patch(u.id, { state: "error", error: "Cancelled" }); }}>Remove</button>}{(u.state === "done" || u.state === "error") && <StatusBadge status={u.state === "done" ? "completed" : "failed"} label={u.state === "done" ? "Done" : "Failed"} />}</div>
      </div>)}</div>}
    </> : <Alert tone="info">Your role is read-only. You can play and download recordings, but uploading needs an editor or administrator.</Alert>}

    <div className="section">
      <SectionHead title="All recordings" description={`${filtered.length} result(s)`} />
      <section className="panel data-panel"><div className="table-wrap"><table><thead><tr><th>Recording</th><th>Created</th><th>Size</th><th>Duration</th><th>Status</th><th>File</th>{canEdit && <th>Delete</th>}</tr></thead><tbody>
        {filtered.map(r => <tr key={r.id}>
          <td><div className="file-cell"><div className="file-icon"><Film size={18} /></div><div><b title={r.filename}>{r.filename}</b><div className="subtle">#{r.id}{r.checksum_sha256 ? ` · sha256 ${r.checksum_sha256.slice(0, 8)}…` : ""}</div></div></div></td>
          <td>{dateLabel(r.created_at)}</td><td>{bytesLabel(r.file_size_bytes)}</td><td>{durationLabel(r.duration_seconds)}</td>
          <td>{canEdit ? <select className="table-select" value={r.status} onChange={e => void setStatus(r.id, e.target.value)} aria-label={`Status of ${r.filename}`}>{["uploaded", "ready", "processing", "failed", "published"].map(s => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}</select> : <StatusBadge status={r.status} />}</td>
          <td><div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><button className="mini-save" onClick={() => onOpen(r.id)}><Pencil size={12} /> Details</button>{r.file_path ? <><button className="mini-save" onClick={() => void play(r)}><Play size={12} /> Play</button><button className="mini-save" onClick={() => void download(r)}><Download size={12} /> Download</button>{canEdit && <button className="mini-save" onClick={() => void validate(r)}><ShieldCheck size={12} /> Validate</button>}</> : <span className="subtle">No file attached</span>}</div></td>
          {canEdit && <td><button className="danger-icon" title="Delete recording" aria-label={`Delete ${r.filename}`} onClick={() => remove(r)}><Trash2 size={15} /></button></td>}
        </tr>)}
        {!filtered.length && <tr><td colSpan={canEdit ? 7 : 6}>{loading ? <div className="empty-cell">Loading recordings…</div> : <EmptyState icon={<HardDrive size={22} />} title={recordings.length ? "No recordings match your search" : "No recordings yet"} text={recordings.length ? "Try a different search term." : canEdit ? "Drop a video above to upload your first recording." : undefined} />}</td></tr>}
      </tbody></table></div></section>
    </div>

    {canEdit && <details className="panel form-panel" style={{ marginTop: 18 }}>
      <summary className="panel-head" style={{ cursor: "pointer", listStyle: "none" }}><div><h3>Create a record without a file</h3><p>Metadata only: nothing is uploaded. Use this to reserve an entry before the file is available.</p></div><Plus size={18} /></summary>
      <form className="inline-form" onSubmit={createRecord}><label>Recording name<input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Biology — Lesson 01" maxLength={255} required /></label><Button type="submit"><Plus size={16} /> Add record</Button></form>
    </details>}

    <div className="section">
      <SectionHead title="Good to know" />
      <Accordion items={[
        { question: "Which files can I upload?", answer: "Video (MP4, MOV, M4V, WebM, MKV, AVI) and audio files (MP3, WAV, M4A, AAC, OGG) for the editor's music track. The server checks the real file contents, not just the name, and rejects files that do not match." },
        { question: "What happens to a very large file or a repeated upload?", answer: "Files over the size limit are rejected while uploading, so they never fill the disk. If the exact same file was uploaded before, the server tells you which recording already has it instead of storing a copy." },
        { question: "Is the video processed or published after upload?", answer: "Not yet. Upload only stores the file and registers it. Transcription, editing and publishing arrive in later phases." },
        { question: "Who can see the files?", answer: "Only signed-in users. Play and download use a short-lived link (5 minutes) that is issued after you sign in." },
      ]} />
    </div>

    {playing && <Modal title={playing.title} onClose={() => setPlaying(null)}>
      <video controls autoPlay src={playing.url} onError={() => setPlayerError("This browser could not play the file. Try Download instead.")} />
      {playerError && <div className="modal-body"><Alert tone="error">{playerError}</Alert></div>}
    </Modal>}
  </>;
}

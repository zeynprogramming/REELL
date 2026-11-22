import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Clock, ExternalLink, Plus, Save, Trash2 } from "lucide-react";
import { absoluteUrl, api } from "../api";
import { Alert, Button, EmptyState, PageHeader, Skeleton, StatusBadge } from "../components/ui";
import { bytesLabel, dateLabel, durationLabel } from "../format";
import type { FileLink, Publication, WorkspaceData } from "../types";

const clock = (s: number) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60; return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(x).padStart(2, "0")}`; };
const parseClock = (v: string): number | null => { const p = v.trim().split(":"); if (p.length < 1 || p.length > 3 || p.some(x => !/^\d+$/.test(x))) return null; return p.reduce((a, x) => a * 60 + Number(x), 0); };
const PLATFORMS = ["YouTube", "Google Classroom", "Slack", "Website", "Other"];
type Row = { t: string; title: string };

export default function Workspace({ recordingId, canEdit, onBack, onChanged }: { recordingId: number; canEdit: boolean; onBack: () => void; onChanged: () => void }) {
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const [title, setTitle] = useState(""); const [description, setDescription] = useState(""); const [tags, setTags] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [lang, setLang] = useState(""); const [text, setText] = useState("");
  const [platform, setPlatform] = useState("YouTube"); const [url, setUrl] = useState(""); const [visibility, setVisibility] = useState("unlisted");

  const load = useCallback(async () => {
    try {
      const d = await api<WorkspaceData>(`/api/recordings/${recordingId}/workspace`);
      setData(d); setError("");
      setTitle(d.metadata?.title ?? ""); setDescription(d.metadata?.description ?? ""); setTags((d.metadata?.tags ?? []).join(", "));
      setRows((d.metadata?.chapters ?? []).map(c => ({ t: clock(c.time_seconds), title: c.title })));
      setLang(d.transcript?.language ?? ""); setText(d.transcript?.content ?? "");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load this recording."); }
    finally { setLoading(false); }
  }, [recordingId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!data?.recording.file_path || videoUrl) return;
    api<FileLink>(`/api/recordings/${recordingId}/file-link`).then(l => setVideoUrl(absoluteUrl(l.url))).catch(() => { /* the player simply stays hidden */ });
  }, [data, recordingId, videoUrl]);

  // Reports success only after the server accepted the change.
  const run = async (key: string, action: () => Promise<unknown>, ok: string) => {
    setBusy(key); setError(""); setNotice("");
    try { await action(); await load(); onChanged(); setNotice(ok); }
    catch (e) { setError(e instanceof Error ? e.message : "The action failed."); }
    finally { setBusy(""); }
  };

  const saveDetails = () => {
    const chapters: { time_seconds: number; title: string }[] = [];
    for (const r of rows) {
      const t = parseClock(r.t);
      if (t == null) { setError(`Chapter “${r.title || "untitled"}”: write the time like 1:30 or 0:05:10.`); return; }
      if (!r.title.trim()) { setError("Every chapter needs a title."); return; }
      chapters.push({ time_seconds: t, title: r.title.trim() });
    }
    void run("details", () => api(`/api/recordings/${recordingId}/metadata`, { method: "PUT", body: JSON.stringify({ title, description, tags: tags.split(",").map(x => x.trim()).filter(Boolean), chapters }) }), "Details saved.");
  };
  const saveTranscript = () => void run("transcript", () => api(`/api/recordings/${recordingId}/transcript`, { method: "PUT", body: JSON.stringify({ language: lang, content: text }) }), "Transcript saved.");
  const logPublication = () => void run("pub", async () => { await api(`/api/recordings/${recordingId}/publications`, { method: "POST", body: JSON.stringify({ platform, url, visibility }) }); setUrl(""); }, "Publication recorded. REEL did not upload anything; this is your own record.");
  const removePub = (p: Publication) => { if (window.confirm("Remove this publication record? The video itself is not affected.")) void run("pub", () => api(`/api/publications/${p.id}`, { method: "DELETE" }), "Publication record removed."); };
  const addChapter = (atCurrent: boolean) => setRows(r => [...r, { t: atCurrent && video.current ? clock(Math.floor(video.current.currentTime)) : "0:00", title: "" }]);
  const setRow = (i: number, patch: Partial<Row>) => setRows(r => r.map((x, k) => k === i ? { ...x, ...patch } : x));

  const rec = data?.recording;
  return <>
    <PageHeader eyebrow="Academy / Manual workspace" title={rec?.filename ?? "Recording"} description="Describe, chapter and track this video by hand. Nothing on this page uses AI."
      actions={<Button variant="secondary" onClick={onBack}><ArrowLeft size={16} /> Back</Button>} />
    {error && <Alert tone="error" onClose={() => setError("")}>{error}</Alert>}
    {notice && <Alert tone="success" onClose={() => setNotice("")}>{notice}</Alert>}
    {loading ? <section className="panel ws-card"><Skeleton h={220} /></section>
      : !rec ? <section className="panel"><EmptyState icon={<Clock size={22} />} title="Recording not found" text="It may have been deleted." /></section>
      : <div className="ws-grid">
        <div className="ws-col">
          <section className="panel ws-card">
            <div className="panel-head"><div><h2>Video</h2><p>{durationLabel(rec.duration_seconds)} · {bytesLabel(rec.file_size_bytes)} · added {dateLabel(rec.created_at)}</p></div><StatusBadge status={rec.status} /></div>
            {videoUrl ? <video ref={video} className="ws-video" src={videoUrl} controls preload="metadata" /> : <EmptyState icon={<Clock size={22} />} title={rec.file_path ? "Loading the player…" : "No video file attached"} text={rec.file_path ? undefined : "You can still write the details and transcript."} />}
          </section>
          <fieldset className="ws-set" disabled={!canEdit}>
            <section className="panel ws-card">
              <div className="panel-head"><div><h2>Details and chapters</h2><p>Title, description, tags and chapter markers, typed by you.</p></div></div>
              <label className="ws-field">Title<input value={title} onChange={e => setTitle(e.target.value)} maxLength={500} /></label>
              <label className="ws-field">Description<textarea rows={4} value={description} onChange={e => setDescription(e.target.value)} maxLength={10000} /></label>
              <label className="ws-field">Tags <small>separated by commas</small><input value={tags} onChange={e => setTags(e.target.value)} placeholder="python, week 3, homework" /></label>
              <div className="ws-sub"><b>Chapters</b><span className="subtle">{rows.length ? "Saved in time order." : "No chapters yet."}</span></div>
              {rows.map((r, i) => <div className="ws-row" key={i}>
                <input className="ws-time" aria-label="Chapter time" value={r.t} onChange={e => setRow(i, { t: e.target.value })} placeholder="0:00" />
                <input aria-label="Chapter title" value={r.title} onChange={e => setRow(i, { title: e.target.value })} placeholder="Chapter title" maxLength={200} />
                <button type="button" className="danger-icon" aria-label="Remove chapter" onClick={() => setRows(x => x.filter((_, k) => k !== i))}><Trash2 size={15} /></button>
              </div>)}
              <div className="ws-actions">
                <Button variant="secondary" onClick={() => addChapter(false)}><Plus size={15} /> Add chapter</Button>
                {videoUrl && <Button variant="secondary" onClick={() => addChapter(true)}><Clock size={15} /> Add at current time</Button>}
                <Button onClick={saveDetails} disabled={busy === "details"}><Save size={15} /> {busy === "details" ? "Saving…" : "Save details"}</Button>
              </div>
            </section>
          </fieldset>
        </div>
        <div className="ws-col">
          <fieldset className="ws-set" disabled={!canEdit}>
            <section className="panel ws-card">
              <div className="panel-head"><div><h2>Transcript</h2><p>Paste or type the text of the lesson. It is not generated automatically.</p></div></div>
              <label className="ws-field">Language<input value={lang} onChange={e => setLang(e.target.value)} placeholder="hy, en, ru…" maxLength={20} /></label>
              <label className="ws-field">Text<textarea rows={12} value={text} onChange={e => setText(e.target.value)} /></label>
              <div className="ws-actions"><span className="subtle">{text.length.toLocaleString()} characters</span><Button onClick={saveTranscript} disabled={busy === "transcript"}><Save size={15} /> {busy === "transcript" ? "Saving…" : "Save transcript"}</Button></div>
            </section>
            <section className="panel ws-card">
              <div className="panel-head"><div><h2>Publication log</h2><p>Note where you published this video yourself. REEL does not upload to any platform.</p></div></div>
              <div className="ws-row">
                <select aria-label="Platform" value={platform} onChange={e => setPlatform(e.target.value)}>{PLATFORMS.map(p => <option key={p}>{p}</option>)}</select>
                <select aria-label="Visibility" value={visibility} onChange={e => setVisibility(e.target.value)}><option value="public">Public</option><option value="unlisted">Unlisted</option><option value="private">Private</option></select>
              </div>
              <label className="ws-field">Link <small>optional</small><input type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…" maxLength={1024} /></label>
              <div className="ws-actions"><Button onClick={logPublication} disabled={busy === "pub"}><Plus size={15} /> Record publication</Button></div>
              {data!.publications.length === 0 ? <EmptyState icon={<ExternalLink size={22} />} title="Not recorded as published" />
                : <ul className="ws-pubs">{data!.publications.map(p => <li key={p.id}><div><b>{p.platform}</b> <span className="subtle">{p.visibility} · {dateLabel(p.published_at)}</span>{p.url && <div><a href={p.url} target="_blank" rel="noreferrer noopener">{p.url}</a></div>}</div>{canEdit && <button type="button" className="danger-icon" aria-label="Remove publication record" onClick={() => removePub(p)}><Trash2 size={15} /></button>}</li>)}</ul>}
            </section>
          </fieldset>
        </div>
      </div>}
  </>;
}

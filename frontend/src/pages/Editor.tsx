import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Clapperboard, Copy, Download, Film, History, Music, Play, Plus, Save, Scissors, Trash2 } from "lucide-react";
import { absoluteUrl, api } from "../api";
import { Alert, Button, EmptyState, PageHeader, ProgressBar } from "../components/ui";
import { bytesLabel } from "../format";
import type { AudioItem, ClipFilter, ClipTransition, FileLink, Job, Page, Project, ProjectSummary, ProjectVersion, Recording, TextItem, TimelineClip } from "../types";

type EClip = TimelineClip & { key: number };
type EText = TextItem & { key: number };
type EAudio = AudioItem & { key: number };
const isAudioFile = (name: string) => /\.(mp3|wav|m4a|aac|ogg)$/i.test(name);
const FILTER_NAMES: Record<ClipFilter, string> = { none: "None", grayscale: "Black & white", sepia: "Sepia", blur: "Blur", sharpen: "Sharpen", vignette: "Vignette" };
const TRANSITION_NAMES: Record<ClipTransition, string> = { none: "None", fade_black: "Dip to black", fade_white: "Dip to white" };
/** Approximate CSS version of the clip's look, so the preview is close to the export (the export uses FFmpeg). */
function previewFilter(c: TimelineClip | null): string {
  if (!c) return "none";
  const parts = [`brightness(${(1 + (c.brightness ?? 0) * 1.6).toFixed(2)})`, `contrast(${(c.contrast ?? 1).toFixed(2)})`, `saturate(${(c.saturation ?? 1).toFixed(2)})`];
  const f = c.filter ?? "none";
  if (f === "grayscale") parts.push("grayscale(1)"); else if (f === "sepia") parts.push("sepia(1)"); else if (f === "blur") parts.push("blur(2px)");
  return parts.join(" ");
}
const pct = (v: number | undefined) => Math.round((v ?? 1) * 100);
const newText = (start: number): TextItem => ({ text: "Your text", start: round(start), end: round(start + 3), position: "bottom", size: 36, color: "#ffffff", box: true });

/** Parse the text of an .srt subtitle file into timeline text items (bottom, white, boxed). */
function parseSrt(raw: string): TextItem[] {
  const time = (h: string, m: string, sec: string, ms: string) => Number(h) * 3600 + Number(m) * 60 + Number(sec) + Number(ms.padEnd(3, "0")) / 1000;
  const out: TextItem[] = [];
  for (const block of raw.replace(/\r/g, "").split(/\n{2,}/)) {
    const lines = block.split("\n").filter(l => l.trim() !== "");
    const at = lines.findIndex(l => l.includes("-->"));
    if (at < 0) continue;
    const m = lines[at].match(/(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)/);
    const text = lines.slice(at + 1).join("\n").replace(/<[^>]+>/g, "").trim();
    if (!m || !text) continue;
    const start = time(m[1], m[2], m[3], m[4]), end = time(m[5], m[6], m[7], m[8]);
    if (end > start) out.push({ text: text.slice(0, 300), start: round(start), end: round(end), position: "bottom", size: 36, color: "#ffffff", box: true });
  }
  return out;
}
const MIN_LEN = 0.2;
let keyCounter = 1;
const withKey = (c: TimelineClip): EClip => ({ ...c, key: keyCounter++ });
const round = (n: number) => Math.round(n * 100) / 100;
const clock = (s: number) => `${Math.floor(s / 60)}:${(Math.floor(s % 60) + "").padStart(2, "0")}.${Math.floor((s % 1) * 10)}`;
const num = (v: string, fallback: number) => { const n = Number(v.replace(",", ".")); return Number.isFinite(n) ? n : fallback; };

export default function Editor({ recordings, jobs, canEdit, onChanged, setPage }: {
  recordings: Recording[]; jobs: Job[]; canEdit: boolean; onChanged: () => void; setPage: (p: Page) => void;
}) {
  const usable = useMemo(() => recordings.filter(r => r.file_path && r.duration_seconds), [recordings]);
  const byId = useMemo(() => new Map(recordings.map(r => [r.id, r])), [recordings]);

  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [name, setName] = useState("Untitled project");
  const [clips, setClips] = useState<EClip[]>([]);
  const [texts, setTexts] = useState<EText[]>([]);
  const [audio, setAudio] = useState<EAudio[]>([]);
  const [dirty, setDirty] = useState(false);
  const rev = useRef(0);                         // counts edits, so a save never marks newer edits as saved
  const markDirty = () => { rev.current += 1; setDirty(true); };
  const [autoMsg, setAutoMsg] = useState("");
  const [history, setHistory] = useState<ProjectVersion[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [resolution, setResolution] = useState("720p");
  const [fps, setFps] = useState(30);
  const [quality, setQuality] = useState("medium");
  const [exportJobId, setExportJobId] = useState<number | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const links = useRef(new Map<number, { url: string; at: number }>());
  const [cue, setCue] = useState<{ key: number; autoplay: boolean } | null>(null);
  const [sequence, setSequence] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [previewError, setPreviewError] = useState("");

  const total = clips.reduce((a, c) => a + (c.end - c.start), 0);
  const sel = clips.find(c => c.key === selected) ?? null;
  const selIndex = sel ? clips.indexOf(sel) : -1;
  const exportsOfProject = projectId == null ? [] : jobs.filter(j => j.project_id === projectId && j.job_type === "export_project").slice(0, 8);
  const exportJob = exportJobId != null ? jobs.find(j => j.id === exportJobId) ?? null : null;

  const loadProjects = useCallback(async () => {
    try { setProjects(await api<ProjectSummary[]>("/api/projects")); } catch (e) { setError(e instanceof Error ? e.message : "Could not load projects."); }
  }, []);
  useEffect(() => { void loadProjects(); }, [loadProjects]);

  const edit = (next: EClip[]) => { setClips(next); markDirty(); };
  const editTexts = (next: EText[]) => { setTexts(next); markDirty(); };
  const patchText = (key: number, values: Partial<TextItem>) => editTexts(texts.map(t => (t.key === key ? { ...t, ...values } : t)));
  const [srtOpen, setSrtOpen] = useState(false);
  const [srtRaw, setSrtRaw] = useState("");
  // Where the playhead is on the whole timeline (after cutting), used to place text and to preview it.
  const tlPos = useMemo(() => {
    if (!sel) return 0;
    let before = 0;
    for (const c of clips) { if (c.key === sel.key) break; before += c.end - c.start; }
    return before + Math.max(0, Math.min(playhead - sel.start, sel.end - sel.start));
  }, [clips, sel, playhead]);
  const activeTexts = texts.filter(t => tlPos >= t.start && tlPos <= t.end);
  const addText = () => { const t = { ...newText(tlPos), key: keyCounter++ }; editTexts([...texts, t]); };
  const editAudio = (next: EAudio[]) => { setAudio(next); markDirty(); };
  const patchAudio = (key: number, values: Partial<AudioItem>) => editAudio(audio.map(a => (a.key === key ? { ...a, ...values } : a)));
  const addAudio = (r: Recording) => {
    const len = r.duration_seconds ?? 0;
    editAudio([...audio, { key: keyCounter++, recording_id: r.id, start: 0, end: len, at: round(Math.min(tlPos, Math.max(0, total - 0.5))), volume: 0.6, fade_in: 1, fade_out: 1 }]);
  };
  const importSrt = () => {
    const items = parseSrt(srtRaw);
    if (!items.length) { setError("No subtitles found. Paste the contents of an .srt file."); return; }
    editTexts([...texts, ...items.map(t => ({ ...t, key: keyCounter++ }))]); setSrtOpen(false); setSrtRaw(""); setNotice(`${items.length} subtitle(s) imported.`);
  };
  const patch = (key: number, values: Partial<TimelineClip>) => edit(clips.map(c => (c.key === key ? { ...c, ...values } : c)));
  const maxOf = (c: EClip) => byId.get(c.recording_id)?.duration_seconds ?? c.end;

  // ---- project actions ----
  const newProject = () => {
    if (dirty && !window.confirm("Discard unsaved changes?")) return;
    setProjectId(null); setHistory(null); setAutoMsg(""); setName("Untitled project"); setClips([]); setTexts([]); setAudio([]); setSelected(null); setDirty(false); setExportJobId(null); setCue(null); setError(""); setNotice("");
  };
  const applyProject = (p: Project) => {
    setProjectId(p.id); setName(p.name); setClips(p.timeline.clips.map(withKey)); setTexts((p.timeline.texts ?? []).map(t => ({ ...t, key: keyCounter++ })));
    setAudio((p.timeline.audio ?? []).map(a => ({ ...a, key: keyCounter++ }))); setSelected(null); setDirty(false); setCue(null); setAutoMsg(""); setHistory(null);
  };
  const openProject = async (id: number) => {
    if (dirty && !window.confirm("Discard unsaved changes?")) return;
    setError(""); setNotice("");
    try {
      applyProject(await api<Project>(`/api/projects/${id}`)); setExportJobId(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not open the project."); }
  };
  const projectBody = () => JSON.stringify({ name: name.trim() || "Untitled project", timeline: { clips: clips.map(({ key: _c, ...c }) => ({ ...c, start: round(c.start), end: round(c.end), volume: c.volume ?? 1, fade_in: c.fade_in ?? 0, fade_out: c.fade_out ?? 0 })),
      audio: audio.map(({ key: _a, ...a }) => ({ ...a, start: round(a.start), end: round(a.end), at: round(a.at) })), texts: texts.map(({ key: _k, ...t }) => ({ ...t, start: round(t.start), end: round(t.end) })) } });
  const save = async (): Promise<number | null> => {
    setError(""); setNotice("");
    const body = projectBody(), myRev = rev.current;
    try {
      const p = projectId == null ? await api<Project>("/api/projects", { method: "POST", body }) : await api<Project>(`/api/projects/${projectId}`, { method: "PUT", body });
      setProjectId(p.id); if (rev.current === myRev) setDirty(false); setNotice("Project saved."); setAutoMsg(""); void loadProjects(); if (history) void loadHistory(p.id);
      return p.id;
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save the project."); return null; }
  };
  const removeProject = async () => {
    if (projectId == null || !window.confirm(`Delete the project “${name}”? Exported videos are kept.`)) return;
    try { await api<void>(`/api/projects/${projectId}`, { method: "DELETE" }); newProjectForce(); void loadProjects(); setNotice("Project deleted."); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not delete the project."); }
  };
  const newProjectForce = () => { setProjectId(null); setHistory(null); setAutoMsg(""); setName("Untitled project"); setClips([]); setTexts([]); setAudio([]); setSelected(null); setDirty(false); setExportJobId(null); setCue(null); };

  const startExport = async () => {
    if (!clips.length) { setError("Add at least one clip before exporting."); return; }
    setBusy(true);
    try {
      const id = dirty || projectId == null ? await save() : projectId;
      if (id == null) return;
      const job = await api<Job>(`/api/projects/${id}/export`, { method: "POST", body: JSON.stringify({ resolution, fps, quality }) });
      setExportJobId(job.id); setNotice("Export started. It runs in the background; progress is shown below."); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start the export."); }
    finally { setBusy(false); }
  };

  // ---- autosave (existing projects only) and leaving the page ----
  useEffect(() => {
    if (!dirty || projectId == null || busy) return;
    const myRev = rev.current;
    const timer = setTimeout(() => {
      api<Project>(`/api/projects/${projectId}?autosave=true`, { method: "PUT", body: projectBody() })
        .then(() => { if (rev.current === myRev) setDirty(false); setAutoMsg(`Autosaved ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`); })
        .catch(e => setAutoMsg(`Autosave paused: ${e instanceof Error ? e.message : "error"}`));
    }, 4000);
    return () => clearTimeout(timer);
  }, [dirty, projectId, busy, name, clips, texts, audio]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // ---- history ----
  const loadHistory = async (id: number) => {
    try { setHistory(await api<ProjectVersion[]>(`/api/projects/${id}/versions`)); } catch (e) { setError(e instanceof Error ? e.message : "Could not load the history."); }
  };
  const restoreVersion = async (v: ProjectVersion) => {
    if (projectId == null || !window.confirm(`Restore “${v.name}” (${v.label}, ${new Date(v.created_at).toLocaleString()})? Your current state is kept in the history first.`)) return;
    try {
      applyProject(await api<Project>(`/api/projects/${projectId}/versions/${v.id}/restore`, { method: "POST" }));
      setNotice("Version restored."); void loadProjects(); void loadHistory(projectId);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not restore the version."); }
  };

  // ---- timeline editing ----
  const addClip = (r: Recording) => {
    const c = withKey({ recording_id: r.id, start: 0, end: r.duration_seconds ?? 0 });
    edit([...clips, c]); setSelected(c.key); setCue({ key: c.key, autoplay: false });
  };
  const move = (dir: -1 | 1) => {
    if (selIndex < 0) return; const j = selIndex + dir; if (j < 0 || j >= clips.length) return;
    const next = clips.slice(); [next[selIndex], next[j]] = [next[j], next[selIndex]]; edit(next);
  };
  const duplicate = () => { if (!sel) return; const copy = withKey({ recording_id: sel.recording_id, start: sel.start, end: sel.end }); const next = clips.slice(); next.splice(selIndex + 1, 0, copy); edit(next); setSelected(copy.key); };
  const remove = () => { if (!sel) return; const next = clips.filter(c => c.key !== sel.key); edit(next); setSelected(next[Math.min(selIndex, next.length - 1)]?.key ?? null); };
  const split = () => {
    if (!sel) return;
    const t = round(playhead);
    if (t <= sel.start + MIN_LEN || t >= sel.end - MIN_LEN) { setError("Move the playhead inside the selected clip (not at its very start or end), then press Split."); return; }
    setError("");
    const right = withKey({ recording_id: sel.recording_id, start: t, end: sel.end });
    const next = clips.slice(); next[selIndex] = { ...sel, end: t }; next.splice(selIndex + 1, 0, right); edit(next);
  };
  const setStart = (v: number) => { if (sel) patch(sel.key, { start: round(Math.max(0, Math.min(v, sel.end - MIN_LEN))) }); };
  const setEnd = (v: number) => { if (sel) patch(sel.key, { end: round(Math.min(maxOf(sel), Math.max(v, sel.start + MIN_LEN))) }); };

  // ---- preview ----
  const select = (c: EClip) => { setSequence(false); setSelected(c.key); setCue({ key: c.key, autoplay: false }); };
  const playAll = () => { if (clips.length) { setSequence(true); setSelected(clips[0].key); setCue({ key: clips[0].key, autoplay: true }); } };

  useEffect(() => {
    if (!cue) return;
    const clip = clips.find(c => c.key === cue.key); const video = videoRef.current;
    if (!clip || !video) return;
    let cancelled = false;
    (async () => {
      try {
        setPreviewError("");
        let entry = links.current.get(clip.recording_id);
        if (!entry || Date.now() - entry.at > 4 * 60_000) { // signed links last 5 minutes
          const link = await api<FileLink>(`/api/recordings/${clip.recording_id}/file-link`);
          entry = { url: absoluteUrl(link.url), at: Date.now() }; links.current.set(clip.recording_id, entry);
        }
        if (cancelled) return;
        const begin = () => { video.currentTime = clip.start; if (cue.autoplay) void video.play().catch(() => undefined); };
        if (video.dataset.rec === String(clip.recording_id) && video.readyState >= 1) { begin(); }
        else { video.dataset.rec = String(clip.recording_id); video.src = entry.url; video.addEventListener("loadedmetadata", begin, { once: true }); video.load(); }
      } catch (e) { if (!cancelled) setPreviewError(e instanceof Error ? e.message : "Could not load the preview."); }
    })();
    return () => { cancelled = true; };
  }, [cue]); // eslint-disable-line react-hooks/exhaustive-deps

  const onTime = () => {
    const video = videoRef.current; if (!video) return;
    setPlayhead(video.currentTime);
    if (!sel || video.paused) return;
    if (video.currentTime >= sel.end - 0.04) {
      const next = sequence ? clips[selIndex + 1] : undefined;
      if (next) { setSelected(next.key); setCue({ key: next.key, autoplay: true }); }
      else { video.pause(); setSequence(false); }
    }
  };

  if (!canEdit) return <>
    <PageHeader eyebrow="Workspace / Editor" title="Video Editor" description="Your role is read-only. Ask an administrator for the Editor role to cut and export videos." />
    <section className="panel"><EmptyState icon={<Clapperboard size={22} />} title="Editing is disabled for viewers" /></section>
  </>;

  return <>
    <PageHeader eyebrow="Workspace / Editor" title="Video Editor" description="Cut, split and join your recordings on a timeline, then export the result as an MP4. Rendering runs in the background."
      actions={<div className="editor-actions"><Button variant="secondary" onClick={newProject}><Plus size={16} /> New project</Button></div>} />
    {error && <Alert tone="error" onClose={() => setError("")}>{error}</Alert>}
    {notice && <Alert tone="success" onClose={() => setNotice("")}>{notice}</Alert>}

    <section className="panel editor-bar">
      <label>Project name<input value={name} maxLength={200} onChange={e => { setName(e.target.value); markDirty(); }} /></label>
      <label>Open project<select value={projectId ?? ""} onChange={e => e.target.value && void openProject(Number(e.target.value))}>
        <option value="">{projects.length ? "Choose a saved project…" : "No saved projects"}</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.clip_count} clips)</option>)}</select></label>
      <Button onClick={() => void save()} disabled={!dirty && projectId != null}><Save size={16} /> {dirty ? "Save" : "Saved"}</Button>
      {projectId != null && <button className="mini-save" onClick={() => (history ? setHistory(null) : void loadHistory(projectId))}><History size={12} /> History</button>}
      <span className="autosave-note" aria-live="polite">{projectId == null ? "Save once to turn on autosave." : dirty ? "Unsaved changes…" : autoMsg || "All changes saved."}</span>
      {projectId != null && <button className="danger-icon" aria-label="Delete project" onClick={() => void removeProject()}><Trash2 size={15} /></button>}
    </section>

    <div className="editor-grid">
      <section className="panel editor-media"><div className="panel-head"><div><h2>Media</h2><p>Videos and audio files with a validated length.</p></div></div>
        <ul className="media-list">{usable.map(r => <li key={r.id}><Film size={16} /><span title={r.filename}>{r.filename}<em>{clock(r.duration_seconds ?? 0)}</em></span>
          {isAudioFile(r.filename)
            ? <button className="mini-save" onClick={() => addAudio(r)}><Music size={12} /> As audio</button>
            : <><button className="mini-save" onClick={() => addClip(r)}><Plus size={12} /> Add</button><button className="mini-save" title="Use this file's sound as background audio" onClick={() => addAudio(r)}><Music size={12} /></button></>}</li>)}
          {!usable.length && <li className="media-empty">No usable files. Upload a video or audio file on the Recordings page and press <b>Validate</b> so its length is known.{" "}<button className="text-btn" onClick={() => setPage("Recordings")}>Go to Recordings →</button></li>}</ul></section>

      <section className="panel editor-preview"><div className="panel-head"><div><h2>Preview</h2><p>{sel ? `Clip ${selIndex + 1} of ${clips.length} · playhead ${clock(playhead)}` : "Select a clip on the timeline."}</p></div>
        <Button variant="secondary" onClick={playAll} disabled={!clips.length}><Play size={16} /> Play timeline</Button></div>
        <div className="video-wrap">
          <video ref={videoRef} className="editor-video" style={{ filter: previewFilter(sel) }} controls playsInline onTimeUpdate={onTime} onError={() => setPreviewError("This browser could not play the file.")} />
          {activeTexts.map(t => <div key={t.key} className={`text-overlay ${t.position}`} style={{ color: t.color, fontSize: `${Math.max(10, t.size * 0.45)}px`, background: t.box ? "rgba(0,0,0,.55)" : "transparent" }}>{t.text}</div>)}
        </div>
        {previewError && <div className="modal-body"><Alert tone="error">{previewError}</Alert></div>}
        {sel && <div className="clip-tools">
          <label>Start (s)<input type="number" step="0.1" min={0} value={sel.start} onChange={e => setStart(num(e.target.value, sel.start))} /></label>
          <label>End (s)<input type="number" step="0.1" min={0} max={maxOf(sel)} value={sel.end} onChange={e => setEnd(num(e.target.value, sel.end))} /></label>
          <button className="mini-save" onClick={() => setStart(playhead)}>Start = playhead</button>
          <button className="mini-save" onClick={() => setEnd(playhead)}>End = playhead</button>
          <button className="mini-save" onClick={split}><Scissors size={12} /> Split at playhead</button>
          <label>Volume (%)<input type="number" min={0} max={200} step={5} value={pct(sel.volume)} onChange={e => patch(sel.key, { volume: Math.max(0, Math.min(200, num(e.target.value, 100))) / 100 })} /></label>
          <label>Fade in (s)<input type="number" min={0} max={30} step={0.5} value={sel.fade_in ?? 0} onChange={e => patch(sel.key, { fade_in: Math.min(30, Math.max(0, num(e.target.value, 0))) })} /></label>
          <label>Fade out (s)<input type="number" min={0} max={30} step={0.5} value={sel.fade_out ?? 0} onChange={e => patch(sel.key, { fade_out: Math.min(30, Math.max(0, num(e.target.value, 0))) })} /></label>
          <button className="mini-save" onClick={() => patch(sel.key, { volume: (sel.volume ?? 1) === 0 ? 1 : 0 })}>{(sel.volume ?? 1) === 0 ? "Unmute" : "Mute clip"}</button>
        </div>}
        {sel && <div className="clip-tools look-tools">
          <label>Filter<select value={sel.filter ?? "none"} onChange={e => patch(sel.key, { filter: e.target.value as ClipFilter })}>{(Object.keys(FILTER_NAMES) as ClipFilter[]).map(f => <option key={f} value={f}>{FILTER_NAMES[f]}</option>)}</select></label>
          <label>Brightness {Math.round((sel.brightness ?? 0) * 100)}<input type="range" min={-0.5} max={0.5} step={0.05} value={sel.brightness ?? 0} onChange={e => patch(sel.key, { brightness: Number(e.target.value) })} /></label>
          <label>Contrast {(sel.contrast ?? 1).toFixed(2)}<input type="range" min={0.5} max={2} step={0.05} value={sel.contrast ?? 1} onChange={e => patch(sel.key, { contrast: Number(e.target.value) })} /></label>
          <label>Saturation {(sel.saturation ?? 1).toFixed(2)}<input type="range" min={0} max={3} step={0.1} value={sel.saturation ?? 1} onChange={e => patch(sel.key, { saturation: Number(e.target.value) })} /></label>
          <button className="mini-save" onClick={() => patch(sel.key, { filter: "none", brightness: 0, contrast: 1, saturation: 1 })}>Reset look</button>
          <label>Transition after this clip<select value={sel.transition ?? "none"} onChange={e => patch(sel.key, { transition: e.target.value as ClipTransition })}>{(Object.keys(TRANSITION_NAMES) as ClipTransition[]).map(t => <option key={t} value={t}>{TRANSITION_NAMES[t]}</option>)}</select></label>
          {(sel.transition ?? "none") !== "none" && <label>Length (s)<input type="number" min={0.1} max={2} step={0.1} value={sel.transition_duration ?? 0.5} onChange={e => patch(sel.key, { transition_duration: Math.min(2, Math.max(0.1, num(e.target.value, 0.5))) })} /></label>}
          <p className="hint">The preview approximates the look; the exported video is rendered by FFmpeg. A transition fades out this clip and fades in the next one (the last clip fades out at the end). It cannot be longer than half of either clip.</p>
        </div>}
      </section>
    </div>

    <section className="panel editor-timeline"><div className="panel-head"><div><h2>Timeline</h2><p>{clips.length} clip(s) · total {clock(total)}. Clips play in order; trim, split, reorder or add clips from other recordings to merge.</p></div>
      {sel && <div className="row-actions">
        <button className="mini-save" onClick={() => move(-1)} disabled={selIndex === 0}><ArrowLeft size={12} /> Earlier</button>
        <button className="mini-save" onClick={() => move(1)} disabled={selIndex === clips.length - 1}>Later <ArrowRight size={12} /></button>
        <button className="mini-save" onClick={duplicate}><Copy size={12} /> Duplicate</button>
        <button className="danger-icon" aria-label="Remove clip" onClick={remove}><Trash2 size={15} /></button></div>}</div>
      {clips.length ? <div className="track" role="list">{clips.map((c, i) => <button key={c.key} role="listitem" className={`clip ${c.key === selected ? "on" : ""}`} style={{ flexGrow: Math.max(c.end - c.start, 1), minWidth: 96 }} onClick={() => select(c)}>
        <b>{i + 1}. {byId.get(c.recording_id)?.filename ?? `Recording #${c.recording_id}`}</b><span>{clock(c.start)} → {clock(c.end)} · {clock(c.end - c.start)}</span></button>)}</div>
        : <EmptyState icon={<Clapperboard size={22} />} title="The timeline is empty" text="Add a recording from the Media list to start." />}
    </section>

    <section className="panel editor-audio"><div className="panel-head"><div><h2>Music &amp; audio</h2><p>Background music or extra sound mixed under the video. Add files with “As audio” in the Media list. The preview plays only the clips' own sound; the mix is applied on export.</p></div></div>
      {audio.length ? <ul className="text-list">{audio.map(a => <li key={a.key}>
        <div className="audio-name"><Music size={16} /> <b>{byId.get(a.recording_id)?.filename ?? `File #${a.recording_id}`}</b></div>
        <label>From (s)<input type="number" step="0.1" min={0} value={a.start} onChange={e => patchAudio(a.key, { start: Math.max(0, num(e.target.value, a.start)) })} /></label>
        <label>To (s)<input type="number" step="0.1" min={0} value={a.end} onChange={e => patchAudio(a.key, { end: Math.min(byId.get(a.recording_id)?.duration_seconds ?? a.end, Math.max(0, num(e.target.value, a.end))) })} /></label>
        <label>Starts at (s)<input type="number" step="0.1" min={0} value={a.at} onChange={e => patchAudio(a.key, { at: Math.min(100000, Math.max(0, num(e.target.value, a.at))) })} /></label>
        <label>Volume (%)<input type="number" min={0} max={200} step={5} value={pct(a.volume)} onChange={e => patchAudio(a.key, { volume: Math.max(0, Math.min(200, num(e.target.value, 100))) / 100 })} /></label>
        <label>Fade in (s)<input type="number" min={0} max={30} step={0.5} value={a.fade_in} onChange={e => patchAudio(a.key, { fade_in: Math.min(30, Math.max(0, num(e.target.value, 0))) })} /></label>
        <label>Fade out (s)<input type="number" min={0} max={30} step={0.5} value={a.fade_out} onChange={e => patchAudio(a.key, { fade_out: Math.min(30, Math.max(0, num(e.target.value, 0))) })} /></label>
        <button className="danger-icon" aria-label="Remove audio" onClick={() => editAudio(audio.filter(x => x.key !== a.key))}><Trash2 size={15} /></button></li>)}</ul>
        : <EmptyState icon={<Music size={22} />} title="No music yet" text="Upload an MP3, WAV, M4A, AAC or OGG file, validate it, then press “As audio”." />}
    </section>

    <section className="panel editor-texts"><div className="panel-head"><div><h2>Text &amp; subtitles</h2><p>Times are on the timeline (after cutting). The preview above shows them; they are drawn into the video on export.</p></div>
      <div className="row-actions"><button className="mini-save" onClick={addText}><Plus size={12} /> Add text at playhead</button><button className="mini-save" onClick={() => setSrtOpen(v => !v)}>Import .srt</button></div></div>
      {srtOpen && <div className="srt-box"><textarea rows={6} placeholder="Paste the contents of an .srt file here" value={srtRaw} onChange={e => setSrtRaw(e.target.value)} />
        <input type="file" accept=".srt,text/plain" onChange={e => { const f = e.target.files?.[0]; if (f) void f.text().then(setSrtRaw); }} />
        <Button onClick={importSrt} disabled={!srtRaw.trim()}>Import</Button></div>}
      {texts.length ? <ul className="text-list">{texts.map(t => <li key={t.key}>
        <textarea rows={2} maxLength={300} value={t.text} onChange={e => patchText(t.key, { text: e.target.value })} aria-label="Text" />
        <label>From (s)<input type="number" step="0.1" min={0} value={t.start} onChange={e => patchText(t.key, { start: num(e.target.value, t.start) })} /></label>
        <label>To (s)<input type="number" step="0.1" min={0} value={t.end} onChange={e => patchText(t.key, { end: num(e.target.value, t.end) })} /></label>
        <label>Position<select value={t.position} onChange={e => patchText(t.key, { position: e.target.value as TextItem["position"] })}><option value="top">Top</option><option value="center">Center</option><option value="bottom">Bottom</option></select></label>
        <label>Size<input type="number" min={12} max={120} value={t.size} onChange={e => patchText(t.key, { size: Math.max(12, Math.min(120, Math.round(num(e.target.value, t.size)))) })} /></label>
        <label>Color<input type="color" value={t.color} onChange={e => patchText(t.key, { color: e.target.value })} /></label>
        <label className="check"><input type="checkbox" checked={t.box} onChange={e => patchText(t.key, { box: e.target.checked })} /> Background</label>
        <button className="danger-icon" aria-label="Remove text" onClick={() => editTexts(texts.filter(x => x.key !== t.key))}><Trash2 size={15} /></button></li>)}</ul>
        : <EmptyState icon={<Clapperboard size={22} />} title="No text yet" text="Add a title or caption, or import subtitles from an .srt file." />}
    </section>

    {history && <section className="panel editor-history"><div className="panel-head"><div><h2>History</h2><p>Every manual save, export and restore is kept (the latest 30). Autosave does not add entries.</p></div></div>
      {history.length ? <ul className="history-list">{history.map(v => <li key={v.id}><div><b>{v.label}</b> · {v.name}<span>{new Date(v.created_at).toLocaleString()} · {v.clip_count} clip(s) · {clock(v.duration_seconds)}</span></div>
        <button className="mini-save" onClick={() => void restoreVersion(v)}>Restore</button></li>)}</ul> : <EmptyState icon={<History size={22} />} title="No history yet" text="Save the project to create the first entry." />}
    </section>}

    <section className="panel editor-export"><div className="panel-head"><div><h2>Export</h2><p>Creates a new MP4 recording. Output is re-encoded (H.264 + AAC) so clips with different sizes can be joined.</p></div></div>
      <div className="inline-form">
        <label>Resolution<select value={resolution} onChange={e => setResolution(e.target.value)}><option>480p</option><option>720p</option><option>1080p</option></select></label>
        <label>Frame rate<select value={fps} onChange={e => setFps(Number(e.target.value))}>{[24, 25, 30, 60].map(f => <option key={f} value={f}>{f} fps</option>)}</select></label>
        <label>Quality<select value={quality} onChange={e => setQuality(e.target.value)}><option value="low">Low (small file)</option><option value="medium">Medium</option><option value="high">High</option></select></label>
        <Button onClick={() => void startExport()} disabled={busy || !clips.length || exportJob?.status === "queued" || exportJob?.status === "processing"}><Download size={16} /> Export MP4</Button>
      </div>
      {projectId != null && exportsOfProject.length > 0 && <div className="export-list"><h3>Exports of this project</h3><ul>{exportsOfProject.map(j => <li key={j.id}>
        <span>#{j.id} · {j.status}{j.status === "processing" ? ` ${j.progress}%` : ""}{j.created_at ? ` · ${new Date(j.created_at).toLocaleString()}` : ""}</span>
        {j.status === "completed" && j.result?.recording_id ? <button className="text-btn" onClick={() => setPage("Recordings")}>Recording #{j.result.recording_id} →</button> : j.status === "failed" ? <em className="job-detail err">{j.error_message}</em> : null}</li>)}</ul></div>}
      {exportJob && <div className="export-status">
        <ProgressBar value={exportJob.progress} />
        <div className="progress-meta"><b>{exportJob.status} · {exportJob.progress}%</b>
          {exportJob.status === "failed" && <span className="job-detail err">{exportJob.error_message}</span>}
          {exportJob.status === "completed" && exportJob.result && <span>Done: {exportJob.result.width}×{exportJob.result.height} · {clock(exportJob.result.duration_seconds ?? 0)} · {bytesLabel(exportJob.result.size_bytes)} — find it on <button className="text-btn" onClick={() => setPage("Recordings")}>Recordings</button> or the <button className="text-btn" onClick={() => setPage("Academy Library")}>Library</button>.</span>}
        </div></div>}
    </section>
  </>;
}

import { Activity, AlertCircle, ArrowUpRight, Archive, CloudUpload, Film, Radio, Upload, Video } from "lucide-react";
import { Button, EmptyState, ProgressBar, SectionHead, Skeleton, StatusBadge } from "../components/ui";
import { bytesLabel, dateLabel } from "../format";
import type { Job, Page, Publication, Recording, Summary } from "../types";

export default function Dashboard({ summary, recordings, jobs, publications, loading, loaded, canEdit, userName, setPage, recordingName, onRefresh }: {
  summary: Summary; recordings: Recording[]; jobs: Job[]; publications: Publication[]; loading: boolean; loaded: boolean; canEdit: boolean;
  userName: string; setPage: (p: Page) => void; recordingName: (id: number | null) => string; onRefresh: () => void;
}) {
  const stats: { label: string; value: number; foot: string; icon: typeof Video; page: Page }[] = [
    { label: "Total Recordings", value: summary.total_recordings, foot: "Recordings stored in the database", icon: Video, page: "Recordings" },
    { label: "Published Videos", value: summary.published_videos, foot: "Publication records", icon: CloudUpload, page: "Dashboard" },
    { label: "Processing", value: summary.processing, foot: "Jobs currently marked processing", icon: Activity, page: "Processing Queue" },
    { label: "Failed Jobs", value: summary.failed_jobs, foot: "Jobs that need attention", icon: AlertCircle, page: "Processing Queue" },
  ];
  const activity = [
    ...recordings.slice(0, 3).map(r => ({ id: `r${r.id}`, title: r.file_path ? "Recording uploaded" : "Recording record created", description: r.filename, date: r.created_at })),
    ...jobs.slice(0, 3).map(j => ({ id: `j${j.id}`, title: `Processing job ${j.status}`, description: `${j.job_type.replace(/_/g, " ")} · ${recordingName(j.recording_id)}`, date: j.created_at })),
    ...publications.slice(0, 2).filter(p => p.published_at).map(p => ({ id: `p${p.id}`, title: `Published to ${p.platform}`, description: recordingName(p.recording_id), date: p.published_at as string })),
  ].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()).slice(0, 5);

  return <>
    <section className="hero">
      <div className="eyebrow">Welcome back, {userName.split(" ")[0]}</div>
      <h1>Turn every lesson recording into a published video.</h1>
      <p>Upload class recordings, track processing jobs and keep student consent in order, all in one workspace.</p>
      <div className="hero-actions">
        {canEdit && <Button onDark arrow onClick={() => setPage("Recordings")}><Upload size={16} /> Upload a recording</Button>}
        <Button variant="secondary" onClick={() => setPage("Processing Queue")}>View processing queue</Button>
      </div>
    </section>

    <div className="section" style={{ marginTop: 28 }}>
      <section className="stats-grid" aria-label="Key figures">
        {stats.map((s, i) => { const Icon = s.icon; return <div key={s.label} className={`stat-card ${i % 2 === 0 ? "a" : "b"}`}>
          <div className="stat-label"><Icon size={17} />{s.label}</div>
          <div><div className="stat-value">{loaded ? s.value : <Skeleton w={80} h={52} />}</div><div className="stat-foot">{s.foot}</div></div>
          <button className="stat-hit" aria-label={`Open ${s.page}`} onClick={() => setPage(s.page)} />
          <div className="stat-corner"><span><ArrowUpRight size={20} /></span></div>
        </div>; })}
      </section>
    </div>

    <div className="section">
      <SectionHead title="Recent recordings" description="Latest items in your library" action={<button className="text-btn" onClick={() => setPage("Recordings")}>View all →</button>} />
      <div className="section-grid">
        <section className="panel">
          <div className="table-wrap"><table className="table-compact"><thead><tr><th>Recording</th><th>Added</th><th>Size</th><th>Status</th></tr></thead><tbody>
            {recordings.slice(0, 5).map(r => <tr key={r.id}><td><div className="file-cell"><div className="file-icon"><Film size={18} /></div><b>{r.filename}</b></div></td><td>{dateLabel(r.created_at)}</td><td>{bytesLabel(r.file_size_bytes)}</td><td><StatusBadge status={r.status} /></td></tr>)}
            {!recordings.length && <tr><td colSpan={4}>{loaded ? <EmptyState icon={<Film size={22} />} title="No recordings yet" text={canEdit ? "Upload your first lesson recording from the Recordings page." : "Recordings will appear here once an editor uploads them."} /> : <div style={{ padding: 20 }}><Skeleton h={18} /></div>}</td></tr>}
          </tbody></table></div>
          <div className="panel-foot"><span>{recordings.length} recording(s) loaded</span><span>Source: PostgreSQL</span></div>
        </section>

        <section className="panel">
          <div className="panel-head"><div><h2>Processing queue</h2><p>Jobs from the API</p></div><button className="text-btn" onClick={() => setPage("Processing Queue")}>View all →</button></div>
          <div className="queue-list">
            {jobs.slice(0, 4).map(j => <div className="queue-item" key={j.id}>
              <div className="queue-file"><div className="file-icon"><Radio size={17} /></div><div><b>{j.job_type.replace(/_/g, " ")}</b><small>{recordingName(j.recording_id)}</small></div><StatusBadge status={j.status} /></div>
              <ProgressBar value={j.progress} /><div className="progress-meta"><span>{j.error_message || j.status}</span><b>{j.progress}%</b></div>
            </div>)}
            {!jobs.length && <EmptyState icon={<Radio size={22} />} title="Queue is empty" text="No processing jobs have been created." />}
          </div>
        </section>
      </div>
    </div>

    <div className="section">
      <div className="section-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <section className="panel">
          <div className="panel-head"><div><h2>Recent publications</h2><p>Publication records in the database</p></div></div>
          <div className="table-wrap"><table className="table-compact"><thead><tr><th>Recording</th><th>Platform</th><th>Visibility</th><th>Published</th></tr></thead><tbody>
            {publications.slice(0, 5).map(p => <tr key={p.id}><td><b>{recordingName(p.recording_id)}</b></td><td style={{ textTransform: "capitalize" }}>{p.platform}</td><td>{p.visibility}</td><td>{dateLabel(p.published_at)}</td></tr>)}
            {!publications.length && <tr><td colSpan={4}><EmptyState icon={<CloudUpload size={22} />} title="Nothing published yet" text="Publishing to YouTube and other platforms arrives in a later phase." /></td></tr>}
          </tbody></table></div>
        </section>
        <section className="panel">
          <div className="panel-head"><div><h2>Activity log</h2><p>Latest recording, job and publication records</p></div><button className="text-btn" disabled={loading} onClick={onRefresh}>Refresh ↻</button></div>
          <div className="activity-list">
            {activity.map(a => <div className="activity-row" key={a.id}><div className="activity-dot"><Archive size={16} /></div><div><b>{a.title}</b><p>{a.description}</p></div><time>{dateLabel(a.date)}</time></div>)}
            {!activity.length && <EmptyState icon={<Archive size={22} />} title="No activity yet" text="Activity appears here as you add data." />}
          </div>
        </section>
      </div>
    </div>
  </>;
}

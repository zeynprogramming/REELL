import { useState } from "react";
import { Film, Library as LibraryIcon, Play } from "lucide-react";
import { absoluteUrl, api } from "../api";
import VideoModal from "../components/VideoModal";
import { Alert, Button, EmptyState, PageHeader, Skeleton, StatusBadge } from "../components/ui";
import { bytesLabel, dateLabel, durationLabel } from "../format";
import type { FileLink, Page, Recording } from "../types";

export default function Library({ recordings, loading, loaded, canEdit, setPage, onOpen }: {
  onOpen: (id: number) => void;
  recordings: Recording[]; loading: boolean; loaded: boolean; canEdit: boolean; setPage: (p: Page) => void;
}) {
  const videos = recordings.filter(r => r.file_path);
  const [playing, setPlaying] = useState<{ title: string; url: string } | null>(null);
  const [error, setError] = useState("");

  const watch = async (r: Recording) => {
    setError("");
    try { const link = await api<FileLink>(`/api/recordings/${r.id}/file-link`); setPlaying({ title: r.filename, url: absoluteUrl(link.url) }); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not open the video."); }
  };

  return <>
    <PageHeader eyebrow="Academy / Videos" title="Academy Library" description="Every uploaded lesson recording, ready to watch. Search with the box at the top of the page."
      actions={canEdit ? <Button variant="secondary" onClick={() => setPage("Recordings")}>Upload a recording</Button> : undefined} />
    {error && <Alert tone="error" onClose={() => setError("")}>{error}</Alert>}
    {!loaded && loading ? <div className="library-grid">{[0, 1, 2].map(i => <div key={i} className="lib-card b"><Skeleton h={150} /><Skeleton w="70%" h={18} /><Skeleton w="40%" h={14} /></div>)}</div>
      : videos.length === 0 ? <section className="panel"><EmptyState icon={<LibraryIcon size={22} />} title="The library is empty" text={canEdit ? "Upload a lesson recording and it will appear here." : "Videos will appear here once an editor uploads them."} /></section>
      : <div className="library-grid">{videos.map((r, i) => <article key={r.id} className={`lib-card ${i % 2 === 0 ? "a" : "b"}`}>
          <button className="lib-poster" onClick={() => void watch(r)} aria-label={`Play ${r.filename}`}><span className="lib-play"><Play size={26} /></span><span className="lib-length">{durationLabel(r.duration_seconds)}</span></button>
          <div className="lib-body"><h3 title={r.filename}><Film size={16} /> {r.filename}</h3>
            <p>{dateLabel(r.created_at)} · {bytesLabel(r.file_size_bytes)}</p>
            <div className="lib-foot"><StatusBadge status={r.status} /><span style={{ display: "flex", gap: 14 }}><button className="text-btn" onClick={() => onOpen(r.id)}>Details</button><button className="text-btn" onClick={() => void watch(r)}>Watch →</button></span></div></div>
        </article>)}</div>}
    {playing && <VideoModal title={playing.title} url={playing.url} onClose={() => setPlaying(null)} />}
  </>;
}

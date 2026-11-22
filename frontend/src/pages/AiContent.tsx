import { Captions, ListTree, Lock, Sparkles, Tags } from "lucide-react";
import { Alert, Button, PageHeader } from "../components/ui";
import type { Page } from "../types";

const PLANNED = [
  { icon: Captions, title: "Transcription", text: "Turn the speech in a lesson recording into searchable text and subtitles." },
  { icon: Sparkles, title: "Title & description drafts", text: "Suggest a title and summary that an editor reviews before use." },
  { icon: ListTree, title: "Chapter suggestions", text: "Propose chapter markers with timestamps from the lesson structure." },
  { icon: Tags, title: "Tags", text: "Suggest topic tags to make lessons easier to find." },
];

export default function AiContent({ setPage }: { setPage: (p: Page) => void }) {
  return <>
    <PageHeader eyebrow="Academy / Experimental" title="AI Content" description="A preview of planned AI features. They are switched off in this deployment." />
    <Alert tone="info" action={{ label: "Open Recordings", onClick: () => setPage("Recordings") }}>AI is not connected, so these tools do not work. You can do the same jobs by hand: open a recording and press Details to write the title, chapters, tags and transcript yourself.</Alert>
    <section className="ai-banner">
      <span className="badge-exp"><Lock size={13} /> Experimental · disabled</span>
      <h2>AI features are not active in this version</h2>
      <p>No recording, audio or transcript is sent to any external AI service, and nothing here generates content. The section is kept so the product shows where AI will fit once it is enabled and reviewed for student privacy.</p>
    </section>
    <div className="ai-grid">{PLANNED.map(p => { const Icon = p.icon; return <div className="panel ai-card" key={p.title}>
      <div className="integration-symbol"><Icon size={20} /></div><h3>{p.title}</h3><p>{p.text}</p><Button variant="secondary" disabled>Not available (AI is off)</Button></div>; })}</div>
  </>;
}

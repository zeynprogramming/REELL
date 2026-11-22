import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "./api";
import { canEdit as roleCanEdit, type CurrentUser } from "./auth";
import { Alert } from "./components/ui";
import { Footer, TopBar } from "./components/Layout";
import Consents from "./pages/Consents";
import Dashboard from "./pages/Dashboard";
import Integrations from "./pages/Integrations";
import AiContent from "./pages/AiContent";
import Library from "./pages/Library";
import Queue from "./pages/Queue";
import Workspace from "./pages/Workspace";
import Editor from "./pages/Editor";
import Recordings from "./pages/Recordings";
import SettingsPage from "./Settings";
import type { ApiState, Consent, Integration, Job, Page, Publication, QueueStatus, Recording, StorageSummary, Summary } from "./types";

const EMPTY_SUMMARY: Summary = { total_recordings: 0, published_videos: 0, processing: 0, failed_jobs: 0 };
const THEME_KEY = "reel.theme";
const readTheme = () => { try { return localStorage.getItem(THEME_KEY) !== "dark"; } catch { return true; } };

export default function AppShell({ user, onUserChange, onLogout }: { user: CurrentUser; onUserChange: (u: CurrentUser) => void; onLogout: () => void }) {
  const canEdit = roleCanEdit(user);
  const [page, setPage] = useState<Page>("Dashboard");
  const [workId, setWorkId] = useState<number | null>(null);
  const [light, setLight] = useState(readTheme);
  const [search, setSearch] = useState("");
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [summary, setSummary] = useState<Summary>(EMPTY_SUMMARY);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [publications, setPublications] = useState<Publication[]>([]);
  const [storage, setStorage] = useState<StorageSummary | null>(null);
  const [queue, setQueue] = useState<QueueStatus | null>(null);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      await api<{ status: string }>("/api/health");
      setApiState("online");
      const [s, r, j, i, c, p, st, qs] = await Promise.all([
        api<Summary>("/api/dashboard/summary"), api<Recording[]>("/api/recordings?limit=100"), api<Job[]>("/api/jobs?limit=100"),
        api<Integration[]>("/api/integrations"), api<Consent[]>("/api/consents"), api<Publication[]>("/api/publications"), api<StorageSummary>("/api/storage/summary"), api<QueueStatus>("/api/system/status"),
      ]);
      setSummary(s); setRecordings(r); setJobs(j); setIntegrations(i); setConsents(c); setPublications(p); setStorage(st); setQueue(qs);
      setError(""); setLoaded(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return; // the sign-in screen takes over
      setApiState(e instanceof ApiError && e.status > 0 ? "online" : "offline");
      if (silent) return; // background polling stays quiet; the status pill still turns red
      setError(e instanceof ApiError && e.status === 0 || e instanceof TypeError
        ? "Cannot reach the REEL API. Check that the backend is running."
        : e instanceof Error ? e.message : "Could not load data.");
    } finally { if (!silent) setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const toggleTheme = () => setLight(v => { const next = !v; try { localStorage.setItem(THEME_KEY, next ? "light" : "dark"); } catch { /* storage unavailable */ } return next; });
  const goTo = (p: Page) => { setWorkId(null); setPage(p); setError(""); setNotice(""); window.scrollTo({ top: 0 }); };

  // Runs a write action, refreshes, and reports only what really happened.
  const runAction = useCallback(async (action: () => Promise<unknown>, message: string) => {
    setError(""); setNotice("");
    try { await action(); await refresh(); setNotice(message); }
    catch (e) { setError(e instanceof Error ? e.message : "The action failed."); }
  }, [refresh]);

  const recordingName = useCallback((id: number | null) => (id == null ? "No recording" : recordings.find(r => r.id === id)?.filename ?? `Recording #${id}`), [recordings]);
  const q = search.trim().toLowerCase();
  const filteredRecordings = useMemo(() => recordings.filter(r => !q || `${r.filename} ${r.status}`.toLowerCase().includes(q)), [recordings, q]);
  const activeJobs = jobs.filter(j => j.status === "queued" || j.status === "processing").length;

  // While jobs are running, poll quietly so progress and results appear without a manual refresh.
  useEffect(() => {
    if (activeJobs === 0) return;
    const timer = setInterval(() => void refresh(true), 3000);
    return () => clearInterval(timer);
  }, [activeJobs, refresh]);

  return <div className={`app ${light ? "light" : "dark"}`}>
    <TopBar page={page} setPage={goTo} user={user} dark={!light} toggleTheme={toggleTheme} search={search} setSearch={setSearch} apiState={apiState} onRefresh={() => void refresh()} onLogout={onLogout} activeJobs={activeJobs} />
    <main className="content">
      {error && <Alert tone="error" onClose={() => setError("")} action={{ label: "Retry", onClick: () => void refresh() }}>{error}</Alert>}
      {notice && <Alert tone="success" onClose={() => setNotice("")}>{notice}</Alert>}
      {workId != null && <Workspace key={workId} recordingId={workId} canEdit={canEdit} onBack={() => setWorkId(null)} onChanged={() => void refresh(true)} />}
      {workId == null && page === "Dashboard" && <Dashboard summary={summary} recordings={filteredRecordings} jobs={jobs} publications={publications} loading={loading} loaded={loaded} canEdit={canEdit} userName={user.full_name} setPage={goTo} recordingName={recordingName} onRefresh={() => void refresh()} />}
      {workId == null && page === "Recordings" && <Recordings recordings={recordings} filtered={filteredRecordings} loading={loading} canEdit={canEdit} storage={storage} onChanged={() => refresh()} runAction={runAction} onOpen={setWorkId} />}
      {workId == null && page === "Video Editor" && <Editor recordings={recordings} jobs={jobs} canEdit={canEdit} onChanged={() => void refresh(true)} setPage={goTo} />}
      {workId == null && page === "Processing Queue" && <Queue jobs={jobs} recordings={recordings} queue={queue} canEdit={canEdit} loading={loading} recordingName={recordingName} runAction={runAction} />}
      {workId == null && page === "Integrations" && <Integrations integrations={integrations} canEdit={canEdit} runAction={runAction} />}
      {workId == null && page === "Consent Management" && <Consents consents={consents} canEdit={canEdit} runAction={runAction} />}
      {workId == null && page === "Settings" && <SettingsPage user={user} onUserChange={onUserChange} />}
      {workId == null && page === "Academy Library" && <Library recordings={filteredRecordings} loading={loading} loaded={loaded} canEdit={canEdit} setPage={goTo} onOpen={setWorkId} />}
      {workId == null && page === "AI Content" && <AiContent setPage={goTo} />}
    </main>
    <Footer apiState={apiState} setPage={goTo} />
  </div>;
}

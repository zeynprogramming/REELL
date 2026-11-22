import { Clapperboard, LogOut, Moon, RefreshCw, Search, Sun } from "lucide-react";
import type { CurrentUser } from "../auth";
import type { ApiState, Page } from "../types";
import { apiBaseUrl } from "../api";

export const NAV: Page[] = ["Dashboard", "Recordings", "Video Editor", "Processing Queue", "Academy Library", "AI Content", "Integrations", "Consent Management", "Settings"];

export function Logo({ onClick }: { onClick?: () => void }) {
  return <button className="logo" onClick={onClick} aria-label="REEL home"><span className="logo-mark"><Clapperboard size={20} /></span><span><b>REEL</b><small>VIDEO AUTOMATION</small></span></button>;
}

const apiLabel = (s: ApiState) => (s === "online" ? "API connected" : s === "offline" ? "API offline" : "Checking API");

export function TopBar(props: {
  page: Page; setPage: (p: Page) => void; user: CurrentUser; dark: boolean; toggleTheme: () => void;
  search: string; setSearch: (v: string) => void; apiState: ApiState; onRefresh: () => void; onLogout: () => void; activeJobs: number;
}) {
  const { page, setPage, user, dark, toggleTheme, search, setSearch, apiState, onRefresh, onLogout, activeJobs } = props;
  return <header className="topbar">
    <div className="topbar-row">
      <Logo onClick={() => setPage("Dashboard")} />
      <div className="top-actions">
        <label className="search-pill"><Search size={16} /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search recordings, jobs…" aria-label="Search" /></label>
        <div className={`api-pill ${apiState}`}><i /><span>{apiLabel(apiState)}</span></div>
        <button className="icon-btn" title="Refresh data" aria-label="Refresh data" onClick={onRefresh}><RefreshCw size={16} /></button>
        <button className="icon-btn" title="Toggle theme" aria-label="Toggle theme" onClick={toggleTheme}>{dark ? <Sun size={17} /> : <Moon size={17} />}</button>
        <div className="user-chip" title={user.email}><span className="user-avatar">{user.full_name.charAt(0).toUpperCase()}</span><div><span>{user.full_name}</span><small>{user.role}</small></div>
          <button className="icon-btn" title="Sign out" aria-label="Sign out" onClick={onLogout}><LogOut size={16} /></button></div>
      </div>
    </div>
    <div className="nav-row"><nav className="main-nav" aria-label="Main">
      {NAV.map(label => <button key={label} className={`nav-link ${page === label ? "active" : ""}`} aria-current={page === label ? "page" : undefined} onClick={() => setPage(label)}>
        {label}{label === "Processing Queue" && activeJobs > 0 && <i className="nav-count">{activeJobs}</i>}</button>)}
    </nav></div>
  </header>;
}

export function Footer({ apiState, setPage }: { apiState: ApiState; setPage: (p: Page) => void }) {
  return <footer className="footer">
    <div className="footer-inner">
      <div><Logo /><p>Video automation for the Academy: recordings, processing, publishing and consent in one workspace.</p></div>
      <div><h4>Workspace</h4><div className="footer-links">{(["Dashboard", "Recordings", "Processing Queue"] as Page[]).map(p => <button key={p} onClick={() => { setPage(p); window.scrollTo({ top: 0 }); }}>{p}</button>)}</div></div>
      <div><h4>System</h4><div className="footer-links">{(["Integrations", "Consent Management", "Settings"] as Page[]).map(p => <button key={p} onClick={() => { setPage(p); window.scrollTo({ top: 0 }); }}>{p}</button>)}</div></div>
    </div>
    <div className="footer-bar"><span>© 2026 REEL · Video Automation Platform</span><span><i className={`footer-dot ${apiState}`} />{apiLabel(apiState)} · {apiBaseUrl || window.location.origin} · v1.0.0</span></div>
  </footer>;
}

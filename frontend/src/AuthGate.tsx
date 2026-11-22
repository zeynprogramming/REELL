import { FormEvent, useCallback, useEffect, useState } from "react";
import { AlertCircle, Clapperboard, LogIn } from "lucide-react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";
import type { CurrentUser, TokenResponse } from "./auth";
import Workspace from "./App";

function LoginScreen({ onSignedIn, notice }: { onSignedIn: (user: CurrentUser) => void; notice: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const result = await api<TokenResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      setToken(result.access_token);
      onSignedIn(result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally { setBusy(false); }
  };

  return <div className="app light login-page">
    <form className="login-card" onSubmit={submit}>
      <div className="logo"><span className="logo-mark"><Clapperboard size={20} /></span><span><b>REEL</b><small>VIDEO AUTOMATION</small></span></div>
      <h1>Sign in</h1>
      <p>Use the account created by your administrator.</p>
      {notice && !error && <div className="app-alert error"><AlertCircle size={16} /><span>{notice}</span></div>}
      {error && <div className="app-alert error" role="alert"><AlertCircle size={16} /><span>{error}</span></div>}
      <label>Email<input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></label>
      <label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
      <button className="primary-btn" type="submit" disabled={busy}><LogIn size={16} /> {busy ? "Signing in…" : "Sign in"}</button>
    </form>
  </div>;
}

export default function AuthGate() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [checking, setChecking] = useState(Boolean(getToken()));
  const [notice, setNotice] = useState("");

  const signOut = useCallback((message = "") => { setToken(null); setUser(null); setNotice(message); }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => signOut("Your session has ended. Please sign in again."));
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  useEffect(() => {
    if (!getToken()) return;
    api<CurrentUser>("/api/auth/me")
      .then(setUser)
      .catch(() => { /* a 401 is handled by the unauthorized handler; other errors fall back to the login screen */ setToken(null); })
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <div className="app light login-page"><div className="login-card"><p>Checking session…</p></div></div>;
  if (!user) return <LoginScreen notice={notice} onSignedIn={u => { setNotice(""); setUser(u); }} />;
  return <Workspace user={user} onUserChange={setUser} onLogout={() => signOut()} />;
}

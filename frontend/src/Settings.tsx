import { FormEvent, useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, KeyRound, Plus, RefreshCw } from "lucide-react";
import { api, setToken } from "./api";
import type { CurrentUser, Role, TokenResponse } from "./auth";

type AuditEntry = { id: number; user_id: number | null; action: string; detail: string | null; ip_address: string | null; created_at: string };
const dateLabel = (v: string | null) => (v ? new Date(v).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—");

export default function Settings({ user, onUserChange, onSessionRenewed }: { user: CurrentUser; onUserChange: (u: CurrentUser) => void; onSessionRenewed?: () => void }) {
  const isAdmin = user.role === "admin";
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [users, setUsers] = useState<CurrentUser[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>("viewer");

  const loadAdminData = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const [u, a] = await Promise.all([api<CurrentUser[]>("/api/users"), api<AuditEntry[]>("/api/audit-logs?limit=15")]);
      setUsers(u); setAudit(a);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load administration data."); }
    finally { setLoading(false); }
  }, [isAdmin]);
  useEffect(() => { void loadAdminData(); }, [loadAdminData]);

  const run = async (action: () => Promise<unknown>, message: string) => {
    setError(""); setNotice("");
    try { await action(); setNotice(message); } catch (e) { setError(e instanceof Error ? e.message : "Action failed."); }
  };

  const changePassword = (e: FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) { setError("The new password and its confirmation do not match."); setNotice(""); return; }
    void run(async () => {
      const result = await api<TokenResponse>("/api/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
      setToken(result.access_token); onUserChange(result.user); onSessionRenewed?.();
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
    }, "Password changed. Other sessions were signed out.");
  };

  const createUser = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await api<CurrentUser>("/api/users", { method: "POST", body: JSON.stringify({ email: newEmail, full_name: newName, password: newUserPassword, role: newRole }) });
      setNewEmail(""); setNewName(""); setNewUserPassword(""); setNewRole("viewer");
      await loadAdminData();
    }, "User created.");
  };

  const updateUser = (id: number, body: Record<string, unknown>, message: string) =>
    run(async () => { await api<CurrentUser>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }); await loadAdminData(); }, message);

  return <>
    <div className="page-heading"><div><div className="eyebrow">SYSTEM / SECURITY</div><h1>Settings</h1><p>Your account{isAdmin ? ", user management and the security audit log." : " and password."}</p></div>{isAdmin && <button className="secondary-btn" onClick={() => void loadAdminData()}><RefreshCw size={15} /> Refresh</button>}</div>
    {error && <div className="app-alert error" role="alert"><AlertCircle size={16} /><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}
    {notice && <div className="app-alert success"><CheckCircle2 size={16} /><span>{notice}</span><button onClick={() => setNotice("")}>Dismiss</button></div>}

    <section className="panel form-panel">
      <div className="panel-head"><div><h2>My account</h2><p>{user.full_name} · {user.email} · role: <b>{user.role}</b> · last sign-in {dateLabel(user.last_login_at)}</p></div></div>
      <form className="inline-form multi" onSubmit={changePassword}>
        <label>Current password<input type="password" autoComplete="current-password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} required /></label>
        <label>New password (min. 10 characters)<input type="password" autoComplete="new-password" minLength={10} maxLength={128} value={newPassword} onChange={e => setNewPassword(e.target.value)} required /></label>
        <label>Confirm new password<input type="password" autoComplete="new-password" minLength={10} maxLength={128} value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required /></label>
        <button className="primary-btn" type="submit"><KeyRound size={16} /> Change password</button>
      </form>
    </section>

    {isAdmin && <>
      <section className="panel form-panel">
        <div className="panel-head"><div><h2>Create user</h2><p>Admin: full access · Editor: can change data · Viewer: read-only.</p></div></div>
        <form className="inline-form multi" onSubmit={createUser}>
          <label>Full name<input value={newName} onChange={e => setNewName(e.target.value)} maxLength={255} required /></label>
          <label>Email<input type="email" value={newEmail} onChange={e => setNewEmail(e.target.value)} maxLength={255} required /></label>
          <label>Initial password<input type="password" autoComplete="new-password" minLength={10} maxLength={128} value={newUserPassword} onChange={e => setNewUserPassword(e.target.value)} required /></label>
          <label>Role<select value={newRole} onChange={e => setNewRole(e.target.value as Role)}><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option></select></label>
          <button className="primary-btn" type="submit"><Plus size={16} /> Create user</button>
        </form>
      </section>

      <section className="panel data-panel">
        <div className="panel-head"><div><h2>Users</h2><p>{users.length} account(s)</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>NAME</th><th>EMAIL</th><th>ROLE</th><th>STATUS</th><th>LAST SIGN-IN</th><th>ACTIONS</th></tr></thead><tbody>
          {users.map(u => { const self = u.id === user.id; return <tr key={u.id}>
            <td><b>{u.full_name}</b>{self && <div className="subtle">You</div>}</td>
            <td>{u.email}</td>
            <td><select className="table-select" value={u.role} disabled={self} onChange={e => void updateUser(u.id, { role: e.target.value }, "Role updated. The user's active sessions were signed out.")}><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option></select></td>
            <td><span className={`status ${u.is_active ? "green" : "orange"}`}><i />{u.is_active ? "Active" : "Deactivated"}</span></td>
            <td>{dateLabel(u.last_login_at)}</td>
            <td>{!self && <button className="mini-save" onClick={() => void updateUser(u.id, { is_active: !u.is_active }, u.is_active ? "User deactivated and signed out." : "User reactivated.")}>{u.is_active ? "Deactivate" : "Reactivate"}</button>}</td>
          </tr>; })}
          {!users.length && <tr><td colSpan={6} className="empty-cell">{loading ? "Loading users…" : "No users found."}</td></tr>}
        </tbody></table></div>
      </section>

      <section className="panel data-panel">
        <div className="panel-head"><div><h2>Security audit log</h2><p>Latest {audit.length} sign-in and account events</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>WHEN</th><th>EVENT</th><th>USER ID</th><th>DETAIL</th><th>IP</th></tr></thead><tbody>
          {audit.map(a => <tr key={a.id}><td>{dateLabel(a.created_at)}</td><td><b>{a.action.replace(/_/g, " ")}</b></td><td>{a.user_id ?? "—"}</td><td>{a.detail ?? "—"}</td><td>{a.ip_address ?? "—"}</td></tr>)}
          {!audit.length && <tr><td colSpan={5} className="empty-cell">{loading ? "Loading…" : "No events recorded yet."}</td></tr>}
        </tbody></table></div>
      </section>
    </>}
  </>;
}

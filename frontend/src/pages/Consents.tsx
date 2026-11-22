import { FormEvent, useState } from "react";
import { Plus, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "../api";
import { Button, EmptyState, PageHeader, StatusBadge } from "../components/ui";
import { dateLabel } from "../format";
import type { Consent } from "../types";

export default function Consents({ consents, canEdit, runAction }: { consents: Consent[]; canEdit: boolean; runAction: (a: () => Promise<unknown>, m: string) => Promise<void> }) {
  const [studentId, setStudentId] = useState("");
  const [allowed, setAllowed] = useState("false");
  const create = (e: FormEvent) => { e.preventDefault(); if (!studentId.trim()) return; void runAction(() => api<Consent>("/api/consents", { method: "POST", body: JSON.stringify({ external_student_id: studentId.trim(), photo_video_allowed: allowed === "true" }) }), "Consent record saved."); setStudentId(""); };
  return <>
    <PageHeader eyebrow="System / Privacy" title="Consent Management" description="Photo and video consent records, referenced by an external student ID. Do not enter names or other personal details." />
    {canEdit && <section className="panel form-panel"><div className="panel-head"><div><h2>Add consent record</h2><p>Stores a reference ID and the consent decision.</p></div></div>
      <form className="inline-form" onSubmit={create}>
        <label>Student reference ID<input value={studentId} onChange={e => setStudentId(e.target.value)} placeholder="e.g. STU-1042" maxLength={255} required /></label>
        <label>Photo / video<select value={allowed} onChange={e => setAllowed(e.target.value)}><option value="false">Not allowed</option><option value="true">Allowed</option></select></label>
        <Button type="submit"><Plus size={16} /> Save consent</Button>
      </form></section>}
    <section className="panel data-panel"><div className="panel-head"><div><h2>Consent records</h2><p>{consents.length} record(s)</p></div></div>
      <div className="table-wrap"><table><thead><tr><th>ID</th><th>Student reference</th><th>Photo / video</th><th>Last checked</th>{canEdit && <th>Actions</th>}</tr></thead><tbody>
        {consents.map(c => <tr key={c.id}><td>#{c.id}</td><td><b>{c.external_student_id}</b></td><td><StatusBadge status={c.photo_video_allowed ? "allowed" : "denied"} label={c.photo_video_allowed ? "Allowed" : "Not allowed"} /></td><td>{dateLabel(c.checked_at)}</td>{canEdit && <td><div style={{ display: "flex", gap: 8 }}><button className="mini-save" onClick={() => void runAction(() => api<Consent>(`/api/consents/${c.id}`, { method: "PATCH", body: JSON.stringify({ photo_video_allowed: !c.photo_video_allowed }) }), "Consent updated.")}>{c.photo_video_allowed ? "Mark not allowed" : "Mark allowed"}</button><button className="danger-icon" aria-label="Delete consent record" onClick={() => { if (window.confirm(`Delete the consent record for ${c.external_student_id}?`)) void runAction(() => api<void>(`/api/consents/${c.id}`, { method: "DELETE" }), "Consent record deleted."); }}><Trash2 size={15} /></button></div></td>}</tr>)}
        {!consents.length && <tr><td colSpan={5}><EmptyState icon={<ShieldCheck size={22} />} title="No consent records yet" /></td></tr>}
      </tbody></table></div></section>
  </>;
}

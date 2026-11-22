import { FormEvent, useState } from "react";
import { Link2, Plus } from "lucide-react";
import { api } from "../api";
import { Alert, Button, EmptyState, PageHeader, StatusBadge } from "../components/ui";
import type { Integration } from "../types";

export default function Integrations({ integrations, canEdit, runAction }: { integrations: Integration[]; canEdit: boolean; runAction: (a: () => Promise<unknown>, m: string) => Promise<void> }) {
  const [provider, setProvider] = useState("YouTube");
  const create = (e: FormEvent) => { e.preventDefault(); void runAction(() => api<Integration>("/api/integrations", { method: "POST", body: JSON.stringify({ provider, is_enabled: false, status: "not_connected" }) }), "Integration entry saved. Connecting an external account is not part of this phase."); };
  return <>
    <PageHeader eyebrow="System / Connections" title="Integrations" description="A registry of external services. Real connections (YouTube, Slack, Google Classroom) arrive in later phases." />
    <Alert tone="info">Entries here are registry records only. No external account is connected and nothing is published.</Alert>
    {canEdit && <section className="panel form-panel"><div className="panel-head"><div><h2>Register integration</h2><p>Add a provider to the registry.</p></div></div>
      <form className="inline-form" onSubmit={create}><label>Provider<select value={provider} onChange={e => setProvider(e.target.value)}>{["YouTube", "Slack", "Google Classroom"].map(p => <option key={p}>{p}</option>)}</select></label><Button type="submit"><Plus size={16} /> Add integration</Button></form></section>}
    <section className="integration-grid">
      {integrations.map(i => <div className="panel integration-card" key={i.id}><div className="integration-symbol"><Link2 size={20} /></div><div className="integration-copy"><h3>{i.provider}</h3><p>Registry entry #{i.id}</p></div><StatusBadge status={i.status} /><small>{i.is_enabled ? "Enabled" : "Not enabled"}</small></div>)}
    </section>
    {!integrations.length && <section className="panel"><EmptyState icon={<Link2 size={22} />} title="No integrations registered" text="Register a provider above to track it here." /></section>}
  </>;
}

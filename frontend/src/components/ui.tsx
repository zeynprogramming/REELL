import { ButtonHTMLAttributes, ReactNode, useEffect } from "react";
import { AlertCircle, ArrowRight, CheckCircle2, Info, Plus, X } from "lucide-react";
import { statusTone } from "../format";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary"; arrow?: boolean; onDark?: boolean };

/** Pill button; `arrow` adds the circular arrow used throughout the Picsart Academy site. */
export function Button({ variant = "primary", arrow, onDark, className = "", children, type = "button", ...rest }: ButtonProps) {
  const cls = [variant === "primary" ? "primary-btn" : "secondary-btn", arrow ? "has-arrow" : "", onDark ? "on-dark" : "", className].filter(Boolean).join(" ");
  return <button type={type} className={cls} {...rest}>{children}{arrow && <span className="btn-arrow"><ArrowRight size={16} /></span>}</button>;
}

export function Alert({ tone, children, onClose, action }: { tone: "error" | "success" | "info"; children: ReactNode; onClose?: () => void; action?: { label: string; onClick: () => void } }) {
  const Icon = tone === "error" ? AlertCircle : tone === "success" ? CheckCircle2 : Info;
  return <div className={`app-alert ${tone}`} role={tone === "error" ? "alert" : "status"}>
    <Icon size={18} /><span>{children}</span>
    {action && <button onClick={action.onClick}>{action.label}</button>}
    {onClose && <button onClick={onClose}>Dismiss</button>}
  </div>;
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <span className={`status ${statusTone(status)}`}><i />{(label ?? status).replace(/_/g, " ")}</span>;
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions}</div>;
}

export function SectionHead({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="section-head"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>;
}

export function EmptyState({ icon, title, text }: { icon: ReactNode; title: string; text?: string }) {
  return <div className="empty-state"><div className="empty-icon">{icon}</div><b>{title}</b>{text && <span>{text}</span>}</div>;
}

export function ProgressBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return <div className="progress-line" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><i style={{ width: `${pct}%` }} /></div>;
}

export function Skeleton({ w = "100%", h = 16 }: { w?: string | number; h?: number }) {
  return <div className="skeleton" style={{ width: w, height: h }} aria-hidden />;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-head"><h3>{title}</h3><button className="icon-btn" aria-label="Close" onClick={onClose}><X size={18} /></button></div>
      {children}
    </div>
  </div>;
}

export function Accordion({ items }: { items: { question: string; answer: string }[] }) {
  return <div className="faq">{items.map(item => <details key={item.question}><summary>{item.question}<span className="plus"><Plus size={16} /></span></summary><p>{item.answer}</p></details>)}</div>;
}

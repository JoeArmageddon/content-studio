import { Link } from "react-router-dom";

const TONES = {
  ok: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400",
  warn: "bg-amber-500/14 text-amber-700 dark:text-amber-400",
  bad: "bg-red-500/12 text-red-600 dark:text-red-400",
  info: "bg-indigo-500/12 text-indigo-600 dark:text-indigo-300",
  mute: "bg-slate-500/12 text-slate-600 dark:text-slate-300",
};

const STATUS_TONE = {
  done: "ok", published: "ok", success: "ok", active: "ok", "1080p": "ok",
  failed: "bad", failure: "bad", error: "bad",
  running: "info", in_progress: "info", queued: "info", pending: "warn",
  dry_run: "mute", skipped: "mute", draft: "mute", paused: "warn", "legacy-720p": "warn", cancelled: "mute",
};
const STATUS_LABEL = { done: "published", dry_run: "dry run", "legacy-720p": "720p", in_progress: "running" };

export function Badge({ tone = "mute", children }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  const s = status || "unknown";
  return <Badge tone={STATUS_TONE[s] || "mute"}>{STATUS_LABEL[s] || s.replace(/_/g, " ")}</Badge>;
}

export function Avatar({ k, size = 36, name }) {
  return (
    <img
      src={`/logos/${k}.png`}
      alt={name || k}
      width={size}
      height={size}
      className="shrink-0 rounded-full object-cover"
      style={{ width: size, height: size, background: "var(--line)" }}
      onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
    />
  );
}

export function Stat({ label, value, sub, tone }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className={`mt-1.5 text-[1.7rem] font-semibold tracking-tight ${tone === "bad" ? "text-red-500" : tone === "ok" ? "text-emerald-500" : "grad-text"}`}>
        {value}
      </div>
      {sub ? <div className="muted mt-0.5 text-xs">{sub}</div> : null}
    </div>
  );
}

export function Section({ title, action, children, className = "" }) {
  return (
    <section className={className}>
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Bar({ value, max, tone = "accent" }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const color = tone === "ok" ? "linear-gradient(90deg, #10b981, #34d399)" : "linear-gradient(90deg, var(--accent), var(--accent-2))";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--line)", boxShadow: "inset 0 1px 2px rgba(0,0,0,.2)" }}>
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color, boxShadow: pct > 0 ? "0 0 10px -1px var(--accent)" : "none" }} />
    </div>
  );
}

export function Loading({ what = "" }) {
  return <div className="muted py-16 text-center text-sm">Loading {what}…</div>;
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="card flex items-center justify-between gap-4 p-4 text-sm" style={{ borderColor: "var(--bad)" }}>
      <span>
        <b className="text-red-500">Couldn't load.</b> <span className="muted">{String(error)}</span>
      </span>
      {onRetry ? <button className="btn" onClick={onRetry}>Retry</button> : null}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="muted card p-8 text-center text-sm">{children}</div>;
}

export function ChannelLink({ k, name, size = 24 }) {
  return (
    <Link to={`/channels/${k}`} className="inline-flex items-center gap-2 font-medium hover:underline">
      <Avatar k={k} size={size} name={name} />
      <span>{name}</span>
    </Link>
  );
}

export function PageHead({ title, sub, children }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {sub ? <p className="muted mt-0.5 text-sm">{sub}</p> : null}
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

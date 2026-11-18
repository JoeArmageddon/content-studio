import { useState } from "react";
import { errMsg, getActions, getSystem, syncStats } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { ago, dur, istDateTime, until } from "../lib/format";
import { Badge, ErrorBox, Loading, PageHead, Section, StatusBadge } from "../components/ui";

export default function SystemPage() {
  const { data: s, error, reload } = useLoad(getSystem, [], 60000);
  const { data: actions, reload: reloadActions } = useLoad(getActions, [], 30000);
  const [msg, setMsg] = useState(null);

  async function sync() {
    try { await syncStats(); setMsg({ ok: true, t: "Stats sync started — numbers refresh in ~1 min." }); reloadActions(); }
    catch (e) { setMsg({ ok: false, t: errMsg(e) }); }
  }

  if (error && !s) return <ErrorBox error={error} onRetry={reload} />;
  if (!s) return <Loading what="system" />;
  const gh = s.github;

  return (
    <div className="space-y-7">
      <PageHead title="System" sub="Health of everything the pipeline depends on.">
        <button className="btn" onClick={sync}>Sync YouTube stats now</button>
      </PageHead>
      {msg ? <div className={`card p-3 text-sm ${msg.ok ? "text-emerald-500" : "text-red-500"}`}>{msg.t}</div> : null}

      <div className="grid gap-3 md:grid-cols-3">
        <div className="card p-4"><div className="label">Database</div><div className="mt-1.5 flex items-center gap-2 font-semibold">Supabase Postgres <Badge tone="ok">connected</Badge></div>
          <div className="muted mt-1 text-xs">{Object.entries(s.database.rows).map(([k, v]) => `${v} ${k}`).join(" · ")}</div></div>
        <div className="card p-4"><div className="label">GitHub Actions</div>
          <div className="mt-1.5 flex items-center gap-2 font-semibold">{gh.repo || "not configured"} {gh.configured ? <Badge tone={gh.ok ? "ok" : "bad"}>{gh.ok ? "connected" : "error"}</Badge> : <Badge tone="warn">no token</Badge>}</div>
          <div className="muted mt-1 text-xs">{gh.configured ? "Run now / Dry run / history work." : "Add GITHUB_TOKEN + GITHUB_REPO on Vercel to enable them."}</div></div>
        <div className="card p-4"><div className="label">YouTube stats</div>
          <div className="mt-1.5 font-semibold">{s.stats_updated_at ? `Synced ${ago(s.stats_updated_at)}` : "Not synced yet"}</div>
          <div className="muted mt-1 text-xs">Auto: {s.schedule.stats}</div></div>
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <Section title="Upcoming pipeline runs" className="lg:col-span-2">
          <div className="card divide-y hairline text-sm">
            {s.schedule.next_runs.map((r) => (
              <div key={r} className="flex justify-between p-3"><span>{istDateTime(r)} IST</span><span className="muted">{until(r)}</span></div>
            ))}
            <div className="muted p-3 text-xs">Cron fires at {s.schedule.pipeline_hours_utc.map((h) => `${String(h).padStart(2, "0")}:00`).join(", ")} UTC. GitHub can delay a run by 5–20 min; each channel stops at its daily cap.</div>
          </div>
        </Section>

        <Section title="Workflow history" className="lg:col-span-3">
          {!actions?.configured ? <div className="card muted p-6 text-center text-sm">Connect GitHub (token on Vercel) to see run history here.</div> : (
            <div className="card divide-y hairline">
              {actions.error ? <div className="p-3 text-sm text-red-500">{actions.error}</div> : null}
              {actions.runs.slice(0, 12).map((r) => (
                <a key={r.id} href={r.url} target="_blank" rel="noreferrer" className="flex items-center gap-3 p-3 text-sm hover:bg-black/[.03] dark:hover:bg-white/[.03]">
                  <div className="min-w-0 flex-1"><div className="truncate font-medium">{r.workflow}</div>
                    <div className="muted text-xs">{r.event} · {istDateTime(r.created_at)}{r.duration_seconds ? ` · ${dur(r.duration_seconds)}` : ""}</div></div>
                  <StatusBadge status={r.status === "completed" ? r.conclusion : r.status} />
                </a>
              ))}
            </div>
          )}
        </Section>
      </div>

      <Section title="What runs where">
        <div className="card grid divide-y hairline sm:grid-cols-2 sm:divide-y-0">
          {s.services.map((x) => (
            <div key={x.name} className="p-3.5 text-sm"><div className="font-medium">{x.name}</div><div className="muted text-xs">{x.role}</div></div>
          ))}
        </div>
      </Section>
    </div>
  );
}

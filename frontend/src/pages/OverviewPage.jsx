import { useState } from "react";
import { Link } from "react-router-dom";
import { getOverview } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { ago, dur, istDateTime, istTime, num, until } from "../lib/format";
import { Avatar, Badge, Bar, ChannelLink, ErrorBox, Loading, PageHead, Section, Stat, StatusBadge } from "../components/ui";
import { ActivityChart } from "../components/charts";

function SlotNote({ slot }) {
  const t = istTime(slot.slot);
  const late = dur(slot.delay_seconds);
  const map = {
    on_time: { tone: "ok", text: `${t} run started on time` },
    late: { tone: "warn", text: `${t} run started ${late} late (GitHub delay)` },
    due: { tone: "info", text: `${t} run is due, starting any moment` },
    waiting: { tone: "warn", text: `${t} slot passed ${late} ago, waiting for GitHub to start it` },
    busy: { tone: "info", text: `${t} slot passed, an earlier delayed run is still going` },
  }[slot.state];
  return (
    <div className="hairline flex items-start gap-2 border-t pt-3">
      <Badge tone={map.tone}>{slot.state === "late" ? "Late" : slot.state === "waiting" ? "Waiting" : slot.state === "on_time" ? "On time" : "Due"}</Badge>
      <span className="text-xs">{map.text}</span>
    </div>
  );
}

const DISMISS_KEY = "cs-dismissed-alerts";
// An alert is identified by its content, so it comes back on its own if the problem changes.
const alertId = (a) => `${a.level}|${a.channel_key || ""}|${a.title}|${a.detail}`;
function loadDismissed() {
  try { return new Set(JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]")); } catch { return new Set(); }
}
function saveDismissed(set) {
  try { localStorage.setItem(DISMISS_KEY, JSON.stringify([...set].slice(-200))); } catch { /* storage unavailable */ }
}

const ALERT_TONE = { error: "bad", warn: "warn", info: "info" };

export default function OverviewPage() {
  const { data: o, error, loading, updated, reload } = useLoad(getOverview, [], 30000);
  const [dismissed, setDismissed] = useState(loadDismissed);
  const [showDismissed, setShowDismissed] = useState(false);
  const dismiss = (ids) => setDismissed((prev) => { const n = new Set(prev); ids.forEach((i) => n.add(i)); saveDismissed(n); return n; });
  const restore = () => { saveDismissed(new Set()); setDismissed(new Set()); setShowDismissed(false); };
  if (error && !o) return <ErrorBox error={error} onRetry={reload} />;
  if (!o) return <Loading what="overview" />;

  const t = o.totals, h = o.health;
  const open = o.alerts.filter((a) => !dismissed.has(alertId(a)));
  const hidden = o.alerts.length - open.length;
  const shown = showDismissed ? o.alerts : open;
  const rate = h.success_rate_7d;

  return (
    <div className="space-y-7">
      <PageHead title="Overview" sub={`Updated ${istTime(updated)} IST · refreshes every 30s`}>
        <button className="btn" onClick={reload} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
      </PageHead>

      {o.alerts.length && (open.length || showDismissed) ? (
        <Section
          title={`Needs attention (${open.length})`}
          action={
            <span className="flex items-center gap-3 text-xs">
              {open.length > 1 ? <button className="muted hover:underline" onClick={() => dismiss(open.map(alertId))}>Dismiss all</button> : null}
              {hidden ? <button className="muted hover:underline" onClick={() => setShowDismissed((v) => !v)}>{showDismissed ? "Hide dismissed" : `Show dismissed (${hidden})`}</button> : null}
            </span>
          }
        >
          <div className="card divide-y hairline">
            {shown.map((a) => {
              const gone = dismissed.has(alertId(a));
              return (
                <div key={alertId(a)} className={`flex items-start gap-3 p-3.5 text-sm ${gone ? "opacity-50" : ""}`}>
                  <Badge tone={ALERT_TONE[a.level]}>{a.level === "error" ? "Problem" : a.level === "warn" ? "Warning" : "Info"}</Badge>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{a.title}</div>
                    <div className="muted mt-0.5 break-words text-xs">{a.detail}</div>
                  </div>
                  {a.channel_key ? <Link to={`/channels/${a.channel_key}`} className="btn shrink-0">Open</Link> : null}
                  {gone ? null : <button className="btn shrink-0" onClick={() => dismiss([alertId(a)])} aria-label={`Dismiss: ${a.title}`}>Dismiss</button>}
                </div>
              );
            })}
          </div>
        </Section>
      ) : o.alerts.length ? (
        <div className="muted flex items-center justify-between rounded-xl px-1 text-xs">
          <span>{hidden} alert{hidden === 1 ? "" : "s"} dismissed</span>
          <span className="flex gap-3">
            <button className="hover:underline" onClick={() => setShowDismissed(true)}>Show</button>
            <button className="hover:underline" onClick={restore}>Restore all</button>
          </span>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Published today" value={`${o.today.published}/${o.today.capacity}`} sub="of today's capacity" />
        <Stat label="Total published" value={num(t.published)} sub="videos on YouTube" />
        <Stat label="Total views" value={num(t.views)} sub={`${num(t.likes)} likes`} />
        <Stat label="Subscribers" value={num(t.subscribers)} sub="across all channels" />
        <Stat
          label="Pipeline success"
          value={rate === null ? "–" : `${rate}%`}
          sub={`${h.done_7d} ok · ${h.failed_7d} failed · since go-live`}
          tone={rate === null ? undefined : rate >= 80 ? "ok" : rate < 50 ? "bad" : undefined}
        />
        <Stat label="Channels live" value={`${t.active}/${t.channels}`} sub={`${t.hd_footage} with HD footage`} />
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <Section title="Activity" className="min-w-0 lg:col-span-3">
          <div className="card p-4"><ActivityChart /></div>
        </Section>

        <Section title="Schedule" className="min-w-0 lg:col-span-2">
          <div className="card space-y-3 p-4 text-sm">
            <div>
              <div className="label mb-1.5">Next pipeline runs (IST)</div>
              <div className="flex flex-wrap gap-2">
                {h.next_runs.slice(0, 3).map((r, i) => (
                  <div key={r} className={`rounded-xl border border-[var(--edge)] px-3 py-1.5 ${i === 0 ? "ring-1 glass" : ""}`} data-first={i === 0} style={i === 0 ? { "--tw-ring-color": "var(--accent)" } : undefined}>
                    <div className="font-semibold">{istTime(r)}</div>
                    <div className="muted text-[11px]">{until(r)}</div>
                  </div>
                ))}
              </div>
            </div>
            {h.slot ? <SlotNote slot={h.slot} /> : null}
            <div className="hairline border-t pt-3">
              <div className="label mb-1">Last run</div>
              {h.last_run ? (
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate">{h.last_run.channel_name} · {ago(h.last_run.started_at)}</span>
                  <StatusBadge status={h.last_run.status} />
                </div>
              ) : <span className="muted">No runs yet</span>}
            </div>
            <div className="hairline border-t pt-3">
              <div className="label mb-1">YouTube stats</div>
              <span className="muted">{h.stats_updated_at ? `Synced ${ago(h.stats_updated_at)}` : "Not synced yet"}</span>
            </div>
          </div>
        </Section>
      </div>

      <Section title="Today by channel" action={<Link to="/channels" className="muted text-xs hover:underline">All channels →</Link>}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {o.today.channels.map((c) => (
            <Link key={c.key} to={`/channels/${c.key}`} className={`card lift block p-3 ${c.active ? "" : "opacity-60"}`}>
              <div className="mb-2.5 flex items-center gap-2.5">
                <Avatar k={c.key} size={30} name={c.name} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{c.name}</div>
                  <div className="muted text-[11px]">{c.active ? `${c.published}/${c.cap} today` : "paused"}</div>
                </div>
              </div>
              <Bar value={c.published} max={c.cap} tone={c.published >= c.cap ? "ok" : "accent"} />
            </Link>
          ))}
        </div>
      </Section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Recent runs" action={<Link to="/runs" className="muted text-xs hover:underline">All runs →</Link>}>
          <div className="card divide-y hairline">
            {o.recent_runs.length === 0 ? <div className="muted p-6 text-center text-sm">No runs yet</div> : null}
            {o.recent_runs.map((r) => (
              <div key={r.id} className="flex items-center gap-3 p-3 text-sm">
                <Avatar k={r.channel_key} size={26} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{r.video_title || r.channel_name}</div>
                  <div className="muted flex items-center gap-2 text-xs">
                    <span>{istDateTime(r.started_at)}</span><span>·</span><span>{dur(r.duration_seconds)}</span>
                  </div>
                </div>
                <StatusBadge status={r.status} />
              </div>
            ))}
          </div>
        </Section>

        <Section title="Top videos" action={<Link to="/videos" className="muted text-xs hover:underline">All videos →</Link>}>
          <div className="card divide-y hairline">
            {o.top_videos.length === 0 ? <div className="muted p-6 text-center text-sm">No published videos yet</div> : null}
            {o.top_videos.map((v) => (
              <div key={v.id} className="flex items-center gap-3 p-3 text-sm">
                {v.thumbnail ? <img src={v.thumbnail} alt="" className="h-12 w-8 shrink-0 rounded object-cover" style={{ background: "var(--line)" }} /> : null}
                <div className="min-w-0 flex-1">
                  <a href={v.youtube_url || undefined} target="_blank" rel="noreferrer" className="line-clamp-1 font-medium hover:underline">{v.title}</a>
                  <div className="muted mt-0.5 text-xs"><ChannelLink k={v.channel_key} name={v.channel_name} size={16} /></div>
                </div>
                <div className="text-right text-xs"><div className="font-semibold">{num(v.views)}</div><div className="muted">views</div></div>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}

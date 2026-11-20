import { getLearning } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { ago, istDateTime, num } from "../lib/format";
import { Avatar, Badge, ErrorBox, Loading, PageHead, Section, Stat } from "../components/ui";

const BASIS = { youtube_analytics: "YouTube Analytics", db_stats: "synced view counts", none: "no data yet" };

export default function LearningPage() {
  const { data, error, reload } = useLoad(getLearning);
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading what="learning loop" />;

  const t = data.totals;
  return (
    <div className="space-y-6">
      <PageHead title="Learning loop" sub="What the pipeline has learned about each niche, and whether it is actually being fed into new videos." />

      {data.stale ? (
        <div className="card p-3 text-sm" style={{ borderColor: "var(--warn, #f59e0b)" }}>
          <b>Insights look stale.</b> <span className="muted">Nothing has been refreshed in over 36 hours. The daily Insights workflow may be delayed or failing.</span>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Last refresh" value={ago(data.last_refresh)} sub={data.last_refresh ? istDateTime(data.last_refresh) : "never"} tone={data.stale ? "bad" : undefined} />
        <Stat label="Competitor data fresh" value={`${t.competitor_fresh}/${t.channels}`} sub="channels with a scan in the last 7 days" tone={t.competitor_fresh === t.channels ? "ok" : undefined} />
        <Stat label="Own-video data" value={`${t.own_with_data}/${t.channels}`} sub="channels with real view data to learn from" tone={t.own_with_data ? undefined : "bad"} />
        <Stat label="Schedule" value="Daily" sub={data.schedule} />
      </div>

      <Section title="Where it is used">
        <div className="card divide-y p-0" style={{ borderColor: "var(--line)" }}>
          {data.feeds.map((f) => (
            <div key={f.agent} className="flex gap-3 p-3 text-sm">
              <b className="w-24 shrink-0">{f.agent}</b>
              <span className="muted">{f.uses}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="By channel">
        <div className="grid gap-3 lg:grid-cols-2">
          {data.channels.map((c) => (
            <div key={c.key} className="card space-y-3 p-4">
              <div className="flex items-center gap-3">
                <Avatar k={c.key} size={32} name={c.name} />
                <div className="min-w-0 flex-1 text-sm font-semibold">{c.name}</div>
                <Badge tone={c.competitor.fresh ? "ok" : "warn"}>competitors {c.competitor.fresh ? "fresh" : "stale"}</Badge>
                <Badge tone={c.own.sample_size ? "ok" : "mute"}>own {c.own.sample_size ? `${c.own.sample_size} videos` : "no data"}</Badge>
              </div>

              <div>
                <div className="label">Competitor titles being used ({c.competitor.scans} scans · {ago(c.competitor.last_at)})</div>
                {c.competitor.top_titles.length ? (
                  <ul className="mt-1 space-y-0.5 text-xs">
                    {c.competitor.top_titles.slice(0, 5).map((x) => <li key={x} className="muted truncate">• {x}</li>)}
                  </ul>
                ) : <div className="muted mt-1 text-xs">None in the last 7 days.</div>}
                {c.competitor.top_hashtags.length ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {c.competitor.top_hashtags.slice(0, 8).map((h) => <span key={h} className="mono muted rounded-full px-2 py-0.5 text-[11px]" style={{ background: "var(--line)" }}>{h}</span>)}
                  </div>
                ) : null}
              </div>

              <div>
                <div className="label">Own best videos · basis: {BASIS[c.own.basis] || c.own.basis}</div>
                {c.own.top_titles.length ? (
                  <ul className="mt-1 space-y-0.5 text-xs">{c.own.top_titles.slice(0, 3).map((x) => <li key={x} className="muted truncate">• {x}</li>)}</ul>
                ) : <div className="muted mt-1 text-xs">Not enough views yet to rank our own videos.</div>}
              </div>

              <div className="hairline flex items-center justify-between border-t pt-2 text-xs">
                <span className="muted">{c.performance.videos} videos · {num(c.performance.views)} views · avg {c.performance.avg_views}</span>
                {c.performance.top_video ? (
                  <a className="truncate pl-3 hover:underline" href={`https://youtube.com/shorts/${c.performance.top_video.id}`} target="_blank" rel="noreferrer">
                    best: {num(c.performance.top_video.views)} ↗
                  </a>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

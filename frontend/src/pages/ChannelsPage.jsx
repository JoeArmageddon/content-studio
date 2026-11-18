import { Link } from "react-router-dom";
import { getChannels } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { ago, num } from "../lib/format";
import { Avatar, Badge, Bar, ErrorBox, Loading, PageHead, StatusBadge } from "../components/ui";
import ChannelControls from "../components/ChannelControls";

export default function ChannelsPage() {
  const { data: channels, error, reload } = useLoad(getChannels, [], 60000);
  if (error && !channels) return <ErrorBox error={error} onRetry={reload} />;
  if (!channels) return <Loading what="channels" />;

  return (
    <div>
      <PageHead title="Channels" sub={`${channels.filter((c) => c.active).length} live · ${channels.filter((c) => !c.active).length} paused`} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {channels.map((c) => (
          <div key={c.key} className={`card flex flex-col p-4 ${c.active ? "" : "opacity-80"}`}>
            <div className="flex items-start gap-3">
              <Avatar k={c.key} size={46} name={c.name} />
              <div className="min-w-0 flex-1">
                <Link to={`/channels/${c.key}`} className="block truncate text-[15px] font-semibold hover:underline">{c.yt_title || c.name}</Link>
                <div className="muted truncate text-xs">{c.niche}</div>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  <StatusBadge status={c.active ? "active" : "paused"} />
                  {!c.authorized ? <Badge tone="bad">not authorized</Badge> : null}
                  <Badge tone={c.footage_quality === "1080p" ? "ok" : "warn"}>{c.footage_clips} clips · {c.footage_quality === "1080p" ? "HD" : "720p"}</Badge>
                </div>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              {[["Subs", num(c.subscribers)], ["Views", num(c.views)], ["Videos", c.published_total], ["Likes", num(c.likes)]].map(([l, v]) => (
                <div key={l}><div className="text-base font-semibold">{v}</div><div className="muted text-[11px]">{l}</div></div>
              ))}
            </div>

            <div className="mt-4">
              <div className="mb-1 flex justify-between text-xs"><span className="muted">Today</span><span>{c.published_today}/{c.daily_cap}</span></div>
              <Bar value={c.published_today} max={c.daily_cap} tone={c.published_today >= c.daily_cap ? "ok" : "accent"} />
            </div>

            <div className="muted mt-3 text-xs">
              Last post {ago(c.last_published_at)} · last run{" "}
              {c.last_run_status ? <b className={c.last_run_status === "failed" ? "text-red-500" : ""}>{c.last_run_status.replace("_", " ")}</b> : "–"}
            </div>

            <div className="hairline mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
              <ChannelControls channel={c} onChange={reload} compact />
              <div className="flex gap-2">
                {c.youtube_url ? <a className="btn" href={c.youtube_url} target="_blank" rel="noreferrer">YouTube ↗</a> : null}
                <Link className="btn" to={`/channels/${c.key}`}>Details</Link>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

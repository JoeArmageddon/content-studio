import { Link, useParams } from "react-router-dom";
import { getChannel, getRuns, getStories, getVideos } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { ago, dur, istDateTime, num } from "../lib/format";
import { Avatar, Badge, Bar, Empty, ErrorBox, Loading, Section, Stat, StatusBadge } from "../components/ui";
import ChannelControls from "../components/ChannelControls";
import RunControls from "../components/RunControls";
import { VideoCard } from "./VideosPage";
import { StageDots } from "./RunsPage";

export default function ChannelDetailPage() {
  const { key } = useParams();
  const { data: c, error, reload } = useLoad(() => getChannel(key), [key], 60000);
  const { data: videos } = useLoad(() => getVideos({ channel_key: key, limit: 12 }), [key]);
  const { data: runs, reload: reloadRuns } = useLoad(() => getRuns({ channel_key: key, limit: 10 }), [key], 20000);
  const { data: stories } = useLoad(() => getStories({ channel_key: key, limit: 8 }), [key]);

  if (error && !c) return <ErrorBox error={error} onRetry={reload} />;
  if (!c) return <Loading what="channel" />;

  return (
    <div className="space-y-7">
      <div><Link to="/channels" className="muted text-xs hover:underline">← Channels</Link></div>

      <div className="card flex flex-wrap items-center gap-4 p-5">
        <Avatar k={c.key} size={64} name={c.name} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{c.yt_title || c.name}</h1>
            <StatusBadge status={c.active ? "active" : "paused"} />
            {!c.authorized ? <Badge tone="bad">not authorized</Badge> : <Badge tone="ok">YouTube linked</Badge>}
          </div>
          <div className="muted mt-0.5 text-sm">{c.niche}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {c.youtube_url ? <a className="btn" href={c.youtube_url} target="_blank" rel="noreferrer">Open on YouTube ↗</a> : null}
            {c.subreddits.slice(0, 4).map((s) => <a key={s} className="btn" href={`https://www.reddit.com/r/${s}`} target="_blank" rel="noreferrer">r/{s} ↗</a>)}
          </div>
        </div>
        <div className="flex flex-col items-end gap-3">
          <ChannelControls channel={c} onChange={reload} />
          <RunControls channelKey={c.key} name={c.name} active={c.active} onDone={reloadRuns} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Subscribers" value={num(c.subscribers)} />
        <Stat label="Views" value={num(c.views)} sub={`${num(c.total_views)} on channel`} />
        <Stat label="Likes" value={num(c.likes)} />
        <Stat label="Published" value={c.published_total} sub={`last ${ago(c.last_published_at)}`} />
        <Stat label="Today" value={`${c.published_today}/${c.daily_cap}`} />
        <Stat label="Runs since go-live" value={`${c.runs_7d_done} ok`} sub={`${c.runs_7d_failed} failed`} tone={c.runs_7d_failed > c.runs_7d_done ? "bad" : undefined} />
      </div>

      <Section title="Recent runs">
        {!runs ? <Loading /> : runs.length === 0 ? <Empty>No runs yet.</Empty> : (
          <div className="card overflow-x-auto"><table className="w-full min-w-[560px]">
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="hairline border-b last:border-0">
                  <td className="td mono muted">#{r.id}</td>
                  <td className="td">{istDateTime(r.started_at)}</td>
                  <td className="td">{dur(r.duration_seconds)}</td>
                  <td className="td"><StageDots log={r.stage_log} status={r.status} /></td>
                  <td className="td max-w-[260px] truncate" title={r.error || r.video_title}>{r.error ? <span className="text-red-500">{r.error.slice(0, 80)}</span> : r.video_title}</td>
                  <td className="td"><StatusBadge status={r.status} /></td>
                </tr>
              ))}
            </tbody></table></div>
        )}
      </Section>

      <Section title="Latest videos" action={<Link to={`/videos`} className="muted text-xs hover:underline">All videos →</Link>}>
        {!videos ? <Loading /> : videos.length === 0 ? <Empty>No videos yet.</Empty> : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            {videos.slice(0, 6).map((v) => <VideoCard key={v.id} v={v} showChannel={false} />)}
          </div>
        )}
      </Section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Story pool">
          <div className="card divide-y hairline">
            {!stories ? <Loading /> : stories.length === 0 ? <div className="muted p-6 text-center text-sm">No stories sourced yet.</div> : stories.map((s) => (
              <div key={s.id} className="p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  {s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="line-clamp-2 font-medium hover:underline">{s.title}</a> : <span className="font-medium">{s.title}</span>}
                  <Badge tone={s.used ? "ok" : "mute"}>{s.used ? "used" : "unused"}</Badge>
                </div>
                <div className="muted mt-0.5 text-xs">{s.score} pts · {ago(s.created_at)}</div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Configuration">
          <div className="card space-y-3 p-4 text-sm">
            <Row label="Voice">{(c.voices || []).join(", ") || "–"}</Row>
            <Row label="Subreddits">{(c.subreddits || []).map((s) => `r/${s}`).join(", ")}</Row>
            <Row label="Footage">{c.footage_clips} clips · {c.footage_quality === "1080p" ? "1080p" : c.footage_quality === "legacy-720p" ? "720p (needs rebuild)" : "none"}</Row>
            <Row label="Footage searches">{(c.background_queries || []).join(" · ")}</Row>
            <Row label="Card persona">{c.persona?.handle || "–"}</Row>
            <div className="muted hairline border-t pt-3 text-xs">Subreddits, voice and footage queries live in <span className="mono">channels.yaml</span>; pause/resume and the daily cap are controlled here.</div>
            <div className="w-full"><div className="label mb-1">Daily cap used</div><Bar value={c.published_today} max={c.daily_cap} /></div>
          </div>
        </Section>
      </div>
    </div>
  );
}

function Row({ label, children }) {
  return <div className="flex gap-3"><div className="label w-28 shrink-0 pt-0.5">{label}</div><div className="min-w-0 break-words">{children}</div></div>;
}

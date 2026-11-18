import { useState } from "react";
import { getChannels, getVideos } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { ago, istDateTime, num } from "../lib/format";
import { ChannelLink, Empty, ErrorBox, Loading, PageHead, StatusBadge } from "../components/ui";

export function VideoCard({ v, showChannel = true }) {
  const live = !!v.youtube_video_id;
  return (
    <div className="card flex flex-col overflow-hidden">
      <div className="relative aspect-[9/12] w-full overflow-hidden" style={{ background: "var(--line)" }}>
        {v.thumbnail ? (
          <a href={v.youtube_url} target="_blank" rel="noreferrer">
            <img src={v.thumbnail} alt="" loading="lazy" className="h-full w-full object-cover" />
          </a>
        ) : (
          <div className="muted flex h-full items-center justify-center px-6 text-center text-xs">Not uploaded<br />(dry run or failed before upload)</div>
        )}
        <div className="absolute left-2 top-2"><StatusBadge status={v.status} /></div>
      </div>
      <div className="flex flex-1 flex-col p-3">
        <div className="line-clamp-2 text-sm font-medium leading-snug">{v.title || "Untitled"}</div>
        {showChannel && v.channel_key ? <div className="mt-1.5 text-xs"><ChannelLink k={v.channel_key} name={v.channel_name} size={18} /></div> : null}
        {live ? (
          <div className="muted mt-2 flex gap-3 text-xs">
            <span><b className="text-[var(--text)]">{num(v.views)}</b> views</span>
            <span><b className="text-[var(--text)]">{num(v.likes)}</b> likes</span>
            <span><b className="text-[var(--text)]">{num(v.comments)}</b> comments</span>
          </div>
        ) : null}
        <div className="muted mt-auto pt-2.5 text-[11px]" title={istDateTime(v.published_at || v.created_at)}>
          {live ? `Published ${ago(v.published_at)}` : `Created ${ago(v.created_at)}`}{v.voice_used ? ` · ${v.voice_used}` : ""}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {v.youtube_url ? <a className="btn !px-2 !py-1 !text-xs" href={v.youtube_url} target="_blank" rel="noreferrer">YouTube ↗</a> : null}
          {v.story_url ? <a className="btn !px-2 !py-1 !text-xs" href={v.story_url} target="_blank" rel="noreferrer">{v.subreddit ? `r/${v.subreddit}` : "Reddit"} ↗</a> : null}
        </div>
      </div>
    </div>
  );
}

export default function VideosPage() {
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("published");
  const [q, setQ] = useState("");
  const { data: channels } = useLoad(getChannels);
  const { data: videos, error, reload } = useLoad(
    () => getVideos({ channel_key: channel || undefined, status: status || undefined, q: q || undefined, limit: 120 }),
    [channel, status, q],
  );

  return (
    <div>
      <PageHead title="Videos" sub="Everything the pipeline has produced. Views/likes sync from YouTube every 3 hours.">
        <input className="input w-44" placeholder="Search titles…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">All channels</option>
          {(channels || []).map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
        </select>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="published">Published</option><option value="draft">Drafts (not uploaded)</option><option value="">All</option>
        </select>
      </PageHead>
      {error && !videos ? <ErrorBox error={error} onRetry={reload} /> : !videos ? <Loading what="videos" /> : videos.length === 0 ? <Empty>No videos match.</Empty> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {videos.map((v) => <VideoCard key={v.id} v={v} />)}
        </div>
      )}
    </div>
  );
}

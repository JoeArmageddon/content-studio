import { useState } from "react";
import { getLibrary } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { ago } from "../lib/format";
import { Avatar, Badge, ErrorBox, Loading, PageHead } from "../components/ui";

export default function LibraryPage() {
  const { data: libs, error, reload } = useLoad(getLibrary);
  const [open, setOpen] = useState(null);
  if (error && !libs) return <ErrorBox error={error} onRetry={reload} />;
  if (!libs) return <Loading what="footage library" />;

  const hd = libs.filter((l) => l.quality === "1080p").length;
  return (
    <div>
      <PageHead title="Footage library" sub={`${hd}/${libs.length} channels have the sharp 1080×1920 set. Clips are CC-BY YouTube videos; credit is added to each description automatically.`} />
      <div className="space-y-3">
        {libs.map((l) => (
          <div key={l.channel_key} className="card">
            <button className="flex w-full items-center gap-3 p-4 text-left" onClick={() => setOpen(open === l.channel_key ? null : l.channel_key)}>
              <Avatar k={l.channel_key} size={34} name={l.channel_name} />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{l.channel_name}</div>
                <div className="muted text-xs">{l.clip_count} clips · {l.size_mb ?? "–"} MB · updated {ago(l.updated_at)}</div>
              </div>
              <Badge tone={l.quality === "1080p" ? "ok" : "warn"}>{l.quality === "1080p" ? "1080p" : l.quality === "legacy-720p" ? "720p · needs rebuild" : "empty"}</Badge>
              <span className="muted text-xs">{open === l.channel_key ? "▲" : "▼"}</span>
            </button>
            {open === l.channel_key ? (
              <div className="hairline overflow-x-auto border-t">
                <table className="w-full min-w-[560px]">
                  <thead><tr><th className="th">Clip</th><th className="th">Uploader (credit)</th><th className="th">Source res.</th><th className="th">Search</th></tr></thead>
                  <tbody>
                    {l.clips.map((c, i) => (
                      <tr key={i} className="hairline border-t">
                        <td className="td"><a className="hover:underline" href={c.url} target="_blank" rel="noreferrer">{(c.title || "").slice(0, 70)} ↗</a></td>
                        <td className="td muted">{c.uploader}</td>
                        <td className="td mono muted">{c.resolution || "720p"}</td>
                        <td className="td muted">{c.query}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

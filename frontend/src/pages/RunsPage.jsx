import { Fragment, useState } from "react";
import { getChannels, getRuns } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { dur, istDateTime, STAGES } from "../lib/format";
import { ChannelLink, Empty, ErrorBox, Loading, PageHead, StatusBadge } from "../components/ui";

// 12 dots, one per pipeline stage: filled = reached, red = where a failed run stopped.
export function StageDots({ log, status }) {
  const reached = new Set((log || []).map((s) => String(s).split("_skipped")[0]));
  const lastIdx = STAGES.reduce((m, s, i) => (reached.has(s) ? i : m), -1);
  // A failed run stopped at the next stage — or, if it reached "publish", at publish itself.
  const stoppedIdx = status !== "failed" ? -1 : reached.has("publish") ? STAGES.length - 1 : lastIdx + 1;
  return (
    <div className="flex items-center gap-[3px]" title={(log || []).join(" → ") || "no stages recorded"}>
      {STAGES.map((s, i) => {
        const done = reached.has(s);
        const stopped = i === stoppedIdx;
        return (
          <i key={s} title={s} className="inline-block h-2 w-2 rounded-full"
            style={{ background: stopped ? "var(--bad)" : done ? "var(--ok)" : "var(--line)" }} />
        );
      })}
    </div>
  );
}

export default function RunsPage() {
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState(null);
  const { data: channels } = useLoad(getChannels);
  const { data: runs, error, loading, reload } = useLoad(
    () => getRuns({ channel_key: channel || undefined, status: status || undefined, limit: 100 }),
    [channel, status], 20000,
  );

  return (
    <div>
      <PageHead title="Runs" sub="Every pipeline run, with the stage it reached. Failed runs show where they stopped.">
        <select className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">All channels</option>
          {(channels || []).map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
        </select>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          <option value="done">Published</option><option value="failed">Failed</option>
          <option value="skipped">Skipped (cap)</option><option value="dry_run">Dry run</option><option value="running">Running</option>
        </select>
        <button className="btn" onClick={reload} disabled={loading}>Refresh</button>
      </PageHead>

      {error && !runs ? <ErrorBox error={error} onRetry={reload} /> : !runs ? <Loading what="runs" /> : runs.length === 0 ? <Empty>No runs match.</Empty> : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[720px]">
            <thead className="hairline border-b"><tr>
              <th className="th">Run</th><th className="th">Channel</th><th className="th">Started (IST)</th>
              <th className="th">Took</th><th className="th">Stages</th><th className="th">Status</th>
            </tr></thead>
            <tbody>
              {runs.map((r) => (
                <Fragment key={r.id}>
                  <tr className="hairline cursor-pointer border-b last:border-0 hover:bg-black/[.03] dark:hover:bg-white/[.03]" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <td className="td mono muted">#{r.id}</td>
                    <td className="td" onClick={(e) => e.stopPropagation()}><ChannelLink k={r.channel_key} name={r.channel_name} /></td>
                    <td className="td">{istDateTime(r.started_at)}</td>
                    <td className="td">{dur(r.duration_seconds)}</td>
                    <td className="td"><StageDots log={r.stage_log} status={r.status} /></td>
                    <td className="td"><StatusBadge status={r.status} /></td>
                  </tr>
                  {open === r.id ? (
                    <tr className="hairline border-b bg-black/[.02] dark:bg-white/[.02]">
                      <td colSpan={6} className="px-4 py-3 text-sm">
                        {r.video_title ? <div className="mb-2"><span className="label mr-2">Video</span>{r.video_title}</div> : null}
                        <div className="mb-2"><span className="label mr-2">Stages</span><span className="mono text-xs">{(r.stage_log || []).join(" → ") || "none recorded"}</span></div>
                        {r.error ? <pre className="mono max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-lg p-3 text-xs text-red-500" style={{ background: "var(--bg)" }}>{r.error}</pre> : <span className="muted text-xs">No error recorded.</span>}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { getChannel, getRuns, getVideos, getInsights, triggerRun } from "../lib/api";
import StatusBadge from "../components/StatusBadge";

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function ChannelDetailPage() {
  const { key } = useParams();
  const [channel, setChannel] = useState(null);
  const [runs, setRuns] = useState([]);
  const [videos, setVideos] = useState([]);
  const [insights, setInsights] = useState([]);
  const [error, setError] = useState(null);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState(null);

  const load = useCallback(() => {
    Promise.all([getChannel(key), getRuns(key), getVideos(key), getInsights(key)])
      .then(([c, r, v, i]) => {
        setChannel(c);
        setRuns(r);
        setVideos(v);
        setInsights(i);
      })
      .catch((e) => setError(e.message));
  }, [key]);

  useEffect(() => {
    load();
  }, [load]);

  const handleTrigger = async () => {
    setTriggering(true);
    setTriggerResult(null);
    try {
      const result = await triggerRun(key);
      setTriggerResult({ ok: true, ...result });
      load();
    } catch (e) {
      setTriggerResult({ ok: false, message: e.response?.data?.detail || e.message });
    } finally {
      setTriggering(false);
    }
  };

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
        Couldn't reach the backend API ({error}).
      </div>
    );
  }
  if (!channel) return <p className="text-slate-500">Loading…</p>;

  return (
    <div>
      <Link to="/" className="mb-4 inline-block text-sm text-indigo-600 hover:underline">
        ← All channels
      </Link>

      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {channel.persona?.avatar_emoji} {channel.name}
          </h1>
          <p className="text-slate-500">{channel.niche}</p>
          <p className="mt-1 text-sm text-slate-400">
            r/{(channel.subreddits || []).join(", r/")} · {channel.daily_cap}/day cap · persona{" "}
            {channel.persona?.handle}
          </p>
        </div>
        <div className="text-right">
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {triggering ? "Running…" : "Trigger run now"}
          </button>
          {triggerResult && (
            <p className={`mt-2 max-w-xs text-xs ${triggerResult.ok ? "text-slate-500" : "text-red-600"}`}>
              {triggerResult.ok
                ? `Run #${triggerResult.run_id}: ${triggerResult.status}`
                : triggerResult.message}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Recent runs
          </h2>
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            {runs.length === 0 ? (
              <p className="p-4 text-sm text-slate-400">No runs yet.</p>
            ) : (
              <table className="w-full text-left text-sm">
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} className="border-b border-slate-100 last:border-0">
                      <td className="px-3 py-2 text-slate-400">#{r.id}</td>
                      <td className="px-3 py-2">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="px-3 py-2 text-slate-500">{formatDate(r.started_at)}</td>
                      <td className="px-3 py-2 text-xs text-slate-400">
                        {(r.stage_log || []).slice(-1)[0]}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Videos</h2>
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            {videos.length === 0 ? (
              <p className="p-4 text-sm text-slate-400">No videos yet.</p>
            ) : (
              <table className="w-full text-left text-sm">
                <tbody>
                  {videos.map((v) => (
                    <tr key={v.id} className="border-b border-slate-100 last:border-0">
                      <td className="max-w-[220px] truncate px-3 py-2" title={v.title}>
                        {v.title || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <StatusBadge status={v.status} />
                      </td>
                      <td className="px-3 py-2 text-slate-500">{v.voice_used || "—"}</td>
                      <td className="px-3 py-2 text-slate-400">{formatDate(v.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            What's working (competitor + own-channel insights)
          </h2>
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            {insights.length === 0 ? (
              <p className="p-4 text-sm text-slate-400">
                No insights yet — Competitor-Scan runs on the daily schedule (or lazily when Metadata
                needs one), Feedback runs daily once the channel is YouTube-authorized.
              </p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {insights.map((i) => (
                  <li key={i.id} className="p-4">
                    <div className="mb-1 flex items-center gap-2">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                          i.source === "competitor_scan"
                            ? "bg-purple-100 text-purple-800"
                            : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {i.source === "competitor_scan" ? "competitor" : "own analytics"}
                      </span>
                      <span className="text-xs text-slate-400">{formatDate(i.created_at)}</span>
                    </div>
                    {(i.findings?.top_titles || []).length > 0 && (
                      <p className="text-sm text-slate-600">
                        Top titles: {i.findings.top_titles.join(" · ")}
                      </p>
                    )}
                    {(i.findings?.top_hashtags || []).length > 0 && (
                      <p className="text-sm text-slate-500">
                        Hashtags: {i.findings.top_hashtags.join(" ")}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

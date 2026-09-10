import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getChannels } from "../lib/api";

export default function ChannelsPage() {
  const [channels, setChannels] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getChannels()
      .then(setChannels)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
        Couldn't reach the backend API ({error}). Is it running? See the backend README's quick start.
      </div>
    );
  }

  if (!channels) {
    return <p className="text-slate-500">Loading channels…</p>;
  }

  return (
    <div>
      <h1 className="mb-1 text-2xl font-semibold text-slate-900">Channels</h1>
      <p className="mb-6 text-slate-500">{channels.length} Storique channels configured.</p>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 font-medium">Channel</th>
              <th className="px-4 py-3 font-medium">Niche</th>
              <th className="px-4 py-3 font-medium">Persona</th>
              <th className="px-4 py-3 font-medium">Daily cap</th>
              <th className="px-4 py-3 font-medium">Voices</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {channels.map((c) => (
              <tr key={c.key} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link to={`/channels/${c.key}`} className="font-medium text-indigo-600 hover:underline">
                    {c.name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-600">{c.niche}</td>
                <td className="px-4 py-3 text-slate-600">
                  {c.persona?.avatar_emoji} {c.persona?.handle}
                </td>
                <td className="px-4 py-3 text-slate-600">{c.daily_cap}/day</td>
                <td className="px-4 py-3 text-slate-600">{(c.voices || []).length}</td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      c.active ? "bg-green-100 text-green-800" : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {c.active ? "active" : "paused"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

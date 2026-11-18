import { useState } from "react";
import { errMsg, patchChannel } from "../lib/api";

// Pause/resume + daily cap stepper for one channel (persisted in the DB; the
// scheduler honours it on its next tick).
export default function ChannelControls({ channel, onChange, compact = false }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function save(body) {
    setBusy(true);
    setErr(null);
    try {
      await patchChannel(channel.key, body);
      await onChange?.();
    } catch (e) {
      setErr(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button className={`btn ${channel.active ? "" : "btn-primary"}`} disabled={busy} onClick={() => save({ active: !channel.active })}>
        {channel.active ? "Pause" : "Resume"}
      </button>
      {!compact ? (
        <div className="flex items-center gap-1" title="Max videos published per day">
          <button className="btn !px-2" disabled={busy || channel.daily_cap <= 1} onClick={() => save({ daily_cap: channel.daily_cap - 1 })} aria-label="Lower daily cap">−</button>
          <span className="w-16 text-center text-sm">{channel.daily_cap}/day</span>
          <button className="btn !px-2" disabled={busy || channel.daily_cap >= 10} onClick={() => save({ daily_cap: channel.daily_cap + 1 })} aria-label="Raise daily cap">+</button>
        </div>
      ) : null}
      {err ? <span className="text-xs text-red-500">{err}</span> : null}
    </div>
  );
}

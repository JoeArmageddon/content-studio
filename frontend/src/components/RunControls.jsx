import { useState } from "react";
import { errMsg, triggerRun } from "../lib/api";

// "Run now" / "Dry run" for one channel — dispatches the GitHub Actions workflow.
export default function RunControls({ channelKey, name, active = true, onDone }) {
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);

  async function go(dry) {
    const what = dry
      ? `Dry run for ${name}? It builds a video but does NOT upload it.`
      : `Run ${name} now? This generates and PUBLISHES a real video to its YouTube channel.`;
    if (!window.confirm(what)) return;
    setBusy(dry ? "dry" : "live");
    setMsg(null);
    try {
      await triggerRun(channelKey, dry);
      setMsg({ ok: true, text: "Started — it takes ~5–10 min. Watch the Runs page." });
      onDone?.();
    } catch (e) {
      setMsg({ ok: false, text: errMsg(e) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button className="btn" disabled={!!busy} onClick={() => go(true)}>{busy === "dry" ? "Starting…" : "Dry run"}</button>
      <button className="btn btn-primary" disabled={!!busy} onClick={() => go(false)} title={active ? "" : "Channel is paused — a manual run still publishes"}>
        {busy === "live" ? "Starting…" : "Run now"}
      </button>
      {msg ? <span className={`text-xs ${msg.ok ? "text-emerald-500" : "text-red-500"}`}>{msg.text}</span> : null}
    </div>
  );
}

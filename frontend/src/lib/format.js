// All times are shown in IST (the user's timezone).
const TZ = "Asia/Kolkata";

export function num(n) {
  if (n === null || n === undefined) return "–";
  const v = Number(n);
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (v >= 10_000) return `${Math.round(v / 1000)}K`;
  if (v >= 1000) return `${(v / 1000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(v);
}

const parse = (d) => (d instanceof Date ? d : new Date(d));

export function istTime(d) {
  if (!d) return "–";
  return parse(d).toLocaleTimeString("en-IN", { timeZone: TZ, hour: "numeric", minute: "2-digit", hour12: true });
}

export function istDateTime(d) {
  if (!d) return "–";
  return parse(d).toLocaleString("en-IN", {
    timeZone: TZ, day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true,
  });
}

export function istDay(d) {
  return parse(d).toLocaleDateString("en-IN", { timeZone: TZ, day: "numeric", month: "short" });
}

export function ago(d) {
  if (!d) return "never";
  const s = Math.round((Date.now() - parse(d).getTime()) / 1000);
  if (s < 0) return `in ${dur(-s)}`;
  if (s < 45) return "just now";
  return `${dur(s)} ago`;
}

export function dur(sec) {
  if (sec === null || sec === undefined) return "–";
  if (sec < 90) return `${Math.round(sec)}s`;
  if (sec < 5400) return `${Math.round(sec / 60)}m`;
  if (sec < 172800) return `${Math.round(sec / 3600)}h`;
  return `${Math.round(sec / 86400)}d`;
}

export function until(d) {
  const s = Math.round((parse(d).getTime() - Date.now()) / 1000);
  return s <= 0 ? "now" : `in ${dur(s)}`;
}

export const STAGES = [
  "source", "curate", "hook", "script", "script_qa", "voice",
  "background", "story_card", "assemble", "metadata", "compliance", "publish",
];

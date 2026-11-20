import { useEffect, useMemo, useRef, useState } from "react";
import { getActivity } from "../lib/api";
import { istDay, num } from "../lib/format";

// Ten distinguishable hues, one per channel (also used by the legend chips).
const PALETTE = ["#7c5cff", "#19b6ff", "#ff5fa8", "#10b981", "#f59e0b", "#14b8a6", "#e879f9", "#84cc16", "#fb7185", "#60a5fa"];
const RANGES = [7, 14, 30];

function niceMax(v) {
  if (v <= 4) return 4;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    if (!ref.current) return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const Chip = ({ on, onClick, children, color }) => (
  <button
    type="button"
    onClick={onClick}
    aria-pressed={on}
    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${on ? "border-[var(--edge)] glass" : "border-transparent opacity-45 hover:opacity-80"}`}
  >
    {color ? <i className="inline-block h-2 w-2 rounded-sm" style={{ background: color }} /> : null}
    {children}
  </button>
);

// Interactive daily activity chart: stacked by channel (or just totals), with failed runs
// on top, a metric toggle (videos / views), a range picker and a hover or touch tooltip.
export function ActivityChart() {
  const [days, setDays] = useState(14);
  const [metric, setMetric] = useState("videos"); // videos | views
  const [off, setOff] = useState(() => new Set()); // hidden channel keys
  const [showFailed, setShowFailed] = useState(true);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [hover, setHover] = useState(null);
  const [wrap, W] = useWidth();

  useEffect(() => {
    let live = true;
    getActivity(days).then((d) => { if (live) { setData(d); setErr(null); } }).catch((e) => live && setErr(e?.response?.data?.detail || e.message));
    return () => { live = false; };
  }, [days]);

  const chans = useMemo(() => data?.channels || [], [data]);
  const colorOf = useMemo(() => Object.fromEntries(chans.map((c, i) => [c.key, PALETTE[i % PALETTE.length]])), [chans]);
  const nameOf = useMemo(() => Object.fromEntries(chans.map((c) => [c.key, c.name])), [chans]);

  const rows = useMemo(() => {
    if (!data) return [];
    const visible = chans.filter((c) => !off.has(c.key));
    return data.series.map((d) => {
      const parts = visible
        .map((c) => ({ key: c.key, v: d.by_channel[c.key] || 0 }))
        .filter((p) => p.v > 0);
      const videos = parts.reduce((a, p) => a + p.v, 0);
      const failed = showFailed ? Object.entries(d.failed_by_channel).filter(([k]) => !off.has(k)).reduce((a, [, v]) => a + v, 0) : 0;
      // views are stored per day (all channels), so apportion them by the visible share of videos
      const share = d.published ? videos / d.published : 0;
      return { date: d.date, parts, videos, failed, views: Math.round(d.views * share) };
    });
  }, [data, chans, off, showFailed]);

  const H = 190, TOP = 12, BOT = 26, LEFT = 34;
  const innerH = H - TOP - BOT;
  const n = rows.length || 1;
  const metricVal = (r) => (metric === "views" ? r.views : r.videos + (showFailed ? r.failed : 0));
  const max = niceMax(Math.max(1, ...rows.map(metricVal)));
  const bw = (W - LEFT - 4) / n;
  const barW = Math.max(4, Math.min(34, bw * 0.66));
  const y = (v) => TOP + innerH - (v / max) * innerH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f * 100) / 100);
  const labelEvery = n <= 8 ? 1 : n <= 16 ? 2 : Math.ceil(n / 8);

  const total = rows.reduce((a, r) => a + (metric === "views" ? r.views : r.videos), 0);
  const failedTotal = rows.reduce((a, r) => a + r.failed, 0);
  const sel = hover !== null ? rows[hover] : null;

  const toggle = (k) => setOff((s) => { const t = new Set(s); if (t.has(k)) t.delete(k); else t.add(k); return t; });
  const soloOrAll = (k) => setOff((s) => (chans.length - s.size === 1 && !s.has(k) ? new Set() : new Set(chans.map((c) => c.key).filter((x) => x !== k))));

  const move = (e) => {
    const box = e.currentTarget.getBoundingClientRect();
    const i = Math.floor((e.clientX - box.left - LEFT) / bw);
    setHover(i >= 0 && i < rows.length ? i : null);
  };
  const onKey = (e) => {
    if (e.key === "ArrowRight") { e.preventDefault(); setHover((h) => (h === null ? 0 : Math.min(rows.length - 1, h + 1))); }
    if (e.key === "ArrowLeft") { e.preventDefault(); setHover((h) => (h === null ? rows.length - 1 : Math.max(0, h - 1))); }
    if (e.key === "Escape") setHover(null);
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1" role="group" aria-label="Metric">
          <Chip on={metric === "videos"} onClick={() => setMetric("videos")}>Videos</Chip>
          <Chip on={metric === "views"} onClick={() => setMetric("views")}>Views</Chip>
        </div>
        <div className="flex items-center gap-1" role="group" aria-label="Range">
          {RANGES.map((r) => <Chip key={r} on={days === r} onClick={() => setDays(r)}>{r}d</Chip>)}
        </div>
      </div>

      <div className="muted mb-1 flex flex-wrap items-baseline gap-x-4 text-xs">
        <span><b className="text-[var(--text)] text-base font-semibold">{num(total)}</b> {metric === "views" ? "views on videos published" : "videos published"} in {days} days</span>
        {failedTotal ? <span>{failedTotal} failed run{failedTotal === 1 ? "" : "s"}</span> : null}
        {metric === "views" ? <span>views are as of the last stats sync</span> : null}
      </div>

      <div ref={wrap} className="relative min-w-0 overflow-hidden">
        {err ? <div className="muted p-8 text-center text-sm">Couldn't load activity: {err}</div> : null}
        {!data && !err ? <div className="muted p-8 text-center text-sm">Loading…</div> : null}
        {data ? (
          <svg
            width={W} height={H}
            role="img" tabIndex={0} onKeyDown={onKey} onBlur={() => setHover(null)}
            aria-label={`Daily ${metric} for the last ${days} days. Use the arrow keys to read each day.`}
            onMouseMove={move} onMouseLeave={() => setHover(null)}
            onTouchStart={(e) => move(e.touches[0])} onTouchMove={(e) => move(e.touches[0])}
            style={{ touchAction: "pan-y", outline: "none" }}
          >
            {ticks.map((t) => (
              <g key={t}>
                <line x1={LEFT} x2={W} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeDasharray={t === 0 ? undefined : "3 4"} />
                <text x={LEFT - 6} y={y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--muted)">{num(t)}</text>
              </g>
            ))}
            {rows.map((r, i) => {
              const x = LEFT + i * bw + (bw - barW) / 2;
              const active = hover === i;
              let acc = 0;
              const segs = metric === "views"
                ? [{ key: "_views", v: r.views, color: "var(--accent)" }]
                : r.parts.map((p) => ({ key: p.key, v: p.v, color: colorOf[p.key] }));
              return (
                <g key={r.date} opacity={hover === null || active ? 1 : 0.5}>
                  {active ? <rect x={LEFT + i * bw} y={TOP} width={bw} height={innerH} fill="var(--glass-strong)" rx="6" /> : null}
                  {segs.map((s) => {
                    const h = (s.v / max) * innerH;
                    const top = y(acc + s.v);
                    acc += s.v;
                    return <rect key={s.key} x={x} y={top} width={barW} height={Math.max(0, h - 1)} rx="2.5" fill={s.color} />;
                  })}
                  {metric === "videos" && showFailed && r.failed ? (
                    <rect x={x} y={y(acc + r.failed)} width={barW} height={Math.max(0, (r.failed / max) * innerH - 1)} rx="2.5" fill="var(--bad)" opacity="0.8" />
                  ) : null}
                  {metricVal(r) === 0 ? <rect x={x} y={y(0) - 2} width={barW} height={2} rx="1" fill="var(--line)" /> : null}
                  {(rows.length - 1 - i) % labelEvery === 0 ? (
                    <text x={i === rows.length - 1 ? Math.min(x + barW, W - 2) : x + barW / 2} y={H - 8} textAnchor={i === rows.length - 1 ? "end" : "middle"} fontSize="10" fill={active ? "var(--text)" : "var(--muted)"} fontWeight={active ? 600 : 400}>
                      {istDay(r.date + "T12:00:00+05:30")}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>
        ) : null}

        {sel ? (() => {
          const TW = metric === "videos" && sel.parts.length > 5 ? 264 : 188;
          const cx = LEFT + hover * bw + bw / 2;
          const left = cx > W / 2 ? cx - TW - barW / 2 - 8 : cx + barW / 2 + 8;
          return (
            <div
              className="pointer-events-none absolute z-10 rounded-xl border border-[var(--edge)] p-3 text-xs shadow-xl backdrop-blur-xl"
              style={{ top: 2, width: TW, left: Math.min(Math.max(0, left), Math.max(0, W - TW)), background: "color-mix(in srgb, var(--base) 92%, transparent)" }}
            >
              <div className="mb-1.5 font-semibold">{istDay(sel.date + "T12:00:00+05:30")}</div>
              {metric === "videos" ? (
                <>
                  {sel.parts.length === 0 ? <div className="muted">Nothing published</div> : null}
                  <div className={TW > 200 ? "grid grid-cols-2 gap-x-4" : ""}>
                    {sel.parts.map((p) => (
                      <div key={p.key} className="flex items-center justify-between gap-2 py-px">
                        <span className="flex min-w-0 items-center gap-1.5"><i className="inline-block h-2 w-2 shrink-0 rounded-sm" style={{ background: colorOf[p.key] }} /><span className="truncate">{nameOf[p.key]}</span></span>
                        <b>{p.v}</b>
                      </div>
                    ))}
                  </div>
                  <div className="hairline mt-1.5 flex justify-between border-t pt-1"><span className="muted">Published</span><b>{sel.videos}</b></div>
                  {sel.failed ? <div className="flex justify-between text-red-500"><span>Failed runs</span><b>{sel.failed}</b></div> : null}
                </>
              ) : (
                <>
                  <div className="flex justify-between"><span className="muted">Views</span><b>{num(sel.views)}</b></div>
                  <div className="flex justify-between"><span className="muted">Videos</span><b>{sel.videos}</b></div>
                  {sel.videos ? <div className="flex justify-between"><span className="muted">Avg per video</span><b>{num(Math.round(sel.views / sel.videos))}</b></div> : null}
                </>
              )}
            </div>
          );
        })() : null}
      </div>

      {data ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {metric === "videos" ? chans.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => toggle(c.key)}
              onDoubleClick={() => soloOrAll(c.key)}
              aria-pressed={!off.has(c.key)}
              title="Click to hide or show. Double-click to show only this channel."
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${off.has(c.key) ? "border-transparent opacity-40 hover:opacity-80" : "border-[var(--edge)] glass"}`}
            >
              <i className="inline-block h-2 w-2 rounded-sm" style={{ background: colorOf[c.key] }} />{c.name}
            </button>
          )) : null}
          {metric === "videos" ? (
            <Chip on={showFailed} onClick={() => setShowFailed((v) => !v)} color="var(--bad)">Failed runs</Chip>
          ) : null}
          {off.size ? <button type="button" className="muted text-[11px] underline" onClick={() => setOff(new Set())}>Show all</button> : null}
        </div>
      ) : null}
    </div>
  );
}

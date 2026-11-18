import { istDay } from "../lib/format";

// 14-day stacked bars: published (green) and failed (red).
export function ActivityChart({ data }) {
  const W = 560, H = 140, PAD = 22, n = data.length;
  const max = Math.max(1, ...data.map((d) => d.published + d.failed));
  const bw = (W - PAD) / n;
  return (
    <svg viewBox={`0 0 ${W} ${H + 22}`} className="w-full" role="img" aria-label="Videos published and failed runs, last 14 days">
      {[0.5, 1].map((f) => (
        <line key={f} x1={PAD} x2={W} y1={H - H * f * 0.9} y2={H - H * f * 0.9} stroke="var(--line)" strokeDasharray="3 4" />
      ))}
      {data.map((d, i) => {
        const x = PAD + i * bw + bw * 0.18;
        const w = bw * 0.64;
        const hp = (d.published / max) * H * 0.9;
        const hf = (d.failed / max) * H * 0.9;
        return (
          <g key={d.date}>
            <title>{`${istDay(d.date)} — ${d.published} published, ${d.failed} failed`}</title>
            <rect x={x} y={H - hp} width={w} height={hp} rx="3" fill="var(--ok)" />
            <rect x={x} y={H - hp - hf} width={w} height={hf} rx="3" fill="var(--bad)" opacity="0.85" />
            {d.published + d.failed === 0 ? <rect x={x} y={H - 2} width={w} height={2} rx="1" fill="var(--line)" /> : null}
            {i % 3 === 0 || i === n - 1 ? (
              <text x={x + w / 2} y={H + 15} textAnchor="middle" fontSize="10" fill="var(--muted)">
                {istDay(d.date)}
              </text>
            ) : null}
          </g>
        );
      })}
      <text x="0" y={H - H * 0.9 + 4} fontSize="10" fill="var(--muted)">{max}</text>
      <text x="0" y={H + 1} fontSize="10" fill="var(--muted)">0</text>
    </svg>
  );
}

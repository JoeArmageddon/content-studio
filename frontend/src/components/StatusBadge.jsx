const COLORS = {
  published: "bg-green-100 text-green-800",
  done: "bg-green-100 text-green-800",
  draft: "bg-slate-100 text-slate-700",
  failed: "bg-red-100 text-red-800",
  running: "bg-blue-100 text-blue-800",
  pending: "bg-amber-100 text-amber-800",
};

export default function StatusBadge({ status }) {
  const cls = COLORS[status] || "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {status || "unknown"}
    </span>
  );
}

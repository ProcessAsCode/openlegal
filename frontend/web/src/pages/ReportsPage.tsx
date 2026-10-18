import { useEffect, useState } from "react";
import { getOrgSlug } from "../api/client";

type Summary = {
  totals: {
    cases: number;
    events: number;
    signed_vcs: number;
    triaged: number;
    resolved: number;
  };
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_source: Record<string, number>;
  vcs_by_type: Record<string, number>;
};

const PRIORITY_COLOR: Record<string, string> = {
  P1: "bg-rose-100 text-rose-800 ring-rose-200",
  P2: "bg-amber-100 text-amber-800 ring-amber-200",
  P3: "bg-sky-100 text-sky-800 ring-sky-200",
  P4: "bg-slate-100 text-slate-700 ring-slate-200",
  "—": "bg-slate-50 text-slate-500 ring-slate-200",
};

const STATUS_COLOR: Record<string, string> = {
  open: "bg-blue-100 text-blue-800",
  triaged: "bg-sky-100 text-sky-800",
  in_progress: "bg-amber-100 text-amber-800",
  waiting_customer: "bg-amber-50 text-amber-700",
  waiting_third_party: "bg-amber-50 text-amber-700",
  resolved: "bg-emerald-100 text-emerald-800",
  closed: "bg-slate-200 text-slate-700",
  cancelled: "bg-rose-100 text-rose-800",
};

export function ReportsPage() {
  const [data, setData] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/reports/summary", { headers: { "X-Org-Slug": getOrgSlug() } })
      .then((r) => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
      .then(setData)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-sm text-slate-500">Loading reports…</div>;
  }
  if (err || !data) {
    return <div className="text-sm text-rose-600">Failed to load reports: {err ?? "no data"}</div>;
  }

  const T = data.totals;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Reports</h1>
        <p className="mt-1 text-sm text-slate-500">
          POC dashboard. SLA compliance, MTTR trends, AI accuracy reports — Phase 1 deliverables.
        </p>
      </div>

      {/* Tiles */}
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Tile label="Cases" value={T.cases} />
        <Tile label="Triaged" value={T.triaged} />
        <Tile label="Resolved + closed" value={T.resolved} />
        <Tile label="Timeline events" value={T.events} />
        <Tile
          label="Signed VCs"
          value={T.signed_vcs}
          accent="emerald"
          sub="Anchored in Register"
        />
      </div>

      {/* Breakdowns */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <BarBlock title="By priority" data={data.by_priority} colorMap={PRIORITY_COLOR} order={["P1","P2","P3","P4","—"]} />
        <BarBlock title="By status" data={data.by_status} colorMap={STATUS_COLOR} />
        <BarBlock title="By source" data={data.by_source} />
        <BarBlock title="Signed VCs by type" data={data.vcs_by_type} />
      </div>

      <p className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
        Each row in <strong>Signed VCs by type</strong> represents a Verifiable Credential anchored in the
        VeriDocs Register and verifiable independently of OpenLegal. Generate a W3C Verifiable Presentation
        bundling these for any reporting period to produce regulator-grade audit evidence.
      </p>
    </div>
  );
}

function Tile({ label, value, accent, sub }: { label: string; value: number; accent?: string; sub?: string }) {
  const ringClass = accent === "emerald" ? "ring-1 ring-emerald-200 bg-emerald-50" : "ring-1 ring-slate-200 bg-white";
  const valueClass = accent === "emerald" ? "text-emerald-800" : "text-slate-800";
  return (
    <div className={`rounded-lg p-4 ${ringClass}`}>
      <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${valueClass}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

function BarBlock({ title, data, colorMap, order }: { title: string; data: Record<string, number>; colorMap?: Record<string,string>; order?: string[] }) {
  const entries = Object.entries(data);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  if (total === 0) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">{title}</h2>
        <p className="text-xs text-slate-400">No data</p>
      </section>
    );
  }
  const sorted = order
    ? entries.sort((a, b) => (order.indexOf(a[0]) - order.indexOf(b[0])))
    : entries.sort((a, b) => b[1] - a[1]);
  const max = Math.max(...sorted.map((e) => e[1]));
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">{title}</h2>
      <div className="space-y-1.5">
        {sorted.map(([k, v]) => {
          const pct = Math.round((v / max) * 100);
          const klass = colorMap?.[k] ?? "bg-sky-100 text-sky-800 ring-sky-200";
          return (
            <div key={k} className="flex items-center gap-2">
              <span className={`pill min-w-[80px] truncate text-[11px] ring-1 ${klass}`}>{k}</span>
              <div className="relative h-3 flex-1 overflow-hidden rounded bg-slate-100">
                <div className="h-full rounded bg-slate-400/80" style={{ width: `${pct}%` }} />
              </div>
              <span className="w-8 text-right font-mono text-xs text-slate-600">{v}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

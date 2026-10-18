import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { GovernanceCalendar } from "../api/client";

function kindRule(b: GovernanceCalendar["bodies"][number]): string {
  if (b.kind === "recurring") {
    const cad = b.cadence === "weekly" ? `weekly (${b.pattern})` : `monthly (${b.pattern?.replace("_", " ")})`;
    return `${cad} · submit ${b.submission_cutoff_working_days} working days before`;
  }
  if (b.kind === "lead_time") return `~${b.lead_working_days} working days lead`;
  if (b.kind === "on_demand") return `on demand · ~${b.lead_calendar_days} calendar days`;
  return b.kind;
}

export default function CalendarPage() {
  const [cal, setCal] = useState<GovernanceCalendar | null>(null);
  const [weeks, setWeeks] = useState(10);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getGovernanceCalendar(weeks)
      .then(setCal)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [weeks]);

  const today = new Date().toISOString().slice(0, 10);
  const soon = (d: string) => {
    const diff = (new Date(d).getTime() - new Date(today).getTime()) / 86400000;
    return diff >= 0 && diff <= 5;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Governance calendar</h1>
          <p className="text-sm text-slate-600">
            Cadence-as-Code: the sitting schedule and submission cutoffs the scheduling
            engine plans approval chains against. Rules are versioned in the process package.
          </p>
        </div>
        <label className="text-xs text-slate-600">
          Horizon
          <select className="ml-2 rounded border border-slate-300 px-2 py-1 text-sm"
                  value={weeks} onChange={(e) => setWeeks(Number(e.target.value))}>
            <option value={4}>4 weeks</option>
            <option value={10}>10 weeks</option>
            <option value={26}>26 weeks</option>
          </select>
        </label>
      </div>

      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      {cal && (
        <>
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Bodies & cadence rules
            </h2>
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Body</th>
                    <th className="px-3 py-2">Rule</th>
                    <th className="px-3 py-2">Prerequisite</th>
                  </tr>
                </thead>
                <tbody>
                  {cal.bodies.map((b) => (
                    <tr key={b.body} className="border-t border-slate-100">
                      <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-800">{b.label}</td>
                      <td className="px-3 py-2 text-slate-700">{kindRule(b)}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-slate-500">{b.prerequisite ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Upcoming sittings <span className="normal-case text-slate-400">(as of {cal.as_of})</span>
            </h2>
            {cal.sittings.length === 0 ? (
              <p className="text-sm text-slate-500">No sittings inside this horizon.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Sitting</th>
                      <th className="px-3 py-2">Body</th>
                      <th className="px-3 py-2">Submit agenda items by</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cal.sittings.map((s) => (
                      <tr key={`${s.body}-${s.date}`} className="border-t border-slate-100">
                        <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-800">{s.date}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-slate-700">{s.label}</td>
                        <td className="whitespace-nowrap px-3 py-2">
                          <span className={`rounded border px-2 py-0.5 text-xs ${soon(s.submit_by) ? "border-amber-300 bg-amber-50 text-amber-800" : "border-slate-200 bg-slate-50 text-slate-600"}`}>
                            {s.submit_by}{soon(s.submit_by) ? " · soon" : ""}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-2 text-xs text-slate-500">
              The Obligations board uses this calendar to compute approval-chain feasibility.
              Pilot values are illustrative until the organisation's kārtības rullis is codified in Discovery.
            </p>
          </section>
        </>
      )}
    </div>
  );
}

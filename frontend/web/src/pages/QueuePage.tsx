import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { CaseStatus, CaseSummary } from "../api/types";
import { PriorityBadge, StatusBadge } from "../components/Badges";

const STATUS_FILTERS: { value: CaseStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "triaged", label: "Triaged" },
  { value: "in_progress", label: "In progress" },
  { value: "waiting_customer", label: "Waiting" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

export function QueuePage() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<CaseStatus | "all">("all");

  useEffect(() => {
    let cancelled = false;
    setCases(null);
    setError(null);

    const opts = filter === "all" ? {} : { status: [filter] };
    api
      .listIncidents(opts)
      .then((res) => { if (!cancelled) setCases(res); })
      .catch((e) => { if (!cancelled) setError(String(e.message ?? e)); });

    return () => { cancelled = true; };
  }, [filter]);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex items-baseline justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Queue</h1>
        <span className="text-sm text-slate-500">
          {cases ? `${cases.length} cases` : ""}
        </span>
      </div>

      <div className="mb-4 flex gap-1 rounded-lg border border-slate-200 bg-white p-1">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              filter === f.value
                ? "bg-accent-600 text-white"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          Failed to load: {error}
        </div>
      )}

      {cases === null && !error && (
        <div className="rounded border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
          Loading...
        </div>
      )}

      {cases && cases.length === 0 && (
        <div className="rounded border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          No cases match this filter.
        </div>
      )}

      {cases && cases.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Case #</th>
                <th className="px-4 py-2.5 font-medium">Title</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Priority</th>
                <th className="px-4 py-2.5 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cases.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-mono text-xs text-slate-700">
                    <Link to={`/cases/${c.id}`} className="text-accent-700 hover:underline">
                      {c.case_number}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5">
                    <Link to={`/cases/${c.id}`} className="text-slate-800 hover:underline">
                      {c.title}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5"><StatusBadge status={c.status} /></td>
                  <td className="px-4 py-2.5"><PriorityBadge priority={c.priority} /></td>
                  <td className="px-4 py-2.5 text-xs text-slate-500">
                    {new Date(c.updated_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getOrgSlug } from "../api/client";

type AuditRow = {
  id: string;
  case_id: string;
  case_number: string | null;
  type: string;
  actor_type: string;
  actor_label: string | null;
  trace_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  vc: {
    vc_id: string;
    vc_type: string;
    issuer_did: string;
    subject_did: string;
    vc_hash: string | null;
  } | null;
};

const TYPE_LABELS: Record<string, string> = {
  signal_attached: "Signal attached",
  normalized: "Normalized",
  classified: "Classified",
  prioritized: "Priority set",
  ownership_decided: "Ownership decided",
  routed: "Routed",
  assigned: "Assigned",
  status_changed: "Status changed",
  priority_changed: "Priority changed",
  ai_proposal_created: "AI proposal created",
  comment_added: "Comment added",
  customer_reply_sent: "Reply sent",
  vc_issued: "VC issued",
  resolved: "Resolved",
  closed: "Closed",
};

export function AuditPage() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [signedOnly, setSignedOnly] = useState(false);
  const [hours, setHours] = useState(168); // 7 days
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({
      limit: "200",
      since_hours: String(hours),
      ...(signedOnly ? { signed_only: "true" } : {}),
    });
    fetch(`/api/incidents/events/audit?${params}`, {
      headers: { "X-Org-Slug": getOrgSlug() },
    })
      .then((r) => r.json())
      .then((data) => Array.isArray(data) ? setRows(data) : setRows([]))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [signedOnly, hours]);

  const signedCount = rows.filter((r) => r.vc).length;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Audit log</h1>
          <p className="mt-1 text-sm text-slate-500">
            Org-wide append-only event feed. Green VC pill = signed Verifiable Credential anchored in VeriDocs Register.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-600">
          <span>
            <span className="font-mono text-slate-800">{rows.length}</span> rows ·
            <span className="ml-1 font-mono text-emerald-700">{signedCount}</span> signed
          </span>
        </div>
      </div>

      <div className="mb-3 flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={signedOnly}
            onChange={(e) => setSignedOnly(e.target.checked)}
            className="rounded border-slate-300"
          />
          <span className="text-slate-700">Signed VCs only</span>
        </label>
        <span className="text-slate-300">|</span>
        <label className="flex items-center gap-2">
          <span className="text-slate-700">Last</span>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value={24}>24 hours</option>
            <option value={72}>3 days</option>
            <option value={168}>7 days</option>
            <option value={720}>30 days</option>
          </select>
        </label>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-3 py-2">When</th>
              <th className="px-3 py-2">Case</th>
              <th className="px-3 py-2">Event</th>
              <th className="px-3 py-2">Actor</th>
              <th className="px-3 py-2">VC</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-400">Loading…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-400">No events.</td></tr>
            )}
            {rows.map((r) => (
              <>
                <tr
                  key={r.id}
                  className="cursor-pointer hover:bg-slate-50"
                  onClick={() => setExpandedRowId(expandedRowId === r.id ? null : r.id)}
                >
                  <td className="px-3 py-2 font-mono text-xs text-slate-500">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {r.case_number ? (
                      <Link to={`/cases/${r.case_id}`} className="text-sky-700 hover:underline" onClick={(e) => e.stopPropagation()}>
                        {r.case_number}
                      </Link>
                    ) : "—"}
                  </td>
                  <td className="px-3 py-2 text-slate-700">{TYPE_LABELS[r.type] ?? r.type}</td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-500">{r.actor_label ?? r.actor_type}</td>
                  <td className="px-3 py-2">
                    {r.vc ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-emerald-200">
                        <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M10 1l7 3v6c0 4.4-3 8.4-7 9-4-0.6-7-4.6-7-9V4l7-3zm0 9.5l4.5-4.5L13 4.5 10 7.5 7 4.5 5.5 6 10 10.5z" clipRule="evenodd"/></svg>
                        {r.vc.vc_type}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                </tr>
                {expandedRowId === r.id && (
                  <tr className="bg-slate-50">
                    <td colSpan={5} className="px-3 py-3 text-xs">
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        <div>
                          <div className="mb-1 font-semibold text-slate-700">Payload</div>
                          <pre className="overflow-x-auto rounded bg-white p-2 font-mono text-[11px]">{JSON.stringify(r.payload, null, 2)}</pre>
                        </div>
                        {r.vc && (
                          <div>
                            <div className="mb-1 font-semibold text-slate-700">Verifiable Credential</div>
                            <dl className="space-y-1">
                              <div>
                                <dt className="text-slate-500">Issuer DID</dt>
                                <dd className="break-all font-mono text-[11px] text-slate-700">{r.vc.issuer_did}</dd>
                              </div>
                              <div>
                                <dt className="text-slate-500">VC ID (subject)</dt>
                                <dd className="break-all font-mono text-[11px] text-slate-700">{r.vc.vc_id}</dd>
                              </div>
                              {r.vc.vc_hash && (
                                <div>
                                  <dt className="text-slate-500">Hash</dt>
                                  <dd className="break-all font-mono text-[11px] text-slate-700">{r.vc.vc_hash}</dd>
                                </div>
                              )}
                              {r.trace_id && (
                                <div>
                                  <dt className="text-slate-500">Trace ID</dt>
                                  <dd className="break-all font-mono text-[11px] text-slate-700">{r.trace_id}</dd>
                                </div>
                              )}
                            </dl>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

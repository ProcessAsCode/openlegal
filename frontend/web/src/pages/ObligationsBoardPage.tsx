import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ChainPlan, GovernanceAlert, GovernanceRunReport } from "../api/client";

const sevClasses: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-300",
  warning: "bg-amber-100 text-amber-800 border-amber-300",
  info: "bg-slate-100 text-slate-700 border-slate-300",
};

function SeverityBadge({ severity }: { severity: string }) {
  const cls = sevClasses[severity] ?? sevClasses.info;
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {severity}
    </span>
  );
}

function ChainTimeline({ plan }: { plan: ChainPlan }) {
  return (
    <div className="mt-2 rounded border border-slate-200 bg-slate-50 p-3 text-sm">
      <div className="mb-2 flex items-center gap-3">
        <span className={`font-semibold ${plan.feasible ? "text-emerald-700" : "text-red-700"}`}>
          {plan.feasible ? "FEASIBLE" : "INFEASIBLE"}
        </span>
        <span className="text-slate-600">
          deadline {plan.deadline} · earliest completion {plan.completion ?? "—"} · slack{" "}
          <b>{plan.slack_days ?? "—"} days</b>
        </span>
      </div>
      <ol className="space-y-1">
        {plan.milestones.map((m) => (
          <li key={m.body} className="flex flex-wrap items-baseline gap-2">
            <span className="font-medium text-slate-800">{m.label}</span>
            <span className="text-slate-600">{m.date}</span>
            {m.submission_deadline && (
              <span className="text-xs text-slate-500">(submit by {m.submission_deadline})</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function ObligationsBoardPage() {
  const [report, setReport] = useState<GovernanceRunReport | null>(null);
  const [alerts, setAlerts] = useState<GovernanceAlert[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAlerts = useCallback(async () => {
    try {
      const res = await api.getGovernanceAlerts(100);
      setAlerts(res.alerts);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void loadAlerts();
  }, [loadAlerts]);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const rep = await api.runGovernance();
      setReport(rep);
      await loadAlerts();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Obligations board</h1>
          <p className="text-sm text-slate-600">
            Governance-as-Code monitoring: contract obligations, corporate approvals and the
            governance calendar — package <code>lv.example.legal.governance_monitoring</code>.
          </p>
        </div>
        <button
          onClick={() => void run()}
          disabled={running}
          className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {running ? "Running…" : "Run governance monitoring"}
        </button>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>
      )}

      {report && (
        <section className="space-y-4">
          <h2 className="text-lg font-medium text-slate-900">
            Run report{" "}
            <span className="text-sm font-normal text-slate-500">
              as of {report.as_of} · {report.alerts_created} alert(s) created
            </span>
          </h2>
          {report.contracts.map((c) => (
            <div key={c.contract} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-2">
                <span className="font-semibold text-slate-900">{c.contract}</span>
                <span className="ml-2 text-sm text-slate-600">{c.title}</span>
              </div>
              {c.findings.length === 0 && (
                <p className="text-sm text-emerald-700">No findings — all obligations in order.</p>
              )}
              <ul className="space-y-3">
                {c.findings.map((f) => (
                  <li key={f.obligation} className="border-t border-slate-100 pt-3 first:border-t-0 first:pt-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={f.severity} />
                      <code className="text-sm">{f.obligation}</code>
                      <span className="text-xs uppercase tracking-wide text-slate-500">{f.state}</span>
                      <span className="text-xs text-slate-400">→ {f.action}</span>
                    </div>
                    <p className="mt-1 text-sm text-slate-700">{f.message}</p>
                    {f.schedule && <ChainTimeline plan={f.schedule} />}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      <section>
        <h2 className="mb-2 text-lg font-medium text-slate-900">
          Alert board{" "}
          <span className="text-sm font-normal text-slate-500">({alerts.length} recorded)</span>
        </h2>
        {alerts.length === 0 ? (
          <p className="text-sm text-slate-500">
            No alerts yet — run governance monitoring to populate the board.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2">Severity</th>
                  <th className="px-3 py-2">Contract</th>
                  <th className="px-3 py-2">Obligation</th>
                  <th className="px-3 py-2">Action</th>
                  <th className="px-3 py-2">Message</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100 align-top">
                    <td className="whitespace-nowrap px-3 py-2 text-slate-500">
                      {a.at.slice(0, 16).replace("T", " ")}
                    </td>
                    <td className="px-3 py-2"><SeverityBadge severity={a.severity} /></td>
                    <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-800">{a.contract}</td>
                    <td className="whitespace-nowrap px-3 py-2"><code>{a.obligation}</code></td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-600">{a.action}</td>
                    <td className="px-3 py-2 text-slate-700">{a.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { CaseDetail, CaseEvent, CaseStatus } from "../api/types";
import { PriorityBadge, StatusBadge } from "../components/Badges";
import { TimelineEvent } from "../components/TimelineEvent";

// FSM transitions (must match services/incident._ALLOWED_TRANSITIONS).
const ALLOWED: Record<CaseStatus, CaseStatus[]> = {
  open: ["triaged", "in_progress", "cancelled"],
  triaged: ["in_progress", "waiting_customer", "waiting_third_party", "resolved", "cancelled"],
  in_progress: ["waiting_customer", "waiting_third_party", "resolved", "cancelled"],
  waiting_customer: ["in_progress", "resolved", "cancelled"],
  waiting_third_party: ["in_progress", "resolved", "cancelled"],
  resolved: ["closed", "in_progress"],
  closed: [],
  cancelled: [],
};

const TRANSITION_LABEL: Record<CaseStatus, string> = {
  open: "Reopen",
  triaged: "Mark triaged",
  in_progress: "Start work",
  waiting_customer: "Wait on customer",
  waiting_third_party: "Wait on 3rd party",
  resolved: "Resolve",
  closed: "Close",
  cancelled: "Cancel",
};

export function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [events, setEvents] = useState<CaseEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transitioning, setTransitioning] = useState<CaseStatus | null>(null);

  const loadAll = useCallback(async () => {
    if (!caseId) return;
    try {
      const [c, e] = await Promise.all([
        api.getIncident(caseId),
        api.listIncidentEvents(caseId),
      ]);
      setCaseDetail(c);
      setEvents(e);
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }, [caseId]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const onTransition = useCallback(
    async (to: CaseStatus) => {
      if (!caseId) return;
      setTransitioning(to);
      try {
        await api.transitionIncident(caseId, to);
        await loadAll();
      } catch (e) {
        setError(String((e as Error).message ?? e));
      } finally {
        setTransitioning(null);
      }
    },
    [caseId, loadAll],
  );

  if (error && !caseDetail) {
    return (
      <div className="mx-auto max-w-4xl rounded border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        Failed to load: {error}{" "}
        <Link to="/queue" className="ml-2 underline">Back to queue</Link>
      </div>
    );
  }

  if (!caseDetail || !events) {
    return <div className="text-sm text-slate-500">Loading case...</div>;
  }

  const nextStatuses = ALLOWED[caseDetail.status];

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
          <Link to="/queue" className="hover:underline">Queue</Link>
          <span>/</span>
          <span className="font-mono">{caseDetail.case_number}</span>
        </div>
        <h1 className="mb-3 text-xl font-semibold tracking-tight">
          {caseDetail.title}
        </h1>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <StatusBadge status={caseDetail.status} />
          <PriorityBadge priority={caseDetail.priority} />
          {caseDetail.ownership && (
            <span className="pill bg-slate-100 text-slate-700">
              {caseDetail.ownership}
            </span>
          )}
          {caseDetail.jira_mirror_key && (
            <span className="pill bg-blue-50 text-blue-700 ring-1 ring-blue-200">
              Jira: {caseDetail.jira_mirror_key}
            </span>
          )}
        </div>

        {caseDetail.description && (
          <div className="mb-6 whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">
            {caseDetail.description}
          </div>
        )}

        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
            Timeline
          </h2>
          <span className="text-xs text-slate-400">
            {events.length} events
          </span>
        </div>
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white px-4">
          {events.map((e) => (
            <TimelineEvent key={e.id} event={e} />
          ))}
        </ul>

        {error && (
          <div className="mt-3 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {error}
          </div>
        )}
      </div>

      <aside className="lg:col-span-1">
        <div className="sticky top-4 rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Actions
          </h3>
          {nextStatuses.length === 0 ? (
            <p className="text-sm text-slate-500">
              No transitions available from <strong>{caseDetail.status}</strong> (terminal).
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {nextStatuses.map((to) => (
                <button
                  key={to}
                  onClick={() => onTransition(to)}
                  disabled={transitioning !== null}
                  className="rounded border border-slate-300 px-3 py-2 text-left text-sm hover:border-accent-500 hover:bg-accent-50 disabled:opacity-50"
                >
                  {TRANSITION_LABEL[to]}
                  <span className="ml-2 text-xs text-slate-400">
                    -&gt; {to}
                  </span>
                </button>
              ))}
            </div>
          )}

          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Times
          </h3>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
            <dt className="text-slate-500">Opened</dt>
            <dd className="font-mono">{new Date(caseDetail.opened_at).toLocaleString()}</dd>
            {caseDetail.triaged_at && (<>
              <dt className="text-slate-500">Triaged</dt>
              <dd className="font-mono">{new Date(caseDetail.triaged_at).toLocaleString()}</dd>
            </>)}
            {caseDetail.resolved_at && (<>
              <dt className="text-slate-500">Resolved</dt>
              <dd className="font-mono">{new Date(caseDetail.resolved_at).toLocaleString()}</dd>
            </>)}
            {caseDetail.closed_at && (<>
              <dt className="text-slate-500">Closed</dt>
              <dd className="font-mono">{new Date(caseDetail.closed_at).toLocaleString()}</dd>
            </>)}
          </dl>
        </div>
      </aside>
    </div>
  );
}

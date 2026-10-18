import type { CasePriority, CaseStatus } from "../api/types";

const STATUS_STYLES: Record<CaseStatus, string> = {
  open: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
  triaged: "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200",
  in_progress: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  waiting_customer: "bg-slate-100 text-slate-700 ring-1 ring-slate-200",
  waiting_third_party: "bg-slate-100 text-slate-700 ring-1 ring-slate-200",
  resolved: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  closed: "bg-slate-200 text-slate-600 ring-1 ring-slate-300",
  cancelled: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
};

const STATUS_LABELS: Record<CaseStatus, string> = {
  open: "Open",
  triaged: "Triaged",
  in_progress: "In progress",
  waiting_customer: "Waiting (customer)",
  waiting_third_party: "Waiting (3rd party)",
  resolved: "Resolved",
  closed: "Closed",
  cancelled: "Cancelled",
};

export function StatusBadge({ status }: { status: CaseStatus }) {
  return (
    <span className={`pill ${STATUS_STYLES[status]}`}>{STATUS_LABELS[status]}</span>
  );
}

const PRIORITY_STYLES: Record<CasePriority, string> = {
  P1: "bg-prio-p1/10 text-prio-p1 ring-1 ring-prio-p1/30",
  P2: "bg-prio-p2/10 text-prio-p2 ring-1 ring-prio-p2/30",
  P3: "bg-prio-p3/10 text-prio-p3 ring-1 ring-prio-p3/30",
  P4: "bg-prio-p4/10 text-prio-p4 ring-1 ring-prio-p4/30",
};

export function PriorityBadge({ priority }: { priority: CasePriority | null }) {
  if (!priority) {
    return <span className="pill bg-slate-100 text-slate-500">-</span>;
  }
  return (
    <span className={`pill font-semibold ${PRIORITY_STYLES[priority]}`}>
      {priority}
    </span>
  );
}

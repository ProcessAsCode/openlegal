import { useState } from "react";
import type { CaseEvent, VCSummary } from "../api/types";
import { getOrgSlug } from "../api/client";

/* Render one row of a case's timeline.
 *
 * Phase 1 keeps formatting minimal: an icon-like glyph for the actor type,
 * the event type, an inline preview of the payload, and a relative timestamp.
 * Operator-friendly explanations of each event type are intentionally minimal
 * for the PoC; Phase 2 will expand with VC linking + AI-decision context.
 */

const ACTOR_GLYPH: Record<string, string> = {
  system: "·",
  user: "U",
  ai: "AI",
  uapf: "P",
  adapter: "A",
  external: "X",
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
  ai_proposal_approved: "AI proposal approved",
  ai_proposal_rejected: "AI proposal rejected",
  ai_proposal_applied: "AI proposal applied",
  comment_added: "Comment added",
  customer_reply_sent: "Reply sent to customer",
  vc_issued: "VC issued",
  jira_synced: "Jira mirror synced",
  escalated: "Escalated",
  sla_warning: "SLA warning",
  sla_breached: "SLA breached",
  resolved: "Resolved",
  closed: "Closed",
  reopened: "Reopened",
  uapf_capability_invoked: "UAPF capability invoked",
  operator_override: "Operator override",
};

function formatRelativeTime(iso: string): string {
  const dt = new Date(iso);
  const now = Date.now();
  const diffSec = Math.round((now - dt.getTime()) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)}h ago`;
  return dt.toLocaleString();
}

function payloadPreview(event: CaseEvent): string | null {
  const p = event.payload;
  if (!p) return null;
  if (event.type === "status_changed") {
    return `${p.from ?? "open"} -> ${p.to ?? "?"}`;
  }
  if (event.type === "routed") {
    const grp = p.group_slug;
    const prio = p.priority;
    return [grp, prio].filter(Boolean).join(" / ");
  }
  if (event.type === "prioritized" || event.type === "priority_changed") {
    const patch = (p as { patch?: { priority?: string } }).patch;
    return patch?.priority ?? null;
  }
  if (event.type === "comment_added") {
    const v = (p as { body_preview?: string }).body_preview;
    return v ?? null;
  }
  if (event.type === "signal_attached") {
    return [p.source, p.external_id].filter(Boolean).join(" / ");
  }
  if (event.type === "jira_synced") {
    return (p as { jira_mirror_key?: string }).jira_mirror_key ?? null;
  }
  return null;
}

export function TimelineEvent({ event }: { event: CaseEvent }) {
  const label = TYPE_LABELS[event.type] ?? event.type;
  const preview = payloadPreview(event);
  const glyph = ACTOR_GLYPH[event.actor_type] ?? "·";
  const vc = event.vc;

  return (
    <li className="flex gap-3 py-2.5">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[10px] font-semibold text-slate-600">
        {glyph}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-800">{label}</span>
            {vc && <VCShield vc={vc} />}
          </div>
          <span className="shrink-0 text-xs text-slate-400" title={event.created_at}>
            {formatRelativeTime(event.created_at)}
          </span>
        </div>
        {preview && (
          <div className="mt-0.5 truncate text-sm text-slate-600">{preview}</div>
        )}
        {event.actor_label && (
          <div className="mt-0.5 font-mono text-xs text-slate-400">{event.actor_label}</div>
        )}
      </div>
    </li>
  );
}

type VerifyState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; issuer: string; vc_type: string }
  | { status: "fail"; reason?: string };

function VCShield({ vc }: { vc: VCSummary }) {
  const [open, setOpen] = useState(false);
  const [verify, setVerify] = useState<VerifyState>({ status: "idle" });

  async function runVerify() {
    setVerify({ status: "loading" });
    try {
      const url = `/api/incidents/vc/${encodeURIComponent(vc.vc_id)}/verify`;
      const r = await fetch(url, { headers: { "X-Org-Slug": getOrgSlug() } });
      if (!r.ok) {
        setVerify({ status: "fail", reason: `HTTP ${r.status}` });
        return;
      }
      const data = await r.json();
      if (data.verified === true) {
        setVerify({ status: "ok", issuer: data.issuer_did, vc_type: data.vc_type });
      } else if (data.verified === false) {
        setVerify({ status: "fail", reason: data.raw?.error || "Signature did not verify" });
      } else {
        setVerify({ status: "fail", reason: data.reason || "Verification inconclusive" });
      }
    } catch (e: unknown) {
      setVerify({ status: "fail", reason: String(e) });
    }
  }

  return (
    <span className="relative inline-flex">
      <button
        onClick={() => setOpen(!open)}
        title={`Signed: ${vc.vc_type}`}
        className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-emerald-200 hover:bg-emerald-100"
      >
        <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M10 1l7 3v6c0 4.4-3 8.4-7 9-4-0.6-7-4.6-7-9V4l7-3zm0 9.5l4.5-4.5L13 4.5 10 7.5 7 4.5 5.5 6 10 10.5z" clipRule="evenodd"/></svg>
        VC
      </button>
      {open && (
        <div className="absolute left-0 top-6 z-10 w-96 rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-lg">
          <div className="mb-1 font-semibold text-slate-700">{vc.vc_type}</div>
          <dl className="space-y-1">
            <div>
              <dt className="text-slate-500">Issuer DID</dt>
              <dd className="break-all font-mono text-[11px] text-slate-700">{vc.issuer_did}</dd>
            </div>
            <div>
              <dt className="text-slate-500">VC ID (subject)</dt>
              <dd className="break-all font-mono text-[11px] text-slate-700">{vc.vc_id}</dd>
            </div>
            {vc.vc_hash && (
              <div>
                <dt className="text-slate-500">Hash</dt>
                <dd className="break-all font-mono text-[11px] text-slate-700">{vc.vc_hash}</dd>
              </div>
            )}
          </dl>

          <div className="mt-2 border-t border-slate-100 pt-2">
            {verify.status === "idle" && (
              <button
                onClick={runVerify}
                className="rounded bg-slate-800 px-3 py-1 text-[11px] font-medium text-white hover:bg-slate-900"
              >
                Verify signature
              </button>
            )}
            {verify.status === "loading" && (
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" strokeDasharray="50 50" /></svg>
                Verifying ES256K JWT proof against issuer DID…
              </div>
            )}
            {verify.status === "ok" && (
              <div className="rounded bg-emerald-50 p-2 text-[11px] text-emerald-800 ring-1 ring-emerald-200">
                <div className="flex items-center gap-1.5 font-medium">
                  <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-8 8a1 1 0 01-1.4 0l-4-4a1 1 0 011.4-1.4L8 12.6l7.3-7.3a1 1 0 011.4 0z" clipRule="evenodd"/></svg>
                  Verified
                </div>
                <div className="mt-1 text-emerald-700">Signature is valid. Issued by an active DID in the VeriDocs Register.</div>
              </div>
            )}
            {verify.status === "fail" && (
              <div className="rounded bg-rose-50 p-2 text-[11px] text-rose-800 ring-1 ring-rose-200">
                <div className="font-medium">Verification failed</div>
                {verify.reason && <div className="mt-1 text-rose-700">{verify.reason}</div>}
              </div>
            )}
          </div>

          <button onClick={() => { setOpen(false); setVerify({ status: "idle" }); }} className="mt-2 text-[11px] text-slate-500 hover:text-slate-700">Close</button>
        </div>
      )}
    </span>
  );
}

/* Types mirroring Pydantic schemas in src/openlegal/schemas/. Keep in sync. */

export type CaseStatus =
  | "open"
  | "triaged"
  | "in_progress"
  | "waiting_customer"
  | "waiting_third_party"
  | "resolved"
  | "closed"
  | "cancelled";

export type CasePriority = "P1" | "P2" | "P3" | "P4";

export type CaseOwnership = "own" | "not_own" | "transferred";

export interface CaseSummary {
  id: string;
  case_number: string;
  title: string;
  status: CaseStatus;
  priority: CasePriority | null;
  ownership: CaseOwnership | null;
  assigned_group_id: string | null;
  assigned_user_id: string | null;
  opened_at: string;
  sla_resolution_due_at: string | null;
  updated_at: string;
}

export interface CaseDetail extends CaseSummary {
  description: string | null;
  classification_id: string | null;
  service_tier_id: string | null;
  jira_mirror_key: string | null;
  triaged_at: string | null;
  first_response_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  sla_first_response_due_at: string | null;
  state_snapshot: Record<string, unknown>;
  created_at: string;
}

export type CaseEventType =
  | "signal_attached" | "normalized" | "classified" | "prioritized"
  | "routed" | "ownership_decided" | "assigned" | "status_changed"
  | "priority_changed" | "ai_proposal_created" | "ai_proposal_approved"
  | "ai_proposal_rejected" | "ai_proposal_applied" | "comment_added"
  | "customer_reply_sent" | "vc_issued" | "jira_synced" | "escalated"
  | "sla_warning" | "sla_breached" | "resolved" | "closed" | "reopened"
  | "uapf_capability_invoked" | "operator_override";

export type CaseEventActorType =
  | "system" | "user" | "ai" | "uapf" | "adapter" | "external";

export interface VCSummary {
  vc_id: string;
  vc_type: string;
  issuer_did: string;
  subject_did: string;
  vc_hash: string | null;
}

export interface CaseEvent {
  id: string;
  case_id: string;
  type: CaseEventType;
  actor_type: CaseEventActorType;
  actor_user_id: string | null;
  actor_label: string | null;
  trace_id: string | null;
  payload: Record<string, unknown>;
  vc_reference_id: string | null;
  vc: VCSummary | null;
  created_at: string;
}


// ── UAPF types ──

export interface UapfPackage {
  packageId: string;
  version: string;
  name?: string;
  description?: string;
  level?: number;
  runnable?: boolean;
  source_url?: string | null;
}

export interface UapfPackagesResponse {
  engine_alive: boolean;
  engine_url: string;
  packages: UapfPackage[];
}

export interface UapfDecision {
  id: string;
  name: string;
  hitPolicy?: string;
  rules?: Array<{ id: string; when?: unknown[]; then?: unknown[] }>;
}

export interface UapfPackageInfo {
  packageId: string;
  version: string;
  name: string;
  description: string;
  level: number;
  manifest: Record<string, unknown>;
  process: { id?: string; name?: string };
  decisions: UapfDecision[];
  capabilities: unknown[];
  triggers: { active: unknown[]; all: unknown[] };
}

export interface UapfSession {
  session_id: string;
  case_id: string | null;
  signal_id: string | null;
  package_id: string;
  process_id: string;
  trigger_name: string | null;
  state: string;
  started_at: string | null;
  ended_at: string | null;
}

export interface UapfSessionDetail extends UapfSession {
  input_payload: Record<string, unknown> | null;
  output_payload: Record<string, unknown> | null;
  audit_chain_engine: unknown[];
  audit_chain_persisted: Array<{
    id: string;
    type: string;
    actor_type: string;
    actor_label: string | null;
    payload: Record<string, unknown> | null;
    created_at: string | null;
    vc?: { vc_id: string; vc_type: string; issuer_did: string } | null;
  }>;
}

export interface DemoSignal {
  id: string;
  title: string;
  body: string;
  source: string;
  severity: string;
  host: string | null;
  expected: { priority: string; group: string; classification: string };
}

export interface DemoRunResponse {
  source: "live" | "replay";
  case: {
    id: string;
    case_number: string;
    title: string;
    status: string;
    priority: string | null;
    classification: string | null;
    group_slug: string | null;
  };
  timeline: Array<{
    id: string;
    type: string;
    actor_type: string;
    actor_label: string | null;
    payload: Record<string, unknown> | null;
    created_at: string | null;
    vc?: VCDetail | null;
  }>;
  vc_chain: VCDetail[];
}

export interface VCDetail {
  vc_id: string;
  vc_type: string;
  issuer_did: string;
  subject_did: string;
  vc_hash: string;
  for_event_id: string;
  for_event_type: string;
}

export interface AlgorithmCard {
  id: string;
  name?: string;
  kind?: string;
  spec?: string;
  io?: { inputs?: unknown[]; outputs?: unknown[] };
  [k: string]: unknown;
}

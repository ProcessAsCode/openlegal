/* Thin fetch wrapper for the OpenLegal backend.
 *
 * Phase 1 auth: X-Org-Slug header on every request. Phase 2 swaps for JWT.
 */

import type {
  AlgorithmCard,
  CaseDetail,
  CaseEvent,
  CaseStatus,
  CaseSummary,
  DemoRunResponse,
  DemoSignal,
  UapfPackageInfo,
  UapfPackagesResponse,
  UapfSession,
  UapfSessionDetail,
} from "./types";

const ORG_SLUG_KEY = "openlegal.org_slug";
const DEFAULT_ORG_SLUG = "demo";

export function getOrgSlug(): string {
  return localStorage.getItem(ORG_SLUG_KEY) || DEFAULT_ORG_SLUG;
}

export function setOrgSlug(slug: string): void {
  localStorage.setItem(ORG_SLUG_KEY, slug);
}


export interface ConnectionInfo {
  id: string;
  kind: string;
  name: string;
  config: Record<string, unknown>;
  has_token: boolean;
  is_enabled: boolean;
  status: string;
  last_error?: string | null;
}
export interface ConnectionsResponse { connections: ConnectionInfo[]; }

export interface OrgInfo { slug: string; name: string; }
export interface OrgsResponse { orgs: OrgInfo[]; }

export interface AgreementObligation {
  id: string; type: string; party?: string; rule?: string;
  value?: unknown; mode?: string; jira?: string;
}

export interface AgentTool {
  name: string; version: string; summary: string; reversibility: string;
}
export interface AgentStep {
  id: string; seq: number; phase: string; thought?: string | null;
  action_capability?: string | null; action_inputs?: Record<string, unknown> | null;
  observation?: unknown; guardrail_verdict?: string | null; guardrail_reason?: string | null;
  approved_at?: string | null; latency_ms?: number | null; created_at?: string | null;
}
export interface AgentMessage {
  id: string; role: string; content: string; is_interjection: boolean; created_at?: string | null;
}
export interface AgentRunSummary {
  id: string; goal: string; status: string; steps_used: number; max_steps: number;
  model_ref?: string | null; created_at?: string | null;
}
export interface AgentRunDetail extends AgentRunSummary {
  agreement_ref?: string | null;
  scratchpad: Record<string, unknown>;
  allowed_capabilities: string[];
  outcome?: { answer?: string } | null;
  halt_reason?: string | null;
  steps: AgentStep[];
  messages: AgentMessage[];
  note?: string;
}
export interface AgentRuntime {
  llm: { provider: string; model: string; endpoint: string; configured: boolean; note: string };
  store: { base_url: string; reachable: boolean; agreements: number | null; detail: string };
  agent: { max_steps: number; irreversible: string[] };
}

export interface StoreValidation { ok?: boolean | null; errors?: number; warnings?: number }
export interface StoreAgreement {
  id: number; uas_id: string; title?: string | null; agreement_type?: string | null;
  profile?: string | null; language: string; status: string;
  buyer_name?: string | null; supplier_name?: string | null;
  clause_count: number; standardization_ratio?: number | null;
  current_version: number; source: string; needs_review: boolean;
  validation: StoreValidation; created_at?: string | null; updated_at?: string | null;
}
export interface StoreFinding {
  layer: string; severity: string; message: string; rule?: string | null; location?: string | null;
}
export interface StoreAgreementDetail extends StoreAgreement {
  version: number; uas: Record<string, unknown>; summary: Record<string, unknown>;
  findings: StoreFinding[]; xml_url: string;
}
export interface StoreVersion { version: number; change_note?: string | null; created_at?: string | null }
export interface StoreProfile { name: string; title?: string }
export interface StoreClause { id: string; title?: string }
export interface StoreConfig {
  uas_versions: string[]; version: string; profiles: StoreProfile[];
  clause_library: StoreClause[]; tree?: Record<string, unknown>;
}
export interface StoreImportResult {
  mode?: string; status: string; agreement_id?: number; uas_id?: string;
  job_id?: string; error?: string; errors?: number; warnings?: number;
}

class ApiClient {
  private base: string;

  constructor(base: string = "") { this.base = base; }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const headers: Record<string, string> = { "X-Org-Slug": getOrgSlug() };
    if (body !== undefined) headers["Content-Type"] = "application/json";

    const res = await fetch(this.base + path, {
      method, headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      const detail = await res
        .json()
        .then((j) => (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)))
        .catch(() => res.statusText);
      throw new Error(`${res.status} ${detail}`);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  listIncidents(
    opts: { status?: CaseStatus[]; limit?: number; offset?: number } = {},
  ): Promise<CaseSummary[]> {
    const qs = new URLSearchParams();
    if (opts.status) opts.status.forEach((s) => qs.append("status", s));
    if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
    if (opts.offset !== undefined) qs.set("offset", String(opts.offset));
    const q = qs.toString();
    return this.request<CaseSummary[]>("GET", "/api/incidents/" + (q ? "?" + q : ""));
  }

  getIncident(caseId: string): Promise<CaseDetail> {
    return this.request<CaseDetail>("GET", `/api/incidents/${caseId}`);
  }

  listIncidentEvents(caseId: string): Promise<CaseEvent[]> {
    return this.request<CaseEvent[]>("GET", `/api/incidents/${caseId}/events`);
  }

  transitionIncident(
    caseId: string,
    toStatus: CaseStatus,
    reason?: string,
  ): Promise<CaseDetail> {
    return this.request<CaseDetail>(
      "POST",
      `/api/incidents/${caseId}/transition`,
      { to_status: toStatus, reason },
    );
  }

  postIntake(payload: {
    source: string;
    raw_payload: Record<string, unknown>;
    external_id?: string;
    dedupe_hash?: string;
  }): Promise<unknown> {
    return this.request("POST", "/api/intake/", payload);
  }

  getUapfManifest(): Promise<unknown> {
    return this.request("GET", "/uapf/host/manifest");
  }

  // ── UAPF endpoints ──
  uapfListPackages(): Promise<UapfPackagesResponse> {
    return this.request<UapfPackagesResponse>("GET", "/api/uapf/packages");
  }

  uapfPackageInfo(packageId: string): Promise<UapfPackageInfo> {
    return this.request<UapfPackageInfo>("GET", `/api/uapf/packages/${packageId}/info`);
  }

  async uapfFetchXml(path: string): Promise<string> {
    const res = await fetch(this.base + path, {
      headers: { "X-Org-Slug": getOrgSlug() },
    });
    if (!res.ok) throw new Error(`${res.status} fetching ${path}`);
    return await res.text();
  }

  uapfListSessions(limit: number = 50): Promise<UapfSession[]> {
    return this.request<UapfSession[]>("GET", `/api/uapf/sessions?limit=${limit}`);
  }

  uapfSessionDetail(sessionId: string): Promise<UapfSessionDetail> {
    return this.request<UapfSessionDetail>("GET", `/api/uapf/sessions/${encodeURIComponent(sessionId)}`);
  }

  uapfDemoSignals(): Promise<DemoSignal[]> {
    return this.request<DemoSignal[]>("GET", "/api/uapf/demo-signals");
  }

  uapfRunDemo(signalId: string): Promise<DemoRunResponse> {
    return this.request<DemoRunResponse>("POST", "/api/uapf/run-demo", { signal_id: signalId });
  }

  uapfRunFreetext(payload: {
    title: string; body: string; severity?: string; source?: string; host?: string;
  }): Promise<DemoRunResponse> {
    return this.request<DemoRunResponse>("POST", "/api/uapf/run-freetext", payload);
  }

  uapfReplayCase(caseId: string): Promise<DemoRunResponse> {
    return this.request<DemoRunResponse>("GET", `/api/uapf/replay-case/${caseId}`);
  }

  uapfAlgorithmCards(packageId: string): Promise<{ algorithms: AlgorithmCard[] }> {
    return this.request<{ algorithms: AlgorithmCard[] }>("GET", `/api/uapf/packages/${packageId}/algorithms`);
  }

  verifyVc(_caseId: string, vcId: string): Promise<{ verified: boolean; issuer_did: string; vc_type: string; raw: unknown }> {
    return this.request("GET", `/api/incidents/vc/${encodeURIComponent(vcId)}/verify`);
  }

  listConnections(): Promise<ConnectionsResponse> {
    return this.request<ConnectionsResponse>("GET", "/api/uapf/connections");
  }



  getGovernanceCalendar(weeks = 10): Promise<GovernanceCalendar> {
    return this.request("GET", `/api/legal/schedule/sittings?weeks=${weeks}`);
  }

  listAgreements(): Promise<{ agreements: AgreementSummary[] }> {
    return this.request("GET", "/api/legal/agreements");
  }

  getAgreementDetail(aid: string): Promise<AgreementDetail> {
    return this.request("GET", `/api/legal/agreements/${aid}`);
  }

  getLegalConnections(): Promise<{ connections: LegalConnection[] }> {
    return this.request("GET", "/api/legal/connections");
  }

  saveLegalConnection(kind: string, body: Record<string, unknown>): Promise<LegalConnection> {
    return this.request("PUT", `/api/legal/connections/${kind}`, body);
  }

  testLegalConnection(kind: string): Promise<LegalConnTest> {
    return this.request("POST", `/api/legal/connections/${kind}/test`);
  }

  runGovernance(start?: string): Promise<GovernanceRunReport> {
    const q = start ? `?start=${start}` : "";
    return this.request<GovernanceRunReport>("POST", `/api/legal/run-governance${q}`);
  }

  getGovernanceAlerts(limit = 100): Promise<{ alerts: GovernanceAlert[] }> {
    return this.request<{ alerts: GovernanceAlert[] }>("GET", `/api/legal/alerts?limit=${limit}`);
  }


  agentTools(): Promise<{ tools: AgentTool[]; policy: Record<string, unknown> }> {
    return this.request("GET", "/api/agent/tools");
  }

  agentRuntime(): Promise<AgentRuntime> {
    return this.request("GET", "/api/agent/runtime");
  }

  agentListRuns(limit = 50): Promise<{ runs: AgentRunSummary[] }> {
    return this.request("GET", `/api/agent/runs?limit=${limit}`);
  }

  agentGetRun(runId: string): Promise<AgentRunDetail> {
    return this.request("GET", `/api/agent/runs/${runId}`);
  }

  agentChat(body: { message: string; run_id?: string; agreement_ref?: string }): Promise<AgentRunDetail> {
    return this.request("POST", "/api/agent/chat", body);
  }

  agentApprove(runId: string): Promise<AgentRunDetail> {
    return this.request("POST", `/api/agent/runs/${runId}/approve`);
  }

  agentReject(runId: string, reason: string): Promise<AgentRunDetail> {
    return this.request("POST", `/api/agent/runs/${runId}/reject`, { reason });
  }

  storeListAgreements(status?: string): Promise<{ count: number; agreements: StoreAgreement[] }> {
    return this.request("GET", `/api/store/agreements${status ? `?status=${status}` : ""}`);
  }

  storeGetAgreement(id: number, version?: number): Promise<StoreAgreementDetail> {
    return this.request("GET", `/api/store/agreements/${id}${version ? `?version=${version}` : ""}`);
  }

  storeVersions(id: number): Promise<{ current_version: number; versions: StoreVersion[] }> {
    return this.request("GET", `/api/store/agreements/${id}/versions`);
  }

  async storeXml(id: number, version: number): Promise<string> {
    const r = await fetch(`/api/store/agreements/${id}/v${version}/xml`, {
      headers: { "X-Org-Slug": getOrgSlug() },
    });
    if (!r.ok) throw new Error(`XML ${r.status}`);
    return r.text();
  }

  storeConfig(): Promise<StoreConfig> {
    return this.request("GET", "/api/store/config");
  }

  storePreview(data: unknown): Promise<{ ok: boolean; xml: string; findings: StoreFinding[]; errors: number; warnings: number }> {
    return this.request("POST", "/api/store/agreements/preview", { data });
  }

  storeSave(body: { agreement_id?: number; data?: unknown; xml?: string; change_note?: string }): Promise<{ agreement_id: number; uas_id: string; version: number }> {
    return this.request("POST", "/api/store/agreements", body);
  }

  async storeImport(body: { file: File | null; text: string; profile: string }): Promise<StoreImportResult> {
    const fd = new FormData();
    if (body.file) fd.append("file", body.file);
    fd.append("text", body.text);
    fd.append("profile", body.profile);
    const r = await fetch("/api/store/agreements/import", {
      method: "POST", headers: { "X-Org-Slug": getOrgSlug() }, body: fd,
    });
    if (!r.ok) throw new Error((await r.text()).slice(0, 300));
    return r.json();
  }

  storeImportStatus(jobId: string): Promise<StoreImportResult> {
    return this.request("GET", `/api/store/agreements/import/${jobId}`);
  }

  listOrgs(): Promise<OrgsResponse> {
    return this.request<OrgsResponse>("GET", "/api/uapf/orgs");
  }

}

export const api = new ApiClient();


/* --- Governance (OpenLegal) --- */
export interface ChainMilestone {
  body: string; label: string; kind: string;
  ready_by: string; submission_deadline: string | null; date: string;
}
export interface ChainPlan {
  deadline: string; approvals: string[]; feasible: boolean;
  completion: string | null; slack_days: number | null; reason: string;
  milestones: ChainMilestone[];
}
export interface GovernanceFinding {
  obligation: string; obligation_type: string; state: string; action: string;
  severity: string; message: string; schedule?: ChainPlan; alert_id?: string;
}
export interface GovernanceContractReport {
  contract: string; title: string; docus_id: string; findings: GovernanceFinding[];
}
export interface GovernanceRunReport {
  run_at: string; org: string; as_of: string; run_id: string;
  alerts_created: number; contracts: GovernanceContractReport[];
}
export interface GovernanceAlert {
  id: string; at: string; org: string | null; severity: string;
  contract: string | null; obligation: string | null; state: string | null;
  action: string | null; message: string | null; detail?: ChainPlan | null;
}


/* --- Agreement Register + legal connectors --- */
export interface AgreementSummary {
  agreement_id: string; title: string; status: string;
  value_eur: number | null; expires: string | null;
  source_docus_id: string | null; source_sap_id: string | null;
  obligations: number; updated_at: string | null;
}
export interface AgreementDetail extends AgreementSummary {
  uas: Record<string, unknown>;
}
export interface LegalConnection {
  id: string; kind: string; name: string;
  config: Record<string, unknown>; is_enabled: boolean; status: string;
}
export interface LegalConnTest {
  ok: boolean; adapter: string; records: number | null; error: string | null;
}

export interface CalendarBody {
  body: string; label: string; kind: string; prerequisite?: string | null;
  cadence?: string; pattern?: string; submission_cutoff_working_days?: number;
  lead_working_days?: number; lead_calendar_days?: number;
}
export interface CalendarSitting {
  body: string; label: string; date: string; submit_by: string;
}
export interface GovernanceCalendar {
  as_of: string; weeks: number; bodies: CalendarBody[]; sittings: CalendarSitting[];
}

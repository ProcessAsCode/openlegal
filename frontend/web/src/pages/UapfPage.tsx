/**
 * UAPF section — admin & demo for the `lv.itsm.incident.triage` package.
 *
 * Layout mirrors OpenDMS UapfPage: a tab bar (Demo / Packages / Sessions /
 * Engine) sitting under a section header. The Demo tab has three inner
 * modes — Curated signals / Free-text / Replay existing — that all share
 * the same BPMN visualisation + signed audit chain side panel.
 *
 * BPMN/DMN rendering uses bpmn-js/dmn-js (the same components OpenDMS ships).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type {} from "../api/client";
import type {
  DemoRunResponse,
  DemoSignal,
  UapfPackage,
  UapfPackageInfo,
  UapfSession,
  UapfSessionDetail,
  VCDetail,
} from "../api/types";
import BpmnDiagram from "../components/BpmnDiagram";
import DmnTableView from "../components/DmnTableView";
import SystemTab from "./SystemTab";

const PACKAGE_ID = "lv.itsm.incident.triage";
const PROCESS_ID = "incident-triage";

// BPMN step list — names mirror the .bpmn ids so live highlighting works
// even before the engine returns parsed packageInfo.
const PROCESS_STEPS = [
  { id: "Event_Start",          label: "Signāls saņemts",            kind: "event"   },
  { id: "Task_NormalizeSignal", label: "Signāla normalizācija",      kind: "service", op: "intake.normalize" },
  { id: "Task_ClassifyIncident",label: "Incidenta klasifikācija",    kind: "service", op: "ai.classify" },
  { id: "Task_SuggestPriority", label: "AI prioritātes ieteikums",   kind: "service", op: "ai.suggest-priority" },
  { id: "Task_EvaluatePriorityDmn", label: "DMN: prioritātes lēmums",kind: "rule",    op: "DMN" },
  { id: "Task_EvaluateOwnershipDmn",label: "DMN: īpašumtiesības",    kind: "rule",    op: "DMN" },
  { id: "Task_EvaluateRoutingDmn",  label: "DMN: maršrutēšana",     kind: "rule",    op: "DMN" },
  { id: "Task_UpdateIncident",  label: "Incidenta atjaunināšana",    kind: "service", op: "incident.update" },
  { id: "Task_DraftResponse",   label: "AI atbildes melnraksts",     kind: "service", op: "ai.draft-response" },
  { id: "Task_EmitEvent",       label: "Notikuma publicēšana",       kind: "service", op: "event.emit" },
  { id: "Event_End",            label: "Klasifikācija pabeigta",     kind: "event" },
];

const PRIORITY_BADGE: Record<string, string> = {
  P1: "bg-red-100 text-red-700 border-red-200",
  P2: "bg-orange-100 text-orange-700 border-orange-200",
  P3: "bg-emerald-100 text-emerald-700 border-emerald-200",
  P4: "bg-gray-100 text-gray-600 border-gray-200",
};

const VC_TYPE_BADGE: Record<string, string> = {
  IncidentOpened:      "bg-blue-100 text-blue-800 border-blue-300",
  IncidentClassified:  "bg-violet-100 text-violet-800 border-violet-300",
  IncidentPrioritized: "bg-amber-100 text-amber-800 border-amber-300",
  IncidentRouted:      "bg-emerald-100 text-emerald-800 border-emerald-300",
};

// Reserved for inline-on-diagram VC shield overlay (Phase 2).
// const EVENT_TO_STEP_ID: Record<string, string> = {
//   signal_attached:    "Task_NormalizeSignal",
//   status_changed:     "Event_Start",
//   classification_set: "Task_ClassifyIncident",
//   priority_set:       "Task_EvaluatePriorityDmn",
//   group_assigned:     "Task_EvaluateRoutingDmn",
//   response_drafted:   "Task_DraftResponse",
// };

// ─────────────────────────────────────────────────────────────────────

export default function UapfPage() {
  const { tab: tabParam } = useParams<{ tab?: string }>();
  const navigate = useNavigate();
  const TABS = ["system", "demo", "packages", "sessions", "engine"];
  const tab = TABS.includes(tabParam || "") ? tabParam! : "system";

  return (
    <div>
      <header className="mb-4">
        <h1 className="text-2xl font-bold text-slate-900">UAPF</h1>
        <p className="text-sm text-slate-500 mt-1">
          Algoritmizēta incidentu triāža — <code className="text-xs">lv.itsm.incident.triage</code> v1.0.0
        </p>
      </header>

      <div className="border-b border-slate-200 mb-5">
        <nav className="flex gap-1">
          {[
            { id: "system",   label: "System",          icon: "🗺" },
            { id: "demo",     label: "Demo console",   icon: "▶" },
            { id: "packages", label: "Packages",        icon: "📦" },
            { id: "sessions", label: "Sessions",        icon: "📜" },
            { id: "engine",   label: "Engine",          icon: "⚙" },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => navigate(`/uapf/${t.id}`)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
                tab === t.id
                  ? "border-accent-600 text-accent-700"
                  : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
              }`}
            >
              <span className="mr-1.5">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {tab === "system"   && <SystemTab />}
      {tab === "demo"     && <DemoTab />}
      {tab === "packages" && <PackagesTab />}
      {tab === "sessions" && <SessionsTab />}
      {tab === "engine"   && <EngineTab />}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
// DEMO TAB — three modes (curated / free-text / replay)
// ═════════════════════════════════════════════════════════════════════

function DemoTab() {
  const [mode, setMode] = useState<"curated" | "freetext" | "replay">("curated");
  const [packageInfo, setPackageInfo] = useState<UapfPackageInfo | null>(null);
  const [bpmnXml, setBpmnXml] = useState<string | null>(null);
  const [dmnXmls, setDmnXmls] = useState<Record<string, string>>({});

  // Live run state
  const [running, setRunning] = useState(false);
  const [activeStepId, setActiveStepId] = useState<string | null>(null);
  const [completedStepIds, setCompletedStepIds] = useState<string[]>([]);
  const [runResult, setRunResult] = useState<DemoRunResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const animateTimer = useRef<number | null>(null);

  // Load package metadata + BPMN/DMN once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const info = await api.uapfPackageInfo(PACKAGE_ID);
        if (cancelled) return;
        setPackageInfo(info);
        const procId = info.process?.id || PROCESS_ID;
        try {
          const bpmn = await api.uapfFetchXml(`/api/uapf/packages/${PACKAGE_ID}/bpmn/${procId}.xml`);
          if (!cancelled) setBpmnXml(bpmn);
        } catch (e) { console.warn("BPMN load failed:", e); }
        const xmls: Record<string, string> = {};
        for (const d of info.decisions || []) {
          try {
            xmls[d.id] = await api.uapfFetchXml(`/api/uapf/packages/${PACKAGE_ID}/dmn/${d.id}.xml`);
          } catch { /* skip */ }
        }
        if (!cancelled) setDmnXmls(xmls);
      } catch (e) {
        console.warn("Package info load failed:", e);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => () => {
    if (animateTimer.current) window.clearTimeout(animateTimer.current);
  }, []);

  const resetRun = useCallback(() => {
    if (animateTimer.current) window.clearTimeout(animateTimer.current);
    setRunning(false);
    setActiveStepId(null);
    setCompletedStepIds([]);
    setRunResult(null);
    setRunError(null);
  }, []);

  const playback = useCallback((result: DemoRunResponse) => {
    // Animate the BPMN step progression at 500ms/step for stage readability.
    // Real exec already happened server-side; this is the visual replay.
    let i = 0;
    const completed: string[] = [];
    setActiveStepId(PROCESS_STEPS[0].id);
    const tick = () => {
      i += 1;
      if (i < PROCESS_STEPS.length) {
        const prev = PROCESS_STEPS[i - 1];
        if (prev?.id) completed.push(prev.id);
        setCompletedStepIds([...completed]);
        setActiveStepId(PROCESS_STEPS[i].id);
        animateTimer.current = window.setTimeout(tick, 500);
      } else {
        setCompletedStepIds(PROCESS_STEPS.map((s) => s.id));
        setActiveStepId(null);
        setRunning(false);
        setRunResult(result);
      }
    };
    animateTimer.current = window.setTimeout(tick, 500);
  }, []);

  const runCurated = useCallback(async (signal: DemoSignal) => {
    resetRun();
    setRunning(true);
    try {
      const result = await api.uapfRunDemo(signal.id);
      // Hold the result until animation finishes (so result card pops at the end)
      playback(result);
    } catch (e) {
      setRunError((e as Error).message);
      setRunning(false);
    }
  }, [resetRun, playback]);

  const runFreetext = useCallback(async (payload: {
    title: string; body: string; severity: string; source: string; host?: string;
  }) => {
    resetRun();
    setRunning(true);
    try {
      const result = await api.uapfRunFreetext(payload);
      playback(result);
    } catch (e) {
      setRunError((e as Error).message);
      setRunning(false);
    }
  }, [resetRun, playback]);

  const runReplay = useCallback(async (caseId: string) => {
    resetRun();
    setRunning(true);
    try {
      const result = await api.uapfReplayCase(caseId);
      playback(result);
    } catch (e) {
      setRunError((e as Error).message);
      setRunning(false);
    }
  }, [resetRun, playback]);

  return (
    <div className="grid grid-cols-12 gap-4">
      {/* LEFT: trigger picker (mode + content depending on mode) */}
      <div className="col-span-4 space-y-3">
        <div className="inline-flex rounded border border-slate-200 bg-white p-0.5">
          {[
            { id: "curated", label: "Curated" },
            { id: "freetext", label: "Free-text" },
            { id: "replay",  label: "Replay" },
          ].map((m) => (
            <button
              key={m.id}
              onClick={() => setMode(m.id as typeof mode)}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                mode === m.id
                  ? "bg-accent-600 text-white"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {mode === "curated" && (
          <CuratedSignalPicker onRun={runCurated} running={running} />
        )}
        {mode === "freetext" && (
          <FreetextSignalForm onRun={runFreetext} running={running} />
        )}
        {mode === "replay" && (
          <ReplayCasePicker onRun={runReplay} running={running} />
        )}
      </div>

      {/* RIGHT: BPMN + result + audit chain side panel */}
      <div className="col-span-8 space-y-4">
        {packageInfo && <ProcessInfoCard info={packageInfo} />}

        {!running && !runResult && !runError && (
          <div className="rounded border border-dashed border-slate-300 bg-white p-8 text-center text-slate-400">
            Select a signal on the left to start a demo run.
          </div>
        )}

        {runError && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            Kļūda: {runError}
          </div>
        )}

        {(running || runResult) && (
          <div className="grid grid-cols-3 gap-3">
            {/* BPMN diagram — spans 2 cols */}
            <div className="col-span-2 bg-white rounded border border-slate-200 p-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-semibold text-sm text-slate-700">BPMN execution</h4>
                {!running && (
                  <button onClick={resetRun}
                    className="text-xs text-slate-500 hover:text-slate-700">
                    ↺ Reset
                  </button>
                )}
              </div>
              {bpmnXml ? (
                <BpmnDiagram
                  xml={bpmnXml}
                  activeStepId={activeStepId}
                  completedStepIds={completedStepIds}
                  height={420}
                />
              ) : (
                <FlowFallback activeStepId={activeStepId} completedStepIds={completedStepIds} />
              )}
            </div>

            {/* Side panel — signed audit chain */}
            <SignedAuditChainPanel
              chain={runResult?.vc_chain || []}
              caseId={runResult?.case?.id || null}
              running={running}
            />
          </div>
        )}

        {/* Result card (post-run) */}
        {runResult && !running && <ClassificationResultCard result={runResult} />}

        {/* DMN tables (collapsible, expanded if a run completed) */}
        {runResult && !running && packageInfo && packageInfo.decisions.length > 0 && (
          <DmnDecisionsPanel
            decisions={packageInfo.decisions}
            xmls={dmnXmls}
            result={runResult}
          />
        )}
      </div>
    </div>
  );
}

// ── curated signal picker ────────────────────────────────────────────

function CuratedSignalPicker({
  onRun, running,
}: { onRun: (s: DemoSignal) => void; running: boolean }) {
  const [signals, setSignals] = useState<DemoSignal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.uapfDemoSignals()
      .then(setSignals)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-sm text-slate-400">Loading…</div>;
  if (!signals.length) return <div className="text-sm text-slate-500">No curated signals</div>;

  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">
        Six curated sample signals. Each click POSTs a fresh signal, runs
        full triage live, and animates the BPMN flow.
      </p>
      <div className="space-y-1.5 max-h-[600px] overflow-y-auto">
        {signals.map((s) => (
          <button
            key={s.id}
            onClick={() => onRun(s)}
            disabled={running}
            className="w-full text-left rounded border border-slate-200 bg-white p-3 hover:border-accent-400 hover:bg-accent-50 disabled:opacity-50"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="font-medium text-sm text-slate-900">{s.title}</div>
              <span className="text-[10px] uppercase tracking-wide text-slate-400 font-mono shrink-0">
                {s.source} · {s.severity}
              </span>
            </div>
            <div className="mt-1 text-xs text-slate-500 line-clamp-2">{s.body}</div>
            <div className="mt-1.5 flex gap-1.5 text-[10px]">
              <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
                expect: {s.expected.priority}
              </span>
              <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
                {s.expected.group}
              </span>
              <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
                {s.expected.classification}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── free-text form ───────────────────────────────────────────────────

function FreetextSignalForm({
  onRun, running,
}: { onRun: (p: { title: string; body: string; severity: string; source: string; host?: string }) => void; running: boolean }) {
  const [title, setTitle] = useState("");
  const [body, setBody]   = useState("");
  const [severity, setSeverity] = useState("medium");
  const [source, setSource]     = useState("manual");
  const [host, setHost]         = useState("");

  return (
    <div className="space-y-2 bg-white rounded border border-slate-200 p-3">
      <p className="text-xs text-slate-500">
        Type your own signal description; OpenLegal creates a new case, runs the
        same triage pipeline live, and shows the result.
      </p>
      <input
        className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
        placeholder="Signal title (e.g. BGP flap rtr-core-04)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="w-full rounded border border-slate-300 px-2 py-1 text-sm h-24"
        placeholder="Body / description"
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      <div className="grid grid-cols-2 gap-2">
        <select className="rounded border border-slate-300 px-2 py-1 text-sm" value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="manual">manual</option>
          <option value="zabbix">zabbix</option>
          <option value="email">email</option>
        </select>
        <select className="rounded border border-slate-300 px-2 py-1 text-sm" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
      </div>
      <input
        className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
        placeholder="Host (optional)"
        value={host}
        onChange={(e) => setHost(e.target.value)}
      />
      <button
        onClick={() => onRun({ title, body, severity, source, host: host || undefined })}
        disabled={running || !title.trim() || !body.trim()}
        className="w-full rounded bg-accent-600 px-3 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-50"
      >
        {running ? "Running…" : "▶ Run triage"}
      </button>
    </div>
  );
}

// ── replay existing case picker ─────────────────────────────────────

function ReplayCasePicker({
  onRun, running,
}: { onRun: (caseId: string) => void; running: boolean }) {
  const [cases, setCases] = useState<Array<{ id: string; case_number: string; title: string; priority: string | null }>>([]);

  useEffect(() => {
    api.listIncidents({ limit: 30 }).then((cs) => {
      const items: Array<{ id: string; case_number: string; title: string; priority: string | null }> =
        cs.map((c) => ({ id: c.id, case_number: c.case_number, title: c.title, priority: c.priority as string | null }));
      setCases(items);
    }).catch(() => {});
  }, []);

  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">
        Re-animate the persisted audit chain of any existing case. No new VCs are
        minted — this plays back what was already signed.
      </p>
      <div className="space-y-1 max-h-[600px] overflow-y-auto">
        {cases.map((c) => (
          <button
            key={c.id}
            onClick={() => onRun(c.id)}
            disabled={running}
            className="w-full text-left rounded border border-slate-200 bg-white p-2 hover:border-accent-400 hover:bg-accent-50 disabled:opacity-50"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="font-medium text-sm text-slate-900 line-clamp-1">{c.title}</div>
              <span className="text-[10px] text-slate-400 font-mono">{c.case_number}</span>
            </div>
            {c.priority && (
              <span className={`mt-1 inline-block text-[10px] px-1.5 py-0.5 rounded font-mono ${PRIORITY_BADGE[c.priority] || "bg-slate-100"}`}>
                {c.priority}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── side panel: signed audit chain ───────────────────────────────────

function SignedAuditChainPanel({
  chain, caseId, running,
}: { chain: VCDetail[]; caseId: string | null; running: boolean }) {
  return (
    <div className="bg-gradient-to-b from-emerald-50/40 to-white rounded border border-emerald-200 p-3">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-semibold text-sm text-emerald-900">Signed audit chain</h4>
        <span className="text-[10px] text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">
          {chain.length} VC{chain.length === 1 ? "" : "s"}
        </span>
      </div>
      {running && (
        <div className="text-xs text-slate-400 italic">
          Signing as steps complete…
        </div>
      )}
      {!running && chain.length === 0 && (
        <div className="text-xs text-slate-400 italic">No VCs yet.</div>
      )}
      <ul className="space-y-2 max-h-[380px] overflow-y-auto">
        {chain.map((vc) => (
          <VcRow key={vc.vc_id} vc={vc} caseId={caseId} />
        ))}
      </ul>
    </div>
  );
}

function VcRow({ vc, caseId }: { vc: VCDetail; caseId: string | null }) {
  const [state, setState] = useState<"idle" | "checking" | "ok" | "fail">("idle");
  const [error, setError] = useState<string | null>(null);

  const verify = async () => {
    if (!caseId) return;
    setState("checking");
    setError(null);
    try {
      const r = await api.verifyVc(caseId, vc.vc_id);
      setState(r.verified ? "ok" : "fail");
      if (!r.verified) setError("Signature did not verify");
    } catch (e) {
      setState("fail");
      setError((e as Error).message);
    }
  };

  const typeBadge = VC_TYPE_BADGE[vc.vc_type] || "bg-slate-100 text-slate-700 border-slate-200";

  return (
    <li className="text-xs bg-white border border-slate-200 rounded p-2 space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className={`px-1.5 py-0.5 rounded border font-medium ${typeBadge}`}>
          🛡 {vc.vc_type}
        </span>
        <button
          onClick={verify}
          className="text-[10px] text-emerald-700 hover:text-emerald-900 underline"
        >
          {state === "idle" && "Verify"}
          {state === "checking" && "Verifying…"}
          {state === "ok" && "✓ Verified"}
          {state === "fail" && "✕ Failed"}
        </button>
      </div>
      <div className="font-mono text-[10px] text-slate-500 break-all">
        Issuer: {vc.issuer_did.replace("did:web:register.opendms.dev:org:", "did:…:")}
      </div>
      <div className="font-mono text-[10px] text-slate-400 truncate" title={vc.vc_id}>
        {vc.vc_id.replace("did:web:register.opendms.dev:doc:", "doc:…:")}
      </div>
      {state === "ok" && (
        <div className="text-[10px] text-emerald-700">ES256K JWT signature valid · DID resolved via Register</div>
      )}
      {state === "fail" && error && (
        <div className="text-[10px] text-red-600">{error}</div>
      )}
    </li>
  );
}

// ── classification result card ───────────────────────────────────────

function ClassificationResultCard({ result }: { result: DemoRunResponse }) {
  const c = result.case;
  return (
    <div className="bg-gradient-to-br from-emerald-50 to-white rounded border-2 border-emerald-300 p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="font-semibold text-emerald-900">Triage result</h4>
          <div className="text-xs text-slate-500 font-mono mt-0.5">{c.case_number}</div>
        </div>
        <span className="text-xs text-slate-500">
          {result.source === "live" ? "Live run" : "Replayed from postgres"}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Priority</div>
          <span className={`mt-0.5 inline-block px-2 py-0.5 rounded font-semibold border ${PRIORITY_BADGE[c.priority || ""] || "bg-slate-100"}`}>
            {c.priority || "—"}
          </span>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Classification</div>
          <div className="text-sm font-mono text-slate-700 mt-0.5">{c.classification || "—"}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Routed to</div>
          <div className="text-sm font-mono text-slate-700 mt-0.5">{c.group_slug || "—"}</div>
        </div>
        <div className="col-span-3 pt-2 border-t border-emerald-200">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Title</div>
          <div className="text-sm text-slate-800 mt-0.5">{c.title}</div>
        </div>
      </div>
    </div>
  );
}

// ── process info card (header) ───────────────────────────────────────

function ProcessInfoCard({ info }: { info: UapfPackageInfo }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3 flex items-start gap-4">
      <div className="text-3xl">📦</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-sm text-slate-800">{info.name}</span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
            {info.packageId}@{info.version}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 text-violet-800 border border-violet-200">
            Level {info.level}
          </span>
        </div>
        {info.description && (
          <p className="mt-1 text-xs text-slate-500 line-clamp-2">{info.description}</p>
        )}
        <div className="mt-1.5 flex gap-3 text-[11px] text-slate-500">
          <span>BPMN: <code>{info.process.id || "?"}</code></span>
          <span>{info.decisions.length} DMN decisions</span>
        </div>
      </div>
    </div>
  );
}

// ── BPMN fallback (when XML didn't load) ────────────────────────────

function FlowFallback({
  activeStepId, completedStepIds,
}: { activeStepId: string | null; completedStepIds: string[] }) {
  const completed = new Set(completedStepIds);
  return (
    <ol className="space-y-1.5">
      {PROCESS_STEPS.map((s, i) => {
        const isDone   = completed.has(s.id);
        const isActive = activeStepId === s.id;
        const dotCls = isDone
          ? "bg-emerald-500 border-emerald-500 text-white"
          : isActive
            ? "bg-amber-100 border-amber-500 text-amber-700 animate-pulse"
            : "bg-white border-slate-300 text-slate-300";
        return (
          <li key={s.id} className="flex items-center gap-3 text-sm">
            <span className={`w-7 h-7 rounded-full border-2 flex items-center justify-center text-xs font-semibold flex-shrink-0 ${dotCls}`}>
              {isDone ? "✓" : i + 1}
            </span>
            <span className={`font-medium ${(isActive || isDone) ? "text-slate-900" : "text-slate-400"}`}>
              {s.label}
            </span>
            {s.op && (
              <span className="ml-auto text-xs font-mono text-slate-500">{s.op}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

// ── DMN tables panel (post-run, collapsible) ────────────────────────

function DmnDecisionsPanel({
  decisions, xmls, result,
}: {
  decisions: UapfPackageInfo["decisions"];
  xmls: Record<string, string>;
  result: DemoRunResponse;
}) {
  const [open, setOpen] = useState(true);

  // Derive fired rules by output value (best-effort)
  const firedByDecision: Record<string, string | null> = {};
  for (const d of decisions) {
    let firedRule: string | null = null;
    // Heuristic match on case fields
    if (d.id.includes("priority") && result.case.priority) firedRule = result.case.priority;
    else if (d.id.includes("routing") && result.case.group_slug) firedRule = result.case.group_slug;
    else if (d.id.includes("ownership") && result.case.group_slug) firedRule = result.case.group_slug;
    firedByDecision[d.id] = firedRule;
  }

  return (
    <div className="bg-white rounded border border-slate-200">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between p-3 hover:bg-slate-50"
      >
        <div className="text-left">
          <h4 className="font-semibold text-sm text-slate-800">
            DMN decision logic ({decisions.length} tables)
          </h4>
          <p className="text-xs text-slate-500 mt-0.5">
            The exact ranked rules the engine evaluated. These live in the .uapf
            package; ProcessGit edits change behaviour on next sync.
          </p>
        </div>
        <span className="text-slate-400 text-sm">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="border-t border-slate-200 p-3 space-y-4">
          {decisions.map((d) => {
            const xml = xmls[d.id];
            return (
              <div key={d.id}>
                <div className="flex items-baseline gap-2 mb-1">
                  <h5 className="font-medium text-sm text-slate-800">{d.name}</h5>
                  <span className="text-[10px] text-slate-400 font-mono">{d.id}</span>
                  {firedByDecision[d.id] && (
                    <span className="text-[10px] text-amber-700 ml-auto">
                      Fired output: <span className="font-mono font-semibold">{firedByDecision[d.id]}</span>
                    </span>
                  )}
                </div>
                {xml
                  ? <DmnTableView xml={xml} firedRuleId={firedByDecision[d.id] || undefined} />
                  : <div className="text-xs text-slate-400 italic">DMN XML not loaded</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
// PACKAGES TAB
// ═════════════════════════════════════════════════════════════════════

function PackagesTab() {
  const [data, setData] = useState<{ engine_alive: boolean; engine_url: string; packages: UapfPackage[] } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.uapfListPackages()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-sm text-slate-400">Loading…</div>;
  if (!data) return <div className="text-sm text-red-600">Failed to load packages</div>;

  return (
    <div className="space-y-3">
      <div className="bg-white rounded border border-slate-200 p-3 text-xs">
        Engine: {data.engine_alive
          ? <span className="text-emerald-700 font-medium">alive</span>
          : <span className="text-red-700 font-medium">unreachable</span>}
        <span className="text-slate-400 font-mono ml-2">{data.engine_url}</span>
      </div>
      {data.packages.map((p) => (
        <div key={p.packageId} className="bg-white rounded border border-slate-200 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-900">{p.name || p.packageId}</span>
                <span className="text-xs font-mono text-slate-500">{p.packageId}@{p.version}</span>
              </div>
              {p.description && (
                <p className="text-xs text-slate-500 mt-1 line-clamp-3">{p.description}</p>
              )}
            </div>
            <div className="flex flex-col items-end text-xs text-slate-500 gap-1">
              {p.level && <span>Level {p.level}</span>}
              {p.runnable !== undefined && (
                <span className={p.runnable ? "text-emerald-700" : "text-slate-400"}>
                  {p.runnable ? "runnable" : "not runnable"}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
// SESSIONS TAB
// ═════════════════════════════════════════════════════════════════════

function SessionsTab() {
  const [sessions, setSessions] = useState<UapfSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, UapfSessionDetail>>({});

  const load = useCallback(() => {
    setLoading(true);
    api.uapfListSessions(50)
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = async (sid: string) => {
    if (expanded === sid) { setExpanded(null); return; }
    setExpanded(sid);
    if (!detail[sid]) {
      try {
        const d = await api.uapfSessionDetail(sid);
        setDetail((prev) => ({ ...prev, [sid]: d }));
      } catch (e) { /* skip */ }
    }
  };

  if (loading) return <div className="text-sm text-slate-400">Loading…</div>;
  if (!sessions.length) {
    return (
      <div className="text-sm text-slate-500 bg-slate-50 border border-dashed border-slate-300 rounded p-4">
        No UAPF sessions yet. Open the Demo console and run a triage.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          Persistent log of every UAPF engine execution. Click a row for the audit chain.
        </p>
        <button onClick={load} className="text-sm text-accent-700 hover:text-accent-900">↻ Reload</button>
      </div>
      <div className="bg-white rounded border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-3 py-2">Started</th>
              <th className="px-3 py-2">Package / process</th>
              <th className="px-3 py-2">Trigger</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Session ID</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <SessionRow
                key={s.session_id}
                session={s}
                expanded={expanded === s.session_id}
                onToggle={() => toggle(s.session_id)}
                detail={detail[s.session_id]}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SessionRow({
  session, expanded, onToggle, detail,
}: {
  session: UapfSession;
  expanded: boolean;
  onToggle: () => void;
  detail: UapfSessionDetail | undefined;
}) {
  const stateBadge: Record<string, string> = {
    completed: "bg-emerald-100 text-emerald-700",
    starting:  "bg-blue-100 text-blue-700",
    active:    "bg-blue-100 text-blue-700",
    failed:    "bg-red-100 text-red-700",
  };
  return (
    <>
      <tr onClick={onToggle} className="border-t border-slate-100 cursor-pointer hover:bg-slate-50">
        <td className="px-3 py-2 text-xs text-slate-600">
          {session.started_at ? new Date(session.started_at).toLocaleString("lv-LV") : "—"}
        </td>
        <td className="px-3 py-2">
          <div className="font-mono text-xs">{session.package_id}</div>
          <div className="font-mono text-xs text-slate-500">{session.process_id}</div>
        </td>
        <td className="px-3 py-2 text-xs">{session.trigger_name || "—"}</td>
        <td className="px-3 py-2">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${stateBadge[session.state] || "bg-slate-100"}`}>
            {session.state}
          </span>
        </td>
        <td className="px-3 py-2 text-right text-[10px] font-mono text-slate-400">{session.session_id}</td>
      </tr>
      {expanded && detail && (
        <tr><td colSpan={5} className="bg-slate-50 px-4 py-3 border-t border-slate-100">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs font-semibold text-slate-700 mb-1">Persisted timeline</div>
              <ol className="space-y-1 max-h-64 overflow-y-auto">
                {detail.audit_chain_persisted.map((e) => (
                  <li key={e.id} className="text-xs flex items-start gap-2 bg-white border border-slate-200 rounded p-1.5">
                    <span className="text-slate-400 font-mono shrink-0">
                      {e.created_at ? new Date(e.created_at).toLocaleTimeString("lv-LV") : ""}
                    </span>
                    <span className="font-mono text-emerald-700">{e.type}</span>
                    {e.vc && <span className="ml-auto text-[10px] text-emerald-700">🛡 VC</span>}
                  </li>
                ))}
                {detail.audit_chain_persisted.length === 0 && (
                  <li className="text-xs text-slate-400 italic">No persisted events</li>
                )}
              </ol>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-700 mb-1">Output payload</div>
              <pre className="text-xs bg-white border border-slate-200 rounded p-2 overflow-x-auto max-h-64">
                {JSON.stringify(detail.output_payload || {}, null, 2)}
              </pre>
            </div>
          </div>
        </td></tr>
      )}
    </>
  );
}

// ═════════════════════════════════════════════════════════════════════
// ENGINE TAB — health/status
// ═════════════════════════════════════════════════════════════════════

function EngineTab() {
  const [data, setData] = useState<{ engine_alive: boolean; engine_url: string; packages: UapfPackage[] } | null>(null);

  useEffect(() => {
    api.uapfListPackages().then(setData).catch(() => {});
  }, []);

  return (
    <div className="space-y-3">
      <div className="bg-white rounded border border-slate-200 p-4">
        <h4 className="font-semibold text-sm mb-2">UAPF engine</h4>
        {data ? (
          <dl className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <dt className="text-slate-500 uppercase tracking-wide">Status</dt>
              <dd className={data.engine_alive ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                {data.engine_alive ? "alive" : "unreachable"}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500 uppercase tracking-wide">URL</dt>
              <dd className="font-mono">{data.engine_url}</dd>
            </div>
            <div>
              <dt className="text-slate-500 uppercase tracking-wide">Packages loaded</dt>
              <dd>{data.packages.length}</dd>
            </div>
          </dl>
        ) : (
          <div className="text-sm text-slate-400">Loading…</div>
        )}
      </div>
      <div className="bg-white rounded border border-slate-200 p-4 text-xs space-y-1">
        <h4 className="font-semibold text-sm mb-2">Host bridge endpoints</h4>
        <div>OpenLegal exposes these for the engine to call back:</div>
        <ul className="ml-4 mt-1 list-disc space-y-0.5 text-slate-600">
          <li><code>GET  /uapf/host/manifest</code> — declared capabilities</li>
          <li><code>POST /uapf/host/capability/&#123;ns&#125;/&#123;op&#125;</code> — execute a capability</li>
          <li><code>POST /uapf/host/audit</code> — engine audit-chain submission</li>
        </ul>
      </div>
    </div>
  );
}

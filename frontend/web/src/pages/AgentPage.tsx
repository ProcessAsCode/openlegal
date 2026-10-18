import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AgentRunDetail, AgentRunSummary, AgentStep, AgentTool } from "../api/client";

/* Līgumu pārvaldības aģents — the oversight surface.
 *
 * Three things this screen has to make obvious to a lawyer and to a
 * supervisor: what the agent decided and why, where a human had to step in,
 * and that nothing irreversible happened without that step. */

export default function AgentPage() {
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [current, setCurrent] = useState<AgentRunDetail | null>(null);
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  async function refreshRuns() {
    try { setRuns((await api.agentListRuns()).runs); } catch (e) { setError(msg(e)); }
  }

  useEffect(() => {
    refreshRuns();
    api.agentTools().then((r) => setTools(r.tools)).catch(() => setTools([]));
  }, []);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [current]);

  async function open(id: string) {
    setError(null);
    try { setCurrent(await api.agentGetRun(id)); } catch (e) { setError(msg(e)); }
  }

  async function send() {
    const message = draft.trim();
    if (!message || busy) return;
    setBusy(true); setError(null); setDraft("");
    try {
      const run = await api.agentChat({ message, run_id: current?.id });
      setCurrent(run);
      await refreshRuns();
    } catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }

  async function approve() {
    if (!current || busy) return;
    setBusy(true); setError(null);
    try { setCurrent(await api.agentApprove(current.id)); await refreshRuns(); }
    catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }

  async function reject() {
    if (!current || busy || !rejectReason.trim()) return;
    setBusy(true); setError(null);
    try {
      setCurrent(await api.agentReject(current.id, rejectReason.trim()));
      setRejecting(false); setRejectReason(""); await refreshRuns();
    } catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }

  const parked = current?.steps?.find(
    (s) => s.guardrail_verdict === "require_approval" && !s.approved_at,
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Līgumu pārvaldības aģents</h1>
        <p className="text-sm text-slate-600">
          Aģents pats izvēlas nākamo darbību un pamato izvēli. Katrs solis tiek reģistrēts
          pirms izpildes; darbības ar neatgriezeniskām vai finansiālām sekām gaida cilvēka
          apstiprinājumu. Galīgo lēmumu pieņem organizācijas darbinieks.
        </p>
      </div>

      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <div className="space-y-4">
          <Panel title="Uzdevumi">
            <button
              className="mb-2 w-full rounded bg-accent-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-800"
              onClick={() => { setCurrent(null); setDraft(""); }}
            >
              Jauns uzdevums
            </button>
            <div className="max-h-80 space-y-1 overflow-auto">
              {runs.length === 0 && <p className="text-sm text-slate-500">Vēl nav neviena uzdevuma.</p>}
              {runs.map((r) => (
                <button
                  key={r.id}
                  onClick={() => open(r.id)}
                  className={`block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100 ${
                    current?.id === r.id ? "bg-slate-100" : ""
                  }`}
                >
                  <span className="line-clamp-2 text-slate-800">{r.goal}</span>
                  <span className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                    <StatusPill status={r.status} />
                    {r.steps_used}/{r.max_steps} soļi
                  </span>
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Rīki un robežas">
            <p className="mb-2 text-xs text-slate-500">
              Nezināma spēja tiek uzskatīta par neatgriezenisku un vienmēr prasa apstiprinājumu.
            </p>
            <div className="max-h-72 space-y-1 overflow-auto">
              {tools.map((t) => (
                <div key={t.name} className="flex items-start justify-between gap-2 text-xs">
                  <code className="text-slate-700">{t.name}</code>
                  <ReversibilityTag value={t.reversibility} />
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <Panel title={current ? "Lēmumu žurnāls" : "Saruna ar aģentu"}>
          {!current && (
            <div className="mb-3 space-y-2 text-sm text-slate-600">
              <p>Piemēri, ko var uzdot:</p>
              <ul className="list-inside list-disc space-y-1 text-slate-500">
                <li>Pārbaudi līgumu UAS-EXAMPLE-001 un uzskaiti saistības un termiņus.</li>
                <li>Sagatavo pārvaldības kalendāru nākamajām 60 dienām visiem līgumiem.</li>
                <li>Salīdzini limitu saistības ar SAP faktiskajiem maksājumiem.</li>
              </ul>
            </div>
          )}

          {current && (
            <div className="mb-3 space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <StatusPill status={current.status} />
                <span className="text-slate-500">
                  {current.steps_used}/{current.max_steps} soļi · modelis {current.model_ref}
                </span>
              </div>
              <p className="rounded bg-slate-50 p-2 text-sm text-slate-700">{current.goal}</p>

              {current.steps.map((s) => <StepCard key={s.id} step={s} />)}

              {current.outcome?.answer && (
                <div className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                  {current.outcome.answer}
                </div>
              )}
              {current.halt_reason && (
                <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
                  Apturēts: {current.halt_reason}
                </div>
              )}
            </div>
          )}

          {parked && (
            <div className="mb-3 rounded border border-amber-400 bg-amber-50 p-3">
              <p className="text-sm font-medium text-amber-900">
                Gaida apstiprinājumu: <code>{parked.action_capability}</code>
              </p>
              <p className="mt-1 text-xs text-amber-800">{parked.guardrail_reason}</p>
              <pre className="mt-2 overflow-auto rounded bg-white p-2 text-xs text-slate-700">
                {JSON.stringify(parked.action_inputs, null, 2)}
              </pre>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  disabled={busy}
                  onClick={approve}
                  className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
                >
                  Apstiprināt un izpildīt
                </button>
                <button
                  disabled={busy}
                  onClick={() => setRejecting((v) => !v)}
                  className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-white"
                >
                  Noraidīt
                </button>
                <span className="text-xs text-amber-800">
                  Ziņa sarunā šo darbību neapstiprina.
                </span>
              </div>
              {rejecting && (
                <div className="mt-2 flex gap-2">
                  <input
                    className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
                    placeholder="Noraidījuma pamatojums"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                  />
                  <button
                    disabled={busy || !rejectReason.trim()}
                    onClick={reject}
                    className="rounded bg-red-700 px-3 py-1.5 text-sm text-white hover:bg-red-800 disabled:opacity-50"
                  >
                    Noraidīt
                  </button>
                </div>
              )}
            </div>
          )}

          <div ref={bottom} />
          <div className="flex gap-2">
            <input
              className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm focus:border-accent-500 focus:outline-none"
              placeholder={current ? "Papildu norādījums aģentam…" : "Ko vajag izdarīt?"}
              value={draft}
              disabled={busy}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            />
            <button
              onClick={send}
              disabled={busy || !draft.trim()}
              className="rounded bg-accent-700 px-4 py-2 text-sm font-medium text-white hover:bg-accent-800 disabled:opacity-50"
            >
              {busy ? "Strādā…" : "Sūtīt"}
            </button>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function StepCard({ step }: { step: AgentStep }) {
  const denied = step.guardrail_verdict === "deny";
  const parked = step.guardrail_verdict === "require_approval" && !step.approved_at;
  const border = denied ? "border-red-200" : parked ? "border-amber-300" : "border-slate-200";
  return (
    <div className={`rounded border ${border} bg-white p-3`}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-700">
          {step.seq}. {step.phase}
        </span>
        {step.action_capability && <code className="text-slate-700">{step.action_capability}</code>}
        {step.guardrail_verdict && <VerdictTag value={step.guardrail_verdict} />}
        {step.approved_at && <span className="text-emerald-700">apstiprināja cilvēks</span>}
        {step.latency_ms != null && <span>{step.latency_ms} ms</span>}
      </div>
      {step.thought && <p className="mt-2 text-sm text-slate-800">{step.thought}</p>}
      {step.guardrail_reason && step.guardrail_verdict !== "allow" && (
        <p className="mt-1 text-xs text-slate-500">{step.guardrail_reason}</p>
      )}
      {step.observation != null && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-slate-500">Rezultāts</summary>
          <pre className="mt-1 max-h-64 overflow-auto rounded bg-slate-50 p-2 text-xs text-slate-700">
            {JSON.stringify(step.observation, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {children}
    </section>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: "bg-emerald-100 text-emerald-800",
    awaiting_approval: "bg-amber-100 text-amber-800",
    running: "bg-blue-100 text-blue-800",
    planning: "bg-blue-100 text-blue-800",
    halted: "bg-slate-200 text-slate-700",
    failed: "bg-red-100 text-red-800",
  };
  const label: Record<string, string> = {
    completed: "pabeigts",
    awaiting_approval: "gaida apstiprinājumu",
    running: "darbojas",
    planning: "plāno",
    halted: "apturēts",
    failed: "kļūda",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${map[status] || "bg-slate-100 text-slate-700"}`}>
      {label[status] || status}
    </span>
  );
}

function ReversibilityTag({ value }: { value: string }) {
  const map: Record<string, [string, string]> = {
    read_only: ["lasīšana", "bg-slate-100 text-slate-600"],
    reversible: ["atgriezeniska", "bg-blue-100 text-blue-800"],
    irreversible: ["neatgriezeniska", "bg-amber-100 text-amber-900"],
  };
  const [label, cls] = map[value] || [value, "bg-slate-100 text-slate-600"];
  return <span className={`shrink-0 rounded px-1.5 py-0.5 ${cls}`}>{label}</span>;
}

function VerdictTag({ value }: { value: string }) {
  const map: Record<string, [string, string]> = {
    allow: ["atļauts", "text-emerald-700"],
    deny: ["liegts", "text-red-700"],
    require_approval: ["prasa apstiprinājumu", "text-amber-700"],
  };
  const [label, cls] = map[value] || [value, "text-slate-600"];
  return <span className={cls}>{label}</span>;
}

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AgentRuntime } from "../api/client";
import type { LegalConnTest, LegalConnection } from "../api/client";

interface CardSpec {
  kind: string;
  title: string;
  blurb: string;
  defaultName: string;
}

const CARDS: CardSpec[] = [
  {
    kind: "docus_registry",
    title: "DOCUS — contract registry",
    blurb:
      "Read-only source of contract registry records. The platform never writes to DOCUS. " +
      "v0.1 runs the mock adapter; the pilot replaces it with a real read-only adapter " +
      "(API, database view, or periodic export) behind the same interface.",
    defaultName: "DOCUS contract registry",
  },
  {
    kind: "sap_actuals",
    title: "SAP — actuals & payments",
    blurb:
      "Read-only source of actual spend and payment lines per contract, used for " +
      "limit-threshold and payment-after-expiry obligations. v0.1 runs the mock adapter.",
    defaultName: "SAP actuals (read-only)",
  },
  {
    kind: "ms_purview",
    title: "Microsoft 365 / Purview (MIP)",
    blurb:
      "Sovereign read of internally-classified documents. DOCUS objects carry " +
      "Purview sensitivity labels (\u201CFor Internal Confidential Use Only\u201D) that " +
      "apply encryption, so an external read returns ciphertext. The real adapter " +
      "decrypts in-tenant on VPS-2 via the MIP SDK super-user grant \u2014 the label is " +
      "never removed, plaintext never leaves the organisation, and every access is logged in the " +
      "Purview audit log. It is the real decryption layer behind docus.read; no UAPF " +
      "package change. v0.1 runs the mock adapter.",
    defaultName: "Microsoft 365 / Purview (MIP)",
  },
];

function ConnectorCard({ spec }: { spec: CardSpec }) {
  const [conn, setConn] = useState<LegalConnection | null>(null);
  const [name, setName] = useState(spec.defaultName);
  const [mode, setMode] = useState("mock");
  const [baseUrl, setBaseUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [test, setTest] = useState<LegalConnTest | null>(null);

  async function load() {
    try {
      const r = await api.getLegalConnections();
      const c = r.connections.find((x) => x.kind === spec.kind) || null;
      setConn(c);
      if (c) {
        setName(c.name);
        setMode((c.config.mode as string) || "mock");
        setBaseUrl((c.config.base_url as string) || "");
      }
    } catch {
      /* not configured yet */
    }
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    setBusy(true); setMsg(null);
    try {
      const c = await api.saveLegalConnection(spec.kind, {
        name, mode, base_url: baseUrl || undefined,
      });
      setConn(c); setMsg("Saved.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doTest() {
    setBusy(true); setMsg(null); setTest(null);
    try {
      setTest(await api.testLegalConnection(spec.kind));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">{spec.title}</h3>
        <span className={`rounded border px-2 py-0.5 text-xs ${conn ? "border-emerald-300 bg-emerald-50 text-emerald-700" : "border-slate-300 bg-slate-50 text-slate-500"}`}>
          {conn ? `configured · ${(conn.config.mode as string) || "mock"}` : "not configured"}
        </span>
      </div>
      <p className="mb-3 text-xs text-slate-500">{spec.blurb}</p>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-xs text-slate-600">
          Name
          <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                 value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="text-xs text-slate-600">
          Mode
          <select className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="mock">mock (v0.1 sample data)</option>
            <option value="api">api (pilot)</option>
            <option value="export">export file (pilot)</option>
          </select>
        </label>
        <label className="text-xs text-slate-600">
          Base URL / path
          <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                 placeholder="(not used in mock mode)"
                 value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
        </label>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button onClick={() => void save()} disabled={busy}
                className="rounded bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50">
          Save
        </button>
        <button onClick={() => void doTest()} disabled={busy}
                className="rounded border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
          Test adapter
        </button>
        {msg && <span className="text-xs text-slate-500">{msg}</span>}
        {test && (
          <span className={`text-xs ${test.ok ? "text-emerald-700" : "text-red-700"}`}>
            {test.ok ? `OK — adapter: ${test.adapter}, ${test.records} record(s)` : `Failed: ${test.error}`}
          </span>
        )}
      </div>
    </div>
  );
}

export function ConnectionsPage() {
  return (
    <div className="space-y-4">
      <AgentRuntimePanel />
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Source connectors</h1>
        <p className="text-sm text-slate-600">
          Read-only sources feeding the Agreement Register. The register — not the sources —
          is what governance monitoring iterates.
        </p>
      </div>
      {CARDS.map((c) => <ConnectorCard key={c.kind} spec={c} />)}
    </div>
  );
}


/* Runtime configuration the pilot has to be able to show on demand: which
 * model answers, where it lives, and where agreements are stored. Values are
 * shapes and reachability only — no keys are returned by the API. */
export function AgentRuntimePanel() {
  const [rt, setRt] = useState<AgentRuntime | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.agentRuntime().then(setRt).catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  if (err) return <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{err}</div>;
  if (!rt) return <div className="text-sm text-slate-500">Ielādē izpildlaika konfigurāciju…</div>;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Modelis un līgumu krātuve</h2>
      <p className="mb-3 text-sm text-slate-600">
        Aģenta spriešana un līgumu imports notiek caur šeit norādīto modeli. Pilotprojektā
        Smilškastes vidē tas ir suverēns LLM aiz anonimizācijas vārtejas; atslēgas šajā skatā netiek rādītas.
      </p>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        <Row label="Modeļa nodrošinātājs" value={rt.llm.provider} />
        <Row label="Modelis" value={rt.llm.model || "—"} />
        <Row label="Galapunkts" value={rt.llm.endpoint || "—"} />
        <Row label="Konfigurēts"
             value={rt.llm.configured ? "jā" : "nē — izmanto rezerves atbildes"}
             tone={rt.llm.configured ? "ok" : "warn"} />
        <Row label="e-Līgumi krātuve" value={rt.store.base_url} />
        <Row label="Krātuve sasniedzama"
             value={rt.store.reachable
               ? `jā — ${rt.store.agreements ?? 0} līgumi`
               : `nē — ${rt.store.detail}`}
             tone={rt.store.reachable ? "ok" : "warn"} />
        <Row label="Soļu limits" value={String(rt.agent.max_steps)} />
        <Row label="Prasa apstiprinājumu" value={rt.agent.irreversible.join(", ")} />
      </dl>
      <p className="mt-3 text-xs text-slate-500">{rt.llm.note}</p>
    </section>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: "ok" | "warn" }) {
  const cls = tone === "warn" ? "text-amber-800" : tone === "ok" ? "text-emerald-800" : "text-slate-800";
  return (
    <div className="flex flex-col">
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className={`break-all font-medium ${cls}`}>{value}</dd>
    </div>
  );
}

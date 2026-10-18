import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { StoreAgreementDetail, StoreFinding, StoreVersion } from "../api/client";
import { StatusTag, ValidationTag } from "./AgreementsPage";

/* One agreement: what it says, whether it conforms, and how it got here. */

export default function AgreementDetailPage() {
  const { agreementId } = useParams();
  const id = Number(agreementId);
  const [doc, setDoc] = useState<StoreAgreementDetail | null>(null);
  const [versions, setVersions] = useState<StoreVersion[]>([]);
  const [version, setVersion] = useState<number | undefined>(undefined);
  const [xml, setXml] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"summary" | "validation" | "xml">("summary");

  useEffect(() => {
    setError(null);
    api.storeGetAgreement(id, version)
      .then((d) => { setDoc(d); setXml(""); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [id, version]);

  useEffect(() => {
    api.storeVersions(id).then((r) => setVersions(r.versions)).catch(() => setVersions([]));
  }, [id]);

  useEffect(() => {
    if (tab !== "xml" || !doc || xml) return;
    api.storeXml(id, doc.version).then(setXml).catch((e) => setXml(String(e)));
  }, [tab, doc, id, xml]);

  if (error) return <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>;
  if (!doc) return <div className="text-sm text-slate-500">Ielādē…</div>;

  const errors = doc.findings.filter((f) => f.severity === "error");
  const warnings = doc.findings.filter((f) => f.severity !== "error");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs text-slate-500">
            <Link to="/agreements" className="hover:underline">Līgumu reģistrs</Link>
            {" / "}{doc.uas_id} · v{doc.version}
          </div>
          <h1 className="text-xl font-semibold text-slate-900">{doc.title || doc.uas_id}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
            <StatusTag value={doc.status} />
            {doc.agreement_type && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">{doc.agreement_type}</span>
            )}
            {doc.profile && <span className="text-xs text-slate-500">profils: {doc.profile}</span>}
            <ValidationTag a={doc} />
            {doc.needs_review && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                MI sagatavots melnraksts — jāpārskata
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <a href={`/api/store/agreements/${id}/v${doc.version}/xml`}
             className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-white">
            Lejupielādēt XML
          </a>
          <Link to={`/agreements/${id}/edit`}
                className="rounded bg-accent-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-800">
            Rediģēt
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex gap-1 border-b border-slate-200 px-3 pt-2">
            <Tab id="summary" tab={tab} set={setTab}>Kopsavilkums</Tab>
            <Tab id="validation" tab={tab} set={setTab}>
              Validācija{doc.findings.length ? ` (${doc.findings.length})` : ""}
            </Tab>
            <Tab id="xml" tab={tab} set={setTab}>Kanoniskais XML</Tab>
          </div>
          <div className="p-4">
            {tab === "summary" && <SummaryView doc={doc} />}
            {tab === "validation" && (
              <div className="space-y-2">
                {doc.findings.length === 0 && (
                  <p className="text-sm text-emerald-800">Nav kļūdu un brīdinājumu.</p>
                )}
                {errors.map((f, i) => <Finding key={`e${i}`} f={f} />)}
                {warnings.map((f, i) => <Finding key={`w${i}`} f={f} />)}
              </div>
            )}
            {tab === "xml" && (
              <pre className="max-h-[32rem] overflow-auto rounded bg-slate-50 p-3 text-xs text-slate-800">
                {xml || "Ielādē…"}
              </pre>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <Panel title="Versijas">
            <ul className="space-y-1 text-sm">
              {versions.map((v) => (
                <li key={v.version}>
                  <button
                    onClick={() => setVersion(v.version)}
                    className={`w-full rounded px-2 py-1 text-left hover:bg-slate-100 ${
                      v.version === doc.version ? "bg-slate-100 font-medium" : ""
                    }`}
                  >
                    v{v.version}
                    {v.version === doc.current_version && (
                      <span className="ml-1 text-xs text-emerald-700">aktuālā</span>
                    )}
                    <span className="block text-xs text-slate-500">
                      {v.change_note || "—"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Izcelsme">
            <dl className="space-y-1 text-sm">
              <Row k="Avots" v={doc.source} />
              <Row k="Klauzulas" v={String(doc.clause_count)} />
              <Row k="Standartizācija"
                   v={doc.standardization_ratio != null
                      ? `${Math.round(doc.standardization_ratio * 100)}%` : "—"} />
              <Row k="Valoda" v={doc.language} />
            </dl>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function SummaryView({ doc }: { doc: StoreAgreementDetail }) {
  const s = (doc.summary || {}) as Record<string, unknown>;
  const entries = Object.entries(s).filter(([, v]) => v !== null && v !== "" && v !== undefined);
  if (entries.length === 0) return <p className="text-sm text-slate-500">Nav kopsavilkuma datu.</p>;
  return (
    <dl className="grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <Row key={k} k={k} v={typeof v === "object" ? JSON.stringify(v) : String(v)} />
      ))}
    </dl>
  );
}

function Finding({ f }: { f: StoreFinding }) {
  const err = f.severity === "error";
  return (
    <div className={`rounded border p-2 text-sm ${err ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"}`}>
      <div className="flex items-center gap-2">
        {f.rule && (
          <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${err ? "bg-red-200 text-red-900" : "bg-amber-200 text-amber-900"}`}>
            {f.rule}
          </span>
        )}
        <span className="text-xs uppercase tracking-wide text-slate-500">{f.layer}</span>
      </div>
      <p className={`mt-1 ${err ? "text-red-900" : "text-amber-900"}`}>{f.message}</p>
      {f.location && <p className="mt-1 break-all text-xs text-slate-500">{f.location}</p>}
    </div>
  );
}

function Tab({ id, tab, set, children }: {
  id: "summary" | "validation" | "xml";
  tab: string;
  set: (v: "summary" | "validation" | "xml") => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={() => set(id)}
      className={`rounded-t px-3 py-1.5 text-sm ${
        tab === id ? "bg-white font-medium text-slate-900 shadow-[inset_0_-2px_0_0_theme(colors.accent.700)]"
                   : "text-slate-500 hover:text-slate-800"}`}
    >
      {children}
    </button>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {children}
    </section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs uppercase tracking-wide text-slate-500">{k}</dt>
      <dd className="break-words text-slate-800">{v}</dd>
    </div>
  );
}

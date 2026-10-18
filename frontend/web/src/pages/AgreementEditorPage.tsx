import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { StoreFinding } from "../api/client";

/* Editor for a UAS agreement.
 *
 * The document is edited as its UAS JSON. That is deliberate for the pilot:
 * the schema is the contract, a field-by-field form would silently drop
 * anything the form does not know about, and "Pārbaudīt" validates the real
 * serialised XML rather than a UI approximation. Saving appends a version. */

export default function AgreementEditorPage() {
  const { agreementId } = useParams();
  const id = agreementId ? Number(agreementId) : undefined;
  const nav = useNavigate();

  const [text, setText] = useState("{}");
  const [note, setNote] = useState("");
  const [findings, setFindings] = useState<StoreFinding[] | null>(null);
  const [counts, setCounts] = useState<{ errors: number; warnings: number } | null>(null);
  const [xml, setXml] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!id) {
      api.storeConfig()
        .then((c) => setText(JSON.stringify({
          agreementType: "services", title: "", language: "lv", status: "draft",
          profile: c.profiles?.[0]?.name || "", parties: [], terms: {},
        }, null, 2)))
        .catch(() => undefined);
      return;
    }
    api.storeGetAgreement(id)
      .then((d) => setText(JSON.stringify(d.uas, null, 2)))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);

  function parsed(): unknown {
    return JSON.parse(text);
  }

  async function check() {
    setBusy(true); setError(null);
    try {
      const r = await api.storePreview(parsed());
      setFindings(r.findings); setCounts({ errors: r.errors, warnings: r.warnings });
      setXml(r.xml);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function save() {
    setBusy(true); setError(null);
    try {
      const r = await api.storeSave({ agreement_id: id, data: parsed(), change_note: note || undefined });
      setDirty(false);
      nav(`/agreements/${r.agreement_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">
          {id ? "Rediģēt līgumu" : "Jauns līgums"}
        </h1>
        <p className="text-sm text-slate-600">
          Saglabāšana nekad nepārraksta iepriekšējo — tiek pievienota nākamā versija.
          Pārbaude validē faktisko UAS XML pret shēmu un Schematron noteikumiem.
        </p>
      </div>

      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">UAS dokuments (JSON)</label>
          <textarea
            className="h-[28rem] w-full rounded border border-slate-300 p-2 font-mono text-xs focus:border-accent-500 focus:outline-none"
            value={text}
            onChange={(e) => { setText(e.target.value); setDirty(true); }}
            spellCheck={false}
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
              placeholder="Izmaiņu piezīme (nav obligāta)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button onClick={check} disabled={busy}
                    className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50">
              Pārbaudīt
            </button>
            <button onClick={save} disabled={busy}
                    className="rounded bg-accent-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-800 disabled:opacity-50">
              {busy ? "Saglabā…" : "Saglabāt versiju"}
            </button>
            {dirty && <span className="text-xs text-amber-700">Nesaglabātas izmaiņas</span>}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">Validācija</span>
            {counts && (
              <span className={`text-sm ${counts.errors ? "text-red-800" : "text-emerald-800"}`}>
                {counts.errors} kļūda(s), {counts.warnings} brīdinājums(i)
              </span>
            )}
          </div>
          {!findings && <p className="text-sm text-slate-500">Nospiediet „Pārbaudīt”, lai validētu.</p>}
          {findings && findings.length === 0 && (
            <p className="text-sm text-emerald-800">Dokuments atbilst shēmai un noteikumiem.</p>
          )}
          <div className="max-h-56 space-y-2 overflow-auto">
            {(findings || []).map((f, i) => (
              <div key={i}
                   className={`rounded border p-2 text-xs ${
                     f.severity === "error" ? "border-red-200 bg-red-50 text-red-900"
                                            : "border-amber-200 bg-amber-50 text-amber-900"}`}>
                {f.rule && <span className="mr-1 font-medium">{f.rule}:</span>}
                {f.message}
              </div>
            ))}
          </div>
          {xml && (
            <>
              <div className="mb-1 mt-3 text-sm font-medium text-slate-700">Kanoniskais XML</div>
              <pre className="max-h-56 overflow-auto rounded bg-slate-50 p-2 text-xs text-slate-800">{xml}</pre>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

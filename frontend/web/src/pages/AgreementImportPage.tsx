import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { AgentRuntime, StoreProfile } from "../api/client";

/* Import: canonical UAS XML needs no model at all; docx/pdf/plain text goes
 * through the extractor, which does. The page says which path applies before
 * the user uploads, so an unconfigured model is never a surprise. */

export default function AgreementImportPage() {
  const nav = useNavigate();
  const [profiles, setProfiles] = useState<StoreProfile[]>([]);
  const [profile, setProfile] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rt, setRt] = useState<AgentRuntime | null>(null);
  const poll = useRef<number | null>(null);

  useEffect(() => {
    api.storeConfig().then((c) => setProfiles(c.profiles || [])).catch(() => setProfiles([]));
    api.agentRuntime().then(setRt).catch(() => setRt(null));
    return () => { if (poll.current) window.clearInterval(poll.current); };
  }, []);

  const isXml = !!file && file.name.toLowerCase().endsWith(".xml");
  const needsModel = !isXml && (!!file || !!text.trim());
  const modelReady = rt?.llm.configured ?? false;

  async function submit() {
    setBusy(true); setError(null); setStatus(null);
    try {
      const r = await api.storeImport({ file, text, profile });
      if (r.status === "done" && r.agreement_id) {
        nav(`/agreements/${r.agreement_id}`);
        return;
      }
      if (r.job_id) {
        setStatus("MI izgūst struktūru no dokumenta…");
        poll.current = window.setInterval(async () => {
          try {
            const j = await api.storeImportStatus(r.job_id!);
            if (j.status === "done" && j.agreement_id) {
              window.clearInterval(poll.current!);
              nav(`/agreements/${j.agreement_id}`);
            } else if (j.status === "error") {
              window.clearInterval(poll.current!);
              setError(j.error || "Izgūšana neizdevās.");
              setStatus(null); setBusy(false);
            }
          } catch { /* keep polling */ }
        }, 2000);
        return;
      }
      setStatus(JSON.stringify(r));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!poll.current) setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Līguma imports</h1>
        <p className="text-sm text-slate-600">
          UAS XML tiek ielasīts un validēts uzreiz. Word, PDF vai ielīmētu tekstu
          vispirms strukturē valodas modelis, un rezultāts nonāk reģistrā kā melnraksts
          ar atzīmi „jāpārskata”.
        </p>
      </div>

      {error && <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      {needsModel && !modelReady && (
        <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          Modelis nav konfigurēts ({rt?.llm.provider}), tāpēc Word/PDF izgūšana nedarbosies.
          UAS XML imports darbojas bez modeļa.
        </div>
      )}

      <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Fails</label>
          <input type="file" accept=".xml,.docx,.pdf,.txt"
                 onChange={(e) => setFile(e.target.files?.[0] || null)}
                 className="block w-full text-sm text-slate-700" />
          {file && (
            <p className="mt-1 text-xs text-slate-500">
              {isXml ? "Kanoniskais UAS XML — modelis netiek izmantots."
                     : "Teksts tiks strukturēts ar valodas modeli."}
            </p>
          )}
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Vai ielīmējiet tekstu</label>
          <textarea className="h-32 w-full rounded border border-slate-300 p-2 text-sm focus:border-accent-500 focus:outline-none"
                    value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Profils</label>
          <select className="rounded border border-slate-300 px-2 py-1 text-sm"
                  value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="">(noklusējuma)</option>
            {profiles.map((p) => (
              <option key={p.name} value={p.name}>{p.title || p.name}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={submit} disabled={busy || (!file && !text.trim())}
                  className="rounded bg-accent-700 px-4 py-2 text-sm font-medium text-white hover:bg-accent-800 disabled:opacity-50">
            {busy ? "Importē…" : "Importēt"}
          </button>
          {status && <span className="text-sm text-slate-600">{status}</span>}
        </div>
      </section>
    </div>
  );
}

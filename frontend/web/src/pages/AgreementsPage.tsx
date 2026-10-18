import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { StoreAgreement } from "../api/client";

/* Līgumu reģistrs — the agreements held in the e-Līgumi UAS store.
 * This is the register; the process package's example agreements are demo
 * fixtures and deliberately not shown here. */

export default function AgreementsPage() {
  const [rows, setRows] = useState<StoreAgreement[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.storeListAgreements()
      .then((r) => setRows(r.agreements))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const shown = rows.filter((a) =>
    !q.trim() ||
    [a.uas_id, a.title, a.buyer_name, a.supplier_name]
      .filter(Boolean).join(" ").toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Līgumu reģistrs</h1>
          <p className="text-sm text-slate-600">
            Līgumi strukturētā UAS formā. Katra saglabāšana pievieno jaunu versiju —
            iepriekšējās netiek pārrakstītas. Aģents reģistru tikai lasa.
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/agreements/import"
                className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-white">
            Imports
          </Link>
          <Link to="/agreements/new"
                className="rounded bg-accent-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-800">
            Jauns līgums
          </Link>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      <input
        className="w-full max-w-sm rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:outline-none"
        placeholder="Meklēt pēc numura, nosaukuma vai puses"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Numurs</th>
              <th className="px-3 py-2">Nosaukums</th>
              <th className="px-3 py-2">Veids</th>
              <th className="px-3 py-2">Puses</th>
              <th className="px-3 py-2">Versija</th>
              <th className="px-3 py-2">Validācija</th>
              <th className="px-3 py-2">Statuss</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="px-3 py-4 text-slate-500">Ielādē…</td></tr>
            )}
            {!loading && shown.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-slate-500">
                  {rows.length === 0
                    ? "Reģistrs ir tukšs. Sāciet ar importu vai izveidojiet jaunu līgumu."
                    : "Nav atbilstību meklētajam."}
                </td>
              </tr>
            )}
            {shown.map((a) => (
              <tr key={a.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-800">
                  <Link to={`/agreements/${a.id}`} className="text-accent-700 hover:underline">
                    {a.uas_id}
                  </Link>
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {a.title || <span className="text-slate-400">—</span>}
                  {a.needs_review && (
                    <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                      jāpārskata
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-slate-600">{a.agreement_type || "—"}</td>
                <td className="px-3 py-2 text-slate-600">
                  {[a.buyer_name, a.supplier_name].filter(Boolean).join(" / ") || "—"}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-slate-600">v{a.current_version}</td>
                <td className="whitespace-nowrap px-3 py-2"><ValidationTag a={a} /></td>
                <td className="whitespace-nowrap px-3 py-2"><StatusTag value={a.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ValidationTag({ a }: { a: { validation?: { ok?: boolean | null; errors?: number; warnings?: number } } }) {
  const v = a.validation || {};
  if (v.ok === null || v.ok === undefined) return <span className="text-slate-400">—</span>;
  if (v.ok) {
    return (
      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-800">
        derīgs{v.warnings ? ` · ${v.warnings} brīdinājumi` : ""}
      </span>
    );
  }
  return (
    <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-800">
      {v.errors} kļūdas{v.warnings ? ` · ${v.warnings} brīdinājumi` : ""}
    </span>
  );
}

export const STATUS_LV: Record<string, string> = {
  draft: "Melnraksts", offered: "Piedāvāts", signed: "Parakstīts", active: "Spēkā",
  suspended: "Apturēts", terminated: "Izbeigts", completed: "Pabeigts",
};

export function StatusTag({ value }: { value?: string | null }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const cls = value === "active" ? "bg-emerald-100 text-emerald-800"
    : value === "draft" ? "bg-slate-100 text-slate-700"
    : "bg-blue-100 text-blue-800";
  return <span className={`rounded px-1.5 py-0.5 text-xs ${cls}`}>{STATUS_LV[value] || value}</span>;
}

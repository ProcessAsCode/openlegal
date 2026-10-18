import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { StoreConfig } from "../api/client";

/* What the store validates against: schema version, profiles, clause library.
 * Read-only for the pilot — the UAS tree is pinned, not edited in the UI. */

export default function StoreConfigPage() {
  const [cfg, setCfg] = useState<StoreConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.storeConfig().then(setCfg).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>;
  if (!cfg) return <div className="text-sm text-slate-500">Ielādē…</div>;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Krātuves konfigurācija</h1>
        <p className="text-sm text-slate-600">
          UAS shēma un noteikumi ir piesaistīti versijai; profili un klauzulu bibliotēka
          nosaka, kas ir obligāts un kas skaitās standarta teksts.
        </p>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Versija</h2>
        <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div><dt className="text-xs text-slate-500">Aktīvā</dt><dd className="font-medium">{cfg.version}</dd></div>
          <div><dt className="text-xs text-slate-500">Pieejamās</dt><dd>{cfg.uas_versions.join(", ")}</dd></div>
          <div><dt className="text-xs text-slate-500">Shēma</dt><dd>{cfg.tree?.schema_present ? "ir" : "trūkst"}</dd></div>
          <div><dt className="text-xs text-slate-500">Noteikumi</dt><dd>{cfg.tree?.rules_present ? "ir" : "trūkst"}</dd></div>
        </dl>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Profili ({cfg.profiles.length})
        </h2>
        <ul className="space-y-1 text-sm">
          {cfg.profiles.map((p) => (
            <li key={p.name} className="flex gap-2">
              <code className="text-slate-700">{p.name}</code>
              <span className="text-slate-500">{p.title || ""}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Klauzulu bibliotēka ({cfg.clause_library.length})
        </h2>
        <ul className="space-y-1 text-sm">
          {cfg.clause_library.map((c) => (
            <li key={c.id} className="flex gap-2">
              <code className="text-slate-700">{c.id}</code>
              <span className="text-slate-500">{c.title || ""}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { api, getOrgSlug, setOrgSlug } from "../api/client";

export function Layout() {
  const [orgSlug] = useState(getOrgSlug());
  const [orgs, setOrgs] = useState<{ slug: string; name: string }[]>([]);

  useEffect(() => {
    api.listOrgs().then((r) => setOrgs(r.orgs)).catch(() => setOrgs([]));
  }, []);

  function changeOrg(slug: string) {
    if (slug === orgSlug) return;
    setOrgSlug(slug);
    window.location.reload();
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 items-center justify-between border-b border-slate-200 bg-white px-4">
        <div className="flex items-center gap-4">
          <span className="font-semibold tracking-tight">
            <span className="text-accent-700">Open</span>Legal
          </span>
          <span className="hidden text-sm text-slate-500 sm:inline">
            Līgumu pārvaldības aģents
          </span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <label className="text-slate-500">Org</label>
          <select
            className="rounded border border-slate-300 px-2 py-1 text-sm focus:border-accent-500 focus:outline-none"
            value={orgSlug}
            onChange={(e) => changeOrg(e.target.value)}
          >
            {orgs.length === 0 && <option value={orgSlug}>{orgSlug}</option>}
            {orgs.map((o) => (
              <option key={o.slug} value={o.slug}>
                {o.name} ({o.slug})
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-56 shrink-0 border-r border-slate-200 bg-white p-3">
          <SidebarSection title="Aģents">
            <NavLink to="/agent" className={navItemClasses}>Uzdevumi un lēmumi</NavLink>
          </SidebarSection>
          <SidebarSection title="Līgumi">
            <NavLink to="/agreements" className={navItemClasses} end>Reģistrs</NavLink>
            <NavLink to="/agreements/import" className={navItemClasses}>Imports</NavLink>
            <NavLink to="/agreements/new" className={navItemClasses}>Jauns līgums</NavLink>
            <NavLink to="/agreements/config" className={navItemClasses}>Konfigurācija</NavLink>
          </SidebarSection>
          <SidebarSection title="Work">
            <NavLink to="/obligations" className={navItemClasses}>Obligations</NavLink>
            <NavLink to="/calendar" className={navItemClasses}>Calendar</NavLink>
            <NavLink to="/queue" className={navItemClasses}>Queue</NavLink>
          </SidebarSection>
          <SidebarSection title="Audit">
            <NavLink to="/audit" className={navItemClasses}>Audit log</NavLink>
          </SidebarSection>
          <SidebarSection title="Reports">
            <NavLink to="/reports" className={navItemClasses}>Dashboard</NavLink>
          </SidebarSection>
          <SidebarSection title="UAPF">
            <NavLink to="/uapf" className={navItemClasses} end>System</NavLink>
            <NavLink to="/uapf/demo" className={navItemClasses}>Demo console</NavLink>
            <NavLink to="/uapf/packages" className={navItemClasses}>Packages</NavLink>
            <NavLink to="/uapf/sessions" className={navItemClasses}>Sessions</NavLink>
            <NavLink to="/uapf/engine" className={navItemClasses}>Engine</NavLink>
          </SidebarSection>
          <SidebarSection title="Admin">
            <NavLink to="/connections" className={navItemClasses}>Connections</NavLink>
          </SidebarSection>
        </aside>

        <main className="min-w-0 flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function SidebarSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="mb-1 px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
        {title}
      </h3>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

const navItemClasses = ({ isActive }: { isActive: boolean }) =>
  `nav-item ${isActive ? "active" : ""}`;

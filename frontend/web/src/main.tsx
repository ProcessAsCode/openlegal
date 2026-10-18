import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import "./index.css";
import { Layout } from "./components/Layout";
import { QueuePage } from "./pages/QueuePage";
import { CaseDetailPage } from "./pages/CaseDetailPage";
import { ConnectionsPage } from "./pages/ConnectionsPage";
import { AuditPage } from "./pages/AuditPage";
import { ReportsPage } from "./pages/ReportsPage";
import UapfPage from "./pages/UapfPage";
import ObligationsBoardPage from "./pages/ObligationsBoardPage";
import AgreementsPage from "./pages/AgreementsPage";
import AgentPage from "./pages/AgentPage";
import AgreementDetailPage from "./pages/AgreementDetailPage";
import AgreementEditorPage from "./pages/AgreementEditorPage";
import AgreementImportPage from "./pages/AgreementImportPage";
import StoreConfigPage from "./pages/StoreConfigPage";
import CalendarPage from "./pages/CalendarPage";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename="/app">
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/queue" replace />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/agent" element={<AgentPage />} />
          <Route path="/obligations" element={<ObligationsBoardPage />} />
          <Route path="/agreements" element={<AgreementsPage />} />
          <Route path="/agreements/new" element={<AgreementEditorPage />} />
          <Route path="/agreements/import" element={<AgreementImportPage />} />
          <Route path="/agreements/config" element={<StoreConfigPage />} />
          <Route path="/agreements/:agreementId" element={<AgreementDetailPage />} />
          <Route path="/agreements/:agreementId/edit" element={<AgreementEditorPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/cases/:caseId" element={<CaseDetailPage />} />
          <Route path="/connections" element={<ConnectionsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/uapf" element={<UapfPage />} />
          <Route path="/uapf/:tab" element={<UapfPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);

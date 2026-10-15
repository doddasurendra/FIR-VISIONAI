import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LanguageProvider } from './context/LanguageContext';

import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';

import { Dashboard } from './pages/Dashboard';
import { CaseManagement } from './pages/CaseManagement';
import { CaseDetail } from './pages/CaseDetail';
import { NewCaseIntake } from './pages/NewCaseIntake';
import { AICaseSummaries } from './pages/AICaseSummaries';
import { LegalSectionAssistance } from './pages/LegalSectionAssistance';
import { EntityNetwork } from './pages/EntityNetwork';
import { EntityReviewQueue } from './pages/EntityReviewQueue';
import { CaseDiaryGenerator } from './pages/CaseDiaryGenerator';
import { ChargesheetGenerator } from './pages/ChargesheetGenerator';
import { AIFIRAssistance } from './pages/AIFIRAssistance';
import { BulkIngestion } from './pages/BulkIngestion';
import { EmployeeManagement } from './pages/EmployeeManagement';
import { AuditTrail } from './pages/AuditTrail';
import { ReportsAnalytics } from './pages/ReportsAnalytics';
import { SettingsHealth } from './pages/SettingsHealth';
import { Login } from './pages/Login';

const AppContent: React.FC = () => {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <div className="flex h-screen bg-slate-100 overflow-hidden font-sans">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/cases" element={<CaseManagement />} />
            <Route path="/cases/:id" element={<CaseDetail />} />
            <Route path="/intake" element={<NewCaseIntake />} />
            <Route path="/summaries" element={<AICaseSummaries />} />
            <Route path="/legal" element={<LegalSectionAssistance />} />
            <Route path="/network" element={<EntityNetwork />} />
            <Route path="/entity-review" element={<EntityReviewQueue />} />
            <Route path="/case-diary" element={<CaseDiaryGenerator />} />
            <Route path="/chargesheet" element={<ChargesheetGenerator />} />
            <Route path="/ai-fir-assistance" element={<AIFIRAssistance />} />
            <Route path="/bulk-ingestion" element={<BulkIngestion />} />
            <Route path="/employees" element={<EmployeeManagement />} />
            <Route path="/audit-trail" element={<AuditTrail />} />
            <Route path="/reports" element={<ReportsAnalytics />} />
            <Route path="/settings" element={<SettingsHealth />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <Router>
      <LanguageProvider>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </LanguageProvider>
    </Router>
  );
};

export default App;

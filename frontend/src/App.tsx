import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LanguageProvider } from './context/LanguageContext';

import { GovernmentHeader } from './components/layout/GovernmentHeader';
import { HorizontalNav } from './components/layout/HorizontalNav';
import { GovernmentFooter } from './components/layout/GovernmentFooter';

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
import { FolderView } from './pages/FolderView';
import { PersonsView } from './pages/PersonsView';
import { FIRApplicationForm } from './pages/FIRApplicationForm';
import { DocumentExtractionWorkspace } from './pages/DocumentExtractionWorkspace';
import { ErrorBoundary } from './components/common/ErrorBoundary';

const AppContent: React.FC = () => {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-900 antialiased">
      {/* Official Andhra Pradesh Government Portal Header */}
      <GovernmentHeader />

      {/* Horizontal Dropdown Navigation Bar */}
      <HorizontalNav />

      {/* Main Full-Width Portal Workspace */}
      <main className="flex-1 w-full max-w-[1700px] mx-auto p-4 sm:p-6 lg:p-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/cases" element={<CaseManagement />} />
          <Route path="/cases/:id" element={<CaseDetail />} />
          <Route path="/intake" element={<NewCaseIntake />} />
          <Route path="/fir-application" element={<FIRApplicationForm />} />
          <Route path="/fir-application/:case_id" element={<FIRApplicationForm />} />
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
          <Route
            path="/document-extraction"
            element={
              <ErrorBoundary title="Document Extraction Workspace Notice">
                <DocumentExtractionWorkspace />
              </ErrorBoundary>
            }
          />
          <Route path="/folders/:slug" element={<FolderView />} />
          <Route path="/folders/persons/:type" element={<PersonsView />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      {/* Department Statutory Footer */}
      <GovernmentFooter />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <Router>
      <LanguageProvider>
        <AuthProvider>
          <ErrorBoundary title="FIR VisionAI System Notice">
            <AppContent />
          </ErrorBoundary>
        </AuthProvider>
      </LanguageProvider>
    </Router>
  );
};

export default App;

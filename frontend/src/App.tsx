import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LanguageProvider } from './context/LanguageContext';
import { FIRModalProvider } from './context/FIRModalContext';

import { GovernmentHeader } from './components/layout/GovernmentHeader';
import { HorizontalNav } from './components/layout/HorizontalNav';
import { GovernmentFooter } from './components/layout/GovernmentFooter';
import { ErrorBoundary } from './components/common/ErrorBoundary';

// Eagerly loaded (small/critical path)
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';

// Lazily loaded (heavy pages — split into separate chunks)
const CaseManagement = lazy(() => import('./pages/CaseManagement').then(m => ({ default: m.CaseManagement })));
const CaseDetail = lazy(() => import('./pages/CaseDetail').then(m => ({ default: m.CaseDetail })));
const NewCaseIntake = lazy(() => import('./pages/NewCaseIntake').then(m => ({ default: m.NewCaseIntake })));
const AICaseSummaries = lazy(() => import('./pages/AICaseSummaries').then(m => ({ default: m.AICaseSummaries })));
const LegalSectionAssistance = lazy(() => import('./pages/LegalSectionAssistance').then(m => ({ default: m.LegalSectionAssistance })));
const EntityNetwork = lazy(() => import('./pages/EntityNetwork').then(m => ({ default: m.EntityNetwork })));
const EntityReviewQueue = lazy(() => import('./pages/EntityReviewQueue').then(m => ({ default: m.EntityReviewQueue })));
const CaseDiaryGenerator = lazy(() => import('./pages/CaseDiaryGenerator').then(m => ({ default: m.CaseDiaryGenerator })));
const ChargesheetGenerator = lazy(() => import('./pages/ChargesheetGenerator').then(m => ({ default: m.ChargesheetGenerator })));
const AIFIRAssistance = lazy(() => import('./pages/AIFIRAssistance').then(m => ({ default: m.AIFIRAssistance })));
const BulkIngestion = lazy(() => import('./pages/BulkIngestion').then(m => ({ default: m.BulkIngestion })));
const EmployeeManagement = lazy(() => import('./pages/EmployeeManagement').then(m => ({ default: m.EmployeeManagement })));
const AuditTrail = lazy(() => import('./pages/AuditTrail').then(m => ({ default: m.AuditTrail })));
const ReportsAnalytics = lazy(() => import('./pages/ReportsAnalytics').then(m => ({ default: m.ReportsAnalytics })));
const SettingsHealth = lazy(() => import('./pages/SettingsHealth').then(m => ({ default: m.SettingsHealth })));
const FolderView = lazy(() => import('./pages/FolderView').then(m => ({ default: m.FolderView })));
const PersonsView = lazy(() => import('./pages/PersonsView').then(m => ({ default: m.PersonsView })));
const FIRApplicationForm = lazy(() => import('./pages/FIRApplicationForm').then(m => ({ default: m.FIRApplicationForm })));
const DocumentExtractionWorkspace = lazy(() => import('./pages/DocumentExtractionWorkspace').then(m => ({ default: m.DocumentExtractionWorkspace })));

/** Shared page-level loading indicator for lazy routes */
const PageLoader: React.FC = () => (
  <div className="flex items-center justify-center min-h-[60vh]">
    <div className="text-center space-y-3">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#0f5132] mx-auto" />
      <p className="text-sm text-slate-500">Loading page…</p>
    </div>
  </div>
);

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
        <Suspense fallback={<PageLoader />}>
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
        </Suspense>
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
          <FIRModalProvider>
            <ErrorBoundary title="FIR VisionAI System Notice">
              <AppContent />
            </ErrorBoundary>
          </FIRModalProvider>
        </AuthProvider>
      </LanguageProvider>
    </Router>
  );
};

export default App;

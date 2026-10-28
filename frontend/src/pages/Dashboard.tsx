import React, { useEffect, useState } from 'react';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { useFIRModal } from '../context/FIRModalContext';
import api from '../api/client';
import {
  FolderOpen,
  CheckCircle,
  Clock,
  Archive,
  AlertCircle,
  FileText,
  TrendingUp,
  ShieldAlert,
  ArrowRight,
  FolderSearch,
  FilePlus,
  Scale,
  MessageCircle
} from 'lucide-react';
import { Link } from 'react-router-dom';

/** Skeleton card for numbers not yet loaded */
const KPISkeleton: React.FC = () => (
  <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between animate-pulse">
    <div className="space-y-2">
      <div className="h-3 w-24 bg-slate-200 rounded" />
      <div className="h-7 w-12 bg-slate-200 rounded" />
      <div className="h-2 w-28 bg-slate-100 rounded" />
    </div>
    <div className="w-12 h-12 rounded-xl bg-slate-100" />
  </div>
);

export const Dashboard: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const { openFIRModal } = useFIRModal();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchKPIs = async () => {
      try {
        const res = await api.get('/analytics/dashboard');
        if (!cancelled) setData(res.data);
      } catch (e) {
        console.error('Error loading dashboard KPIs:', e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchKPIs();
    return () => { cancelled = true; };
  }, [user?.id]); // depend only on user id, not the whole user object

  const statusCounts = data?.cases_by_status || {};

  return (
    <div className="space-y-6">
      {/* Top Welcome / Scope Banner */}
      <div className="bg-gradient-to-r from-blue-900 to-slate-900 text-white rounded-xl p-6 shadow-md border border-blue-800/40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-400/30 mb-2">
              <span>Jurisdiction Scoped: {user?.role}</span>
            </div>
            <h2 className="text-xl font-bold tracking-tight">
              Welcome, {user?.full_name || 'Officer'}
            </h2>
            <p className="text-sm text-slate-300 mt-0.5">
              Authorized Operational Station: <span className="font-semibold text-white">{user?.station || user?.district || 'Headquarters'}</span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              onClick={openFIRModal}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow transition-colors flex items-center gap-1.5"
            >
              <span>{t.nav.newCaseIntake}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <Link
              to="/ai-fir-assistance"
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-blue-300 border border-blue-500/30 rounded-lg text-xs font-semibold shadow transition-colors"
            >
              {t.nav.aiFirAssistance}
            </Link>
          </div>
        </div>
      </div>

      {/* ── QUICK ACCESS ──────────────────────────────────────────────────── */}
      <div>
        <div className="mb-3">
          <h2 className="text-base font-bold text-slate-800 tracking-tight">QUICK ACCESS</h2>
          <p className="text-xs text-slate-500 mt-0.5">Access essential FIR and case intelligence features quickly.</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {/* Card 1 — Existing / Old FIRs */}
          <Link
            to="/cases"
            aria-label="View existing and old FIRs"
            className="group flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md hover:border-blue-300 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 cursor-pointer"
          >
            <div className="p-5 flex flex-col gap-3 flex-1">
              <div className="w-11 h-11 rounded-lg bg-blue-50 text-blue-700 flex items-center justify-center group-hover:bg-blue-100 transition-colors">
                <FolderSearch className="w-5 h-5" aria-hidden="true" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-bold text-slate-800 mb-1 group-hover:text-blue-800 transition-colors flex flex-wrap items-center gap-1.5 leading-snug">
                  <span>Existing / Old FIRs</span>
                  <span className="text-xs font-semibold text-slate-500 font-['Noto_Sans_Telugu',sans-serif]">— పాత FIRలు</span>
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">View, search, and review previously registered FIRs.</p>
              </div>
            </div>
            <div className="px-5 pb-4">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-700 group-hover:text-blue-900 transition-colors">
                View Existing FIRs
                <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
              </span>
            </div>
          </Link>

          {/* Card 2 — New FIRs */}
          <Link
            to="/intake"
            aria-label="Register a new FIR"
            className="group flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md hover:border-emerald-300 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 cursor-pointer"
          >
            <div className="p-5 flex flex-col gap-3 flex-1">
              <div className="w-11 h-11 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center group-hover:bg-emerald-100 transition-colors">
                <FilePlus className="w-5 h-5" aria-hidden="true" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-bold text-slate-800 mb-1 group-hover:text-emerald-800 transition-colors flex flex-wrap items-center gap-1.5 leading-snug">
                  <span>New FIRs</span>
                  <span className="text-xs font-semibold text-slate-500 font-['Noto_Sans_Telugu',sans-serif]">— కొత్త FIRలు</span>
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">Register a new FIR and upload relevant case documents.</p>
              </div>
            </div>
            <div className="px-5 pb-4">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 group-hover:text-emerald-900 transition-colors">
                Register New FIR
                <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
              </span>
            </div>
          </Link>

          {/* Card 3 — Laws & Sections */}
          <Link
            to="/legal"
            aria-label="Explore laws and statutory sections"
            className="group flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md hover:border-amber-300 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 cursor-pointer"
          >
            <div className="p-5 flex flex-col gap-3 flex-1">
              <div className="w-11 h-11 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center group-hover:bg-amber-100 transition-colors">
                <Scale className="w-5 h-5" aria-hidden="true" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-bold text-slate-800 mb-1 group-hover:text-amber-800 transition-colors flex flex-wrap items-center gap-1.5 leading-snug">
                  <span>Laws & Sections</span>
                  <span className="text-xs font-semibold text-slate-500 font-['Noto_Sans_Telugu',sans-serif]">— చట్టాలు మరియు సెక్షన్లు</span>
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">Review applicable laws and receive statutory-section assistance.</p>
              </div>
            </div>
            <div className="px-5 pb-4">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-700 group-hover:text-amber-900 transition-colors">
                Explore Laws & Sections
                <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
              </span>
            </div>
          </Link>

          {/* Card 4 — AI FIR Chatbot */}
          <Link
            to="/ai-fir-assistance"
            aria-label="Open AI FIR Assistance chatbot"
            className="group flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md hover:border-indigo-300 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 cursor-pointer"
          >
            <div className="p-5 flex flex-col gap-3 flex-1">
              <div className="w-11 h-11 rounded-lg bg-indigo-50 text-indigo-700 flex items-center justify-center group-hover:bg-indigo-100 transition-colors">
                <MessageCircle className="w-5 h-5" aria-hidden="true" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-bold text-slate-800 mb-1 group-hover:text-indigo-800 transition-colors flex flex-wrap items-center gap-1.5 leading-snug">
                  <span>AI FIR Chatbot</span>
                  <span className="text-xs font-semibold text-slate-500 font-['Noto_Sans_Telugu',sans-serif]">— AI FIR చాట్బాట్</span>
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">Ask questions about an uploaded FIR or authorized case records.</p>
              </div>
            </div>
            <div className="px-5 pb-4">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-700 group-hover:text-indigo-900 transition-colors">
                Ask AI Assistant
                <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
              </span>
            </div>
          </Link>
        </div>
      </div>
      {/* ── END QUICK ACCESS ──────────────────────────────────────────────── */}

      {/* Primary KPI Grid — shows skeletons immediately, fills in when data arrives */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          <>
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
          </>
        ) : (
          <>
            <Link
              to="/cases"
              aria-label="View all Total Scoped Cases"
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between hover:border-blue-400 hover:shadow-md transition-all group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 cursor-pointer block"
            >
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase group-hover:text-blue-600 transition-colors">Total Scoped Cases</p>
                <h3 className="text-2xl font-bold text-slate-900 mt-1">{data?.total_cases || 0}</h3>
                <span className="text-[11px] text-slate-400 group-hover:text-slate-600 transition-colors">Recorded within your jurisdiction &rarr;</span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center group-hover:bg-blue-600 group-hover:text-white transition-all shadow-sm">
                <FolderOpen className="w-6 h-6" />
              </div>
            </Link>

            <Link
              to="/cases?status=IN_REVIEW"
              aria-label="View Under Review cases"
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between hover:border-amber-400 hover:shadow-md transition-all group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 cursor-pointer block"
            >
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase group-hover:text-amber-600 transition-colors">Under Review</p>
                <h3 className="text-2xl font-bold text-amber-600 mt-1">{statusCounts['IN_REVIEW'] || 0}</h3>
                <span className="text-[11px] text-slate-400 group-hover:text-slate-600 transition-colors">Pending field verification &rarr;</span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center group-hover:bg-amber-600 group-hover:text-white transition-all shadow-sm">
                <Clock className="w-6 h-6" />
              </div>
            </Link>

            <Link
              to="/cases?status=APPROVED"
              aria-label="View Approved FIRs"
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between hover:border-emerald-400 hover:shadow-md transition-all group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 cursor-pointer block"
            >
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase group-hover:text-emerald-600 transition-colors">Approved FIRs</p>
                <h3 className="text-2xl font-bold text-emerald-600 mt-1">{statusCounts['APPROVED'] || 0}</h3>
                <span className="text-[11px] text-slate-400 group-hover:text-slate-600 transition-colors">Court filing ready &rarr;</span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center group-hover:bg-emerald-600 group-hover:text-white transition-all shadow-sm">
                <CheckCircle className="w-6 h-6" />
              </div>
            </Link>

            <Link
              to="/cases?status=DRAFT"
              aria-label="View Pending Draft cases"
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between hover:border-indigo-400 hover:shadow-md transition-all group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 cursor-pointer block"
            >
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase group-hover:text-indigo-600 transition-colors">Pending Drafts</p>
                <h3 className="text-2xl font-bold text-indigo-600 mt-1">{statusCounts['DRAFT'] !== undefined ? statusCounts['DRAFT'] : (data?.pending_drafts || 0)}</h3>
                <span className="text-[11px] text-slate-400 group-hover:text-slate-600 transition-colors">
                  {statusCounts['DRAFT'] !== undefined ? 'Saved FIR drafts • Click to view &rarr;' : 'Case diaries & chargesheets &rarr;'}
                </span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center group-hover:bg-indigo-600 group-hover:text-white transition-all shadow-sm">
                <FileText className="w-6 h-6" />
              </div>
            </Link>
          </>
        )}
      </div>

      {/* Contraband Breakdown & District Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Contraband Seizure Breakdown */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <h3 className="font-bold text-sm text-slate-800 mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue-600" />
            Contraband Seizures by Volume
          </h3>
          <div className="space-y-3">
            {data?.contraband_stats?.map((item: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-100">
                <div>
                  <h4 className="font-semibold text-xs text-slate-800">{item.contraband}</h4>
                  {item.contraband === 'Unknown' ? (
                    <Link to="/cases?contraband=unknown" className="text-[11px] text-orange-700 font-semibold hover:underline">
                      {item.cases} cases with no contraband recorded — review them
                    </Link>
                  ) : (
                    <p className="text-[11px] text-slate-500">{item.cases} Recorded Cases</p>
                  )}
                </div>
                <div className="text-right">
                  <span className="font-bold text-sm text-blue-700">{item.total_quantity}</span>
                  <span className="text-[11px] text-slate-500 ml-1">Units</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* District Caseload or Quick Verification Panel */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="font-bold text-sm text-slate-800 mb-4 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-amber-600" />
              Action Items & Verification Queue
            </h3>
            <div className="space-y-3">
              <div className="p-3.5 bg-amber-50/60 rounded-lg border border-amber-200/60 flex items-start justify-between">
                <div>
                  <h4 className="font-semibold text-xs text-amber-900">Extracted Fields Awaiting Human Sign-off</h4>
                  <p className="text-[11px] text-amber-700 mt-0.5">
                    {data?.pending_verifications || 0} fields extracted by AI require officer verification.
                  </p>
                </div>
                <Link
                  to="/cases"
                  className="px-2.5 py-1 text-xs font-semibold bg-amber-600 text-white rounded hover:bg-amber-700"
                >
                  Review
                </Link>
              </div>

              <div className="p-3.5 bg-blue-50/60 rounded-lg border border-blue-200/60 flex items-start justify-between">
                <div>
                  <h4 className="font-semibold text-xs text-blue-900">Entity Duplicate Resolution</h4>
                  <p className="text-[11px] text-blue-700 mt-0.5">
                    Review suspect person and vehicle candidate duplicates in the resolution queue.
                  </p>
                </div>
                <Link
                  to="/entity-review"
                  className="px-2.5 py-1 text-xs font-semibold bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  Examine
                </Link>
              </div>

              <div className="p-3.5 bg-emerald-50/60 rounded-lg border border-emerald-200/60 flex items-start justify-between">
                <div>
                  <h4 className="font-semibold text-xs text-emerald-900">Cryptographic Audit Chain</h4>
                  <p className="text-[11px] text-emerald-700 mt-0.5">
                    Append-only SHA-256 hash chain is continuously monitored for tampering.
                  </p>
                </div>
                <Link
                  to="/audit-trail"
                  className="px-2.5 py-1 text-xs font-semibold bg-emerald-600 text-white rounded hover:bg-emerald-700"
                >
                  Verify
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

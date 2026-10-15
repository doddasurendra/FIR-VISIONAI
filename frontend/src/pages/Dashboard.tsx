import React, { useEffect, useState } from 'react';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
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
  ArrowRight
} from 'lucide-react';
import { Link } from 'react-router-dom';

export const Dashboard: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchKPIs = async () => {
      try {
        const res = await api.get('/analytics/dashboard');
        setData(res.data);
      } catch (e) {
        console.error('Error loading dashboard KPIs:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchKPIs();
  }, [user]);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
      </div>
    );
  }

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
            <Link
              to="/intake"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow transition-colors flex items-center gap-1.5"
            >
              <span>{t.nav.newCaseIntake}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link
              to="/ai-fir-assistance"
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-blue-300 border border-blue-500/30 rounded-lg text-xs font-semibold shadow transition-colors"
            >
              {t.nav.aiFirAssistance}
            </Link>
          </div>
        </div>
      </div>

      {/* Primary KPI Grid (Database-Calculated Numbers) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Total Scoped Cases</p>
            <h3 className="text-2xl font-bold text-slate-900 mt-1">{data?.total_cases || 0}</h3>
            <span className="text-[11px] text-slate-400">Recorded within your jurisdiction</span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
            <FolderOpen className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Under Review</p>
            <h3 className="text-2xl font-bold text-amber-600 mt-1">{statusCounts['IN_REVIEW'] || 0}</h3>
            <span className="text-[11px] text-slate-400">Pending field verification</span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
            <Clock className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Approved FIRs</p>
            <h3 className="text-2xl font-bold text-emerald-600 mt-1">{statusCounts['APPROVED'] || 0}</h3>
            <span className="text-[11px] text-slate-400">Court filing ready</span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
            <CheckCircle className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Pending Drafts</p>
            <h3 className="text-2xl font-bold text-indigo-600 mt-1">{data?.pending_drafts || 0}</h3>
            <span className="text-[11px] text-slate-400">Case diaries & chargesheets</span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <FileText className="w-6 h-6" />
          </div>
        </div>
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
                  <p className="text-[11px] text-slate-500">{item.cases} Recorded Cases</p>
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

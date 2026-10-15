import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  BarChart3,
  TrendingUp,
  AlertTriangle,
  User,
  Shield,
  HelpCircle,
  FileText
} from 'lucide-react';

export const ReportsAnalytics: React.FC = () => {
  const { t } = useLanguage();
  const [repeatOffenders, setRepeatOffenders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        setLoading(true);
        const res = await api.get('/analytics/repeat-offenders');
        setRepeatOffenders(res.data);
      } catch (e) {
        console.error('Failed to load repeat offender analytics:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, []);

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-blue-600" />
          <span>{t.nav.reportsAnalytics}</span>
        </h2>
        <p className="text-xs text-slate-500">
          Section 17: Explainable Repeat-Offender Pattern Analysis & Risk Scoring (Review Aid Only)
        </p>
      </div>

      {/* Accuracy & Ethics Governance Alert (Non-negotiable requirement from Section 17!) */}
      <div className="bg-amber-50 border border-amber-200 text-amber-900 p-4 rounded-xl text-xs space-y-1">
        <h4 className="font-bold flex items-center gap-1.5 text-amber-950">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <span>Statutory Governance & Risk Scoring Disclaimer</span>
        </h4>
        <p className="leading-relaxed">
          In strict accordance with legal governance rules, risk scores are explainable decision-support review aids based exclusively on verified historical offence counts and network degree. They do not constitute an autonomous judgment, prediction of guilt, or criminal classification without judicial trial.
        </p>
      </div>

      {/* Repeat Offenders Cards Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-bold text-sm text-slate-800">
            Detected Repeat-Offender Profiles ({repeatOffenders.length})
          </h3>
          <span className="text-xs text-slate-400">Ranked by Recidivism Weight</span>
        </div>

        {loading ? (
          <div className="p-12 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : repeatOffenders.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-xs">
            No repeat offenders identified in current jurisdiction scope.
          </div>
        ) : (
          <div className="p-4 space-y-3">
            {repeatOffenders.map((offender, idx) => (
              <div
                key={idx}
                className="p-4 bg-slate-50 rounded-xl border border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs"
              >
                <div className="space-y-1.5 flex-1">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold">
                      <User className="w-4 h-4" />
                    </div>
                    <h4 className="font-bold text-sm text-slate-900">{offender.name}</h4>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                        offender.risk_level === 'HIGH'
                          ? 'bg-red-50 text-red-700 border-red-200'
                          : offender.risk_level === 'MEDIUM'
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      }`}
                    >
                      Risk: {offender.risk_level} ({offender.risk_score})
                    </span>
                  </div>

                  {/* Explainable Factor Pills */}
                  <div className="space-y-1 pt-1">
                    <span className="text-[11px] font-semibold text-slate-500 block">Contributing Factors:</span>
                    {offender.risk_factors?.map((rf: string, rfIdx: number) => (
                      <p key={rfIdx} className="text-slate-700 text-[11px]">
                        • {rf}
                      </p>
                    ))}
                  </div>
                </div>

                {/* Associated Cases Pills */}
                <div className="text-left md:text-right space-y-1.5">
                  <span className="text-[11px] font-semibold text-slate-500 block">
                    Linked Case Reports ({offender.offence_count}):
                  </span>
                  <div className="flex flex-wrap md:justify-end gap-1.5">
                    {offender.associated_cases?.map((ac: any, cIdx: number) => (
                      <span
                        key={cIdx}
                        className="font-mono text-[10px] bg-white text-blue-700 font-bold px-2 py-1 rounded border border-slate-200 shadow-2xs"
                      >
                        {ac.fir_number}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

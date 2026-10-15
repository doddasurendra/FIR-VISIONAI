import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  Sparkles,
  RefreshCw,
  FileText,
  Languages,
  Calendar,
  MapPin,
  Clock
} from 'lucide-react';

export const AICaseSummaries: React.FC = () => {
  const { t, language, setLanguage } = useLanguage();
  const [cases, setCases] = useState<any[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>('');
  const [summaryData, setSummaryData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchCases = async () => {
      try {
        const res = await api.get('/cases/');
        setCases(res.data);
        if (res.data.length > 0) {
          setSelectedCaseId(res.data[0].id);
        }
      } catch (e) {
        console.error('Failed to load cases:', e);
      }
    };
    fetchCases();
  }, []);

  const fetchSummary = async (caseId: string, regen = false) => {
    if (!caseId) return;
    try {
      setLoading(true);
      const res = await api.get(`/generation/case/${caseId}/summary`, {
        params: { language, regenerate: regen }
      });
      setSummaryData(res.data);
    } catch (e) {
      console.error('Failed to fetch summary:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCaseId) {
      fetchSummary(selectedCaseId);
    }
  }, [selectedCaseId, language]);

  const selectedCase = cases.find((c) => c.id === selectedCaseId);

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-blue-600" />
            <span>{t.nav.aiCaseSummaries}</span>
          </h2>
          <p className="text-xs text-slate-500">
            Component 2: Grounded 3 to 5 sentence executive summaries with caching & multilingual generation.
          </p>
        </div>

        {/* Case Selector */}
        <div className="flex items-center space-x-2 text-xs">
          <span className="font-semibold text-slate-600">Select Case:</span>
          <select
            value={selectedCaseId}
            onChange={(e) => setSelectedCaseId(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-1.5 bg-white text-slate-800 font-medium focus:ring-2 focus:ring-blue-500"
          >
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.fir_number} ({c.offence_nature?.slice(0, 25)}...)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Main Summary Display Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-5">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
              {selectedCase?.fir_number}
            </span>
            <span className="text-[10px] font-bold bg-purple-100 text-purple-800 px-2 py-0.5 rounded">
              {t.common.aiGenerated}
            </span>
          </div>

          <button
            onClick={() => fetchSummary(selectedCaseId, true)}
            disabled={loading}
            className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-blue-600' : ''}`} />
            <span>Regenerate</span>
          </button>
        </div>

        {/* Summary Content Body */}
        {loading ? (
          <div className="p-8 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="text-xs text-slate-500 mt-2">Generating executive summary from case evidence...</p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-slate-50 p-5 rounded-xl border border-slate-200 text-slate-800 text-xs sm:text-sm leading-relaxed font-sans">
              {summaryData?.summary || 'No summary available.'}
            </div>

            <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-100">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                Language: <strong className="text-slate-600 uppercase">{language}</strong> (Cached response)
              </span>
              <span>Grounding: Strict factual evidence from recorded FIR</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

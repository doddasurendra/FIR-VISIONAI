import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import {
  Scale,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ExternalLink,
  BookOpen,
  HelpCircle,
  Clock,
  ShieldCheck
} from 'lucide-react';

export const LegalSectionAssistance: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const urlCaseId = searchParams.get('caseId');

  const [cases, setCases] = useState<any[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(urlCaseId || '');
  const [recommendations, setRecommendations] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [decisionModal, setDecisionModal] = useState<any>(null);
  const [decisionReason, setDecisionReason] = useState('Grounded by recorded material facts and seizure evidence');
  const [savingDecision, setSavingDecision] = useState(false);

  useEffect(() => {
    const fetchCases = async () => {
      try {
        const res = await api.get('/cases/');
        setCases(res.data);
        if (!selectedCaseId && res.data.length > 0) {
          setSelectedCaseId(res.data[0].id);
        }
      } catch (e) {
        console.error('Failed to load cases:', e);
      }
    };
    fetchCases();
  }, []);

  const fetchRecommendations = async (caseId: string) => {
    if (!caseId) return;
    try {
      setLoading(true);
      const res = await api.get(`/legal/recommend/${caseId}`);
      setRecommendations(res.data);
    } catch (e) {
      console.error('Failed to load legal recommendations:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCaseId) {
      fetchRecommendations(selectedCaseId);
    }
  }, [selectedCaseId]);

  const handleDecisionSubmit = async (decision: 'ACCEPTED' | 'REJECTED') => {
    if (!decisionModal || !selectedCaseId) return;
    try {
      setSavingDecision(true);
      await api.post('/legal/decision', {
        case_id: selectedCaseId,
        legal_corpus_id: decisionModal.legal_corpus_id,
        decision,
        reason: decisionReason
      });
      setDecisionModal(null);
      await fetchRecommendations(selectedCaseId);
    } catch (e) {
      console.error('Failed to save legal decision:', e);
    } finally {
      setSavingDecision(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Scale className="w-5 h-5 text-blue-600" />
            <span>{t.nav.legalSectionAssistance}</span>
          </h2>
          <p className="text-xs text-slate-500">
            Section 27 Case-Type Classification & Fact-to-Element Legal Corpus Matching
          </p>
        </div>

        {/* Case Selector Dropdown */}
        <div className="flex items-center space-x-2 text-xs">
          <span className="font-semibold text-slate-600">Select Case:</span>
          <select
            value={selectedCaseId}
            onChange={(e) => setSelectedCaseId(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-1.5 bg-white text-slate-800 font-medium focus:ring-2 focus:ring-blue-500"
          >
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.fir_number} ({c.offence_nature?.slice(0, 30)}...)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Date & Legal Regime Banner */}
      {recommendations && (
        <div className="bg-slate-900 text-white p-4 rounded-xl shadow-sm border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-200">Applicable Statutory Regime:</span>
              <span className="font-mono px-2 py-0.5 rounded bg-blue-600/30 text-blue-300 border border-blue-500/30 font-semibold">
                {recommendations.applicable_regime}
              </span>
            </div>
            <p className="text-slate-400">
              Offence Occurrence Date: <strong className="text-white">{recommendations.offence_date || 'Under Investigation'}</strong> |
              Transition Rule: BNS 2023 applies to incidents on or after 1 July 2024.
            </p>
          </div>
          <div className="bg-slate-800 px-3 py-2 rounded-lg border border-slate-700 text-[11px] text-amber-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>AI Decision Support: Officer sign-off is statutory requirement.</span>
          </div>
        </div>
      )}

      {/* Recommendations Cards List */}
      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="text-xs text-slate-500 mt-2">Evaluating case facts against primary legal corpus...</p>
        </div>
      ) : recommendations?.candidates?.length === 0 ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200 text-slate-500 text-xs">
          <Scale className="w-10 h-10 text-slate-300 mx-auto mb-2" />
          <p className="font-semibold text-slate-700">No candidate sections met the evidence threshold</p>
          <p className="text-slate-400 mt-0.5">Essential statutory ingredients could not be established from recorded facts.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {recommendations?.candidates?.map((cand: any, idx: number) => (
            <div
              key={idx}
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 border-b border-slate-100 pb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                      {cand.section_number}
                    </span>
                    <span className="text-xs font-semibold text-slate-600">{cand.act_name}</span>
                    <span className="text-[10px] bg-amber-50 text-amber-800 border border-amber-200 font-bold px-2 py-0.5 rounded">
                      {cand.status_label}
                    </span>
                  </div>
                  <h3 className="font-bold text-sm text-slate-900">{cand.section_title}</h3>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setDecisionModal(cand)}
                    className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1 transition-colors"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Accept Section</span>
                  </button>
                  <button
                    onClick={() => {
                      setDecisionModal(cand);
                      setDecisionReason('Essential statutory elements unproven or inapplicable.');
                    }}
                    className="px-3 py-1.5 bg-slate-100 hover:bg-red-50 text-slate-700 hover:text-red-700 rounded-lg text-xs font-semibold border border-slate-300 transition-colors"
                  >
                    <span>Reject</span>
                  </button>
                </div>
              </div>

              {/* Statutory Full Text Box */}
              <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
                <span className="text-[11px] font-bold text-slate-500 block mb-1">
                  Verified Statutory Text ({cand.act_name}):
                </span>
                <p className="text-slate-800 italic leading-relaxed">"{cand.full_text}"</p>
                {cand.penalty_text && (
                  <p className="mt-2 text-[11px] font-semibold text-red-700">
                    Prescribed Statutory Penalty: {cand.penalty_text}
                  </p>
                )}
              </div>

              {/* Facts vs Missing Ingredients Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                {/* Matched Facts */}
                <div className="p-3 bg-emerald-50/60 rounded-lg border border-emerald-200/60 space-y-1.5">
                  <h4 className="font-bold text-emerald-900 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Evidenced Facts in FIR (Matched Ingredients)</span>
                  </h4>
                  {cand.matched_facts?.map((f: string, fIdx: number) => (
                    <p key={fIdx} className="text-emerald-800 text-[11px]">
                      • {f}
                    </p>
                  ))}
                </div>

                {/* Missing / Unproven Elements */}
                <div className="p-3 bg-amber-50/60 rounded-lg border border-amber-200/60 space-y-1.5">
                  <h4 className="font-bold text-amber-900 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                    <span>Statutory Ingredients Not Yet Established / Pending</span>
                  </h4>
                  {cand.missing_elements?.length > 0 ? (
                    cand.missing_elements.map((m: string, mIdx: number) => (
                      <p key={mIdx} className="text-amber-800 text-[11px]">
                        • {m}
                      </p>
                    ))
                  ) : (
                    <p className="text-emerald-700 text-[11px] italic">
                      All primary prima-facie ingredients supported by recorded seizure.
                    </p>
                  )}
                </div>
              </div>

              {/* Provenance Link */}
              <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                <span>Effective Date: {cand.effective_date || 'Standard Statute'}</span>
                {cand.source_url && (
                  <a
                    href={cand.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-600 hover:underline flex items-center gap-1"
                  >
                    <span>India Code Official Gazette Citation</span>
                    <ExternalLink className="w-2.5 h-2.5" />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Decision Reason Modal */}
      {decisionModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 border border-slate-200">
            <h3 className="font-bold text-sm text-slate-900">
              Confirm Decision: {decisionModal.section_number} ({decisionModal.act_name})
            </h3>
            <p className="text-xs text-slate-500">
              Your decision will be recorded in the append-only cryptographic audit trail along with your reasoning.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Officer Review Reasoning:
              </label>
              <textarea
                rows={3}
                value={decisionReason}
                onChange={(e) => setDecisionReason(e.target.value)}
                className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setDecisionModal(null)}
                className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={savingDecision}
                onClick={() => handleDecisionSubmit('ACCEPTED')}
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-500 shadow-sm"
              >
                {savingDecision ? 'Saving...' : 'Accept as Applicable'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

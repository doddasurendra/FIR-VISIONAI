import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  Scale,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ExternalLink,
  RefreshCw,
  ShieldCheck,
  FileText,
} from 'lucide-react';

const errorText = (e: any, fallback: string) => {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (e?.code === 'ECONNABORTED') return `${fallback} (the server did not answer in time).`;
  return e?.message || fallback;
};

const TEXT_BADGE: Record<string, { label: string; cls: string }> = {
  VERIFIED_STATUTORY_TEXT: { label: 'Verified Statutory Text', cls: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  UNVERIFIED_SUMMARY: { label: 'Unverified summary', cls: 'bg-amber-50 text-amber-800 border-amber-200' },
  NOT_IN_CORPUS: { label: 'Not in the legal corpus', cls: 'bg-slate-100 text-slate-600 border-slate-200' },
};

export const LegalSectionAssistance: React.FC = () => {
  const { t } = useLanguage();
  const [searchParams] = useSearchParams();
  const urlCaseId = searchParams.get('caseId');

  const [cases, setCases] = useState<any[]>([]);
  const [casesError, setCasesError] = useState<string | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(urlCaseId || '');
  const [recommendations, setRecommendations] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decisionModal, setDecisionModal] = useState<{ cand: any; decision: 'ACCEPTED' | 'REJECTED' } | null>(null);
  const [decisionReason, setDecisionReason] = useState('');
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [savingDecision, setSavingDecision] = useState(false);
  const latestRequest = useRef(0);

  const fetchCases = useCallback(async () => {
    setCasesError(null);
    try {
      const res = await api.get('/cases/', { timeout: 30000 });
      setCases(res.data);
      setSelectedCaseId((current) => current || res.data[0]?.id || '');
    } catch (e: any) {
      setCasesError(errorText(e, 'Cases could not be loaded'));
    }
  }, []);

  useEffect(() => { fetchCases(); }, [fetchCases]);

  const fetchRecommendations = useCallback(async (caseId: string) => {
    if (!caseId) return;
    const requestId = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/legal/recommend/${caseId}`, { timeout: 45000 });
      if (requestId === latestRequest.current) setRecommendations(res.data);
    } catch (e: any) {
      if (requestId === latestRequest.current) {
        setRecommendations(null);
        setError(errorText(e, 'Legal suggestions could not be loaded'));
      }
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedCaseId) fetchRecommendations(selectedCaseId);
  }, [selectedCaseId, fetchRecommendations]);

  const openDecision = (cand: any, decision: 'ACCEPTED' | 'REJECTED') => {
    setDecisionError(null);
    setDecisionReason(decision === 'ACCEPTED'
      ? 'Grounded by recorded material facts and seizure evidence'
      : 'Essential statutory elements unproven or inapplicable.');
    setDecisionModal({ cand, decision });
  };

  const handleDecisionSubmit = async () => {
    if (!decisionModal || !selectedCaseId) return;
    try {
      setSavingDecision(true);
      setDecisionError(null);
      await api.post('/legal/decision', {
        case_id: selectedCaseId,
        legal_corpus_id: decisionModal.cand.legal_corpus_id,
        decision: decisionModal.decision,
        reason: decisionReason,
      });
      setDecisionModal(null);
      await fetchRecommendations(selectedCaseId);
    } catch (e: any) {
      setDecisionError(errorText(e, 'The decision could not be saved'));
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
            Sections recorded in the FIR, and provisions whose ingredients match the facts, for officer review
          </p>
        </div>

        <div className="flex items-center space-x-2 text-xs">
          <span className="font-semibold text-slate-600">Select Case:</span>
          <select
            value={selectedCaseId}
            onChange={(e) => setSelectedCaseId(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-1.5 bg-white text-slate-800 font-medium focus:ring-2 focus:ring-blue-500 max-w-[320px]"
          >
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.fir_number} ({c.offence_nature?.slice(0, 30)}{c.offence_nature?.length > 30 ? '…' : ''})
              </option>
            ))}
          </select>
        </div>
      </div>

      {casesError && (
        <div className="p-3 rounded-xl border bg-red-50 border-red-200 text-red-800 text-xs flex items-center justify-between gap-3" role="alert">
          <span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{casesError}</span>
          <button onClick={fetchCases} className="flex items-center gap-1 px-3 py-1.5 bg-white border border-red-200 rounded-md font-semibold hover:bg-red-100">
            <RefreshCw className="w-3.5 h-3.5" /> Retry
          </button>
        </div>
      )}

      {/* Date & Legal Regime Banner */}
      {recommendations && !loading && (
        <div className="bg-slate-900 text-white p-4 rounded-xl shadow-sm border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-slate-200">Applicable Statutory Regime:</span>
              <span className="font-mono px-2 py-0.5 rounded bg-blue-600/30 text-blue-300 border border-blue-500/30 font-semibold">
                {recommendations.applicable_regime}
              </span>
            </div>
            <p className="text-slate-400">
              Date of offence: <strong className="text-white">{recommendations.offence_date || 'not recorded'}</strong>
              {recommendations.offence_date_source && <> (from {recommendations.offence_date_source})</>} |
              BNS 2023 applies to incidents on or after 1 July 2024; the IPC before.
            </p>
            {recommendations.recorded_fir_sections?.length > 0 && (
              <p className="text-slate-400">Recorded in the FIR: <span className="text-white">{recommendations.recorded_fir_sections.join(', ')}</span></p>
            )}
          </div>
          <div className="bg-slate-800 px-3 py-2 rounded-lg border border-slate-700 text-[11px] text-amber-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>Decision support only: officer sign-off is a statutory requirement.</span>
          </div>
        </div>
      )}

      {error && !loading && (
        <div className="p-4 rounded-xl border bg-red-50 border-red-200 text-red-800 text-xs flex items-center justify-between gap-3" role="alert">
          <span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{error}</span>
          <button onClick={() => fetchRecommendations(selectedCaseId)}
            className="flex items-center gap-1 px-3 py-1.5 bg-white border border-red-200 rounded-md font-semibold hover:bg-red-100">
            <RefreshCw className="w-3.5 h-3.5" /> Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="text-xs text-slate-500 mt-2">Evaluating case facts against the legal corpus...</p>
        </div>
      ) : recommendations?.candidates?.length === 0 ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200 text-slate-500 text-xs">
          <Scale className="w-10 h-10 text-slate-300 mx-auto mb-2" />
          <p className="font-semibold text-slate-700">No sections are recorded in this FIR and none matched its facts</p>
          <p className="text-slate-400 mt-0.5">Check the case narrative and offence details, then try again.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {recommendations?.candidates?.map((cand: any, idx: number) => {
            const badge = TEXT_BADGE[cand.text_status] || TEXT_BADGE.UNVERIFIED_SUMMARY;
            return (
              <div key={`${cand.act_name}-${cand.section_number}-${idx}`}
                className={`bg-white p-5 rounded-xl border shadow-sm space-y-4 ${cand.regime_applies === false ? 'border-amber-300' : 'border-slate-200'}`}>
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 border-b border-slate-100 pb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-mono text-xs font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">{cand.section_number}</span>
                      <span className="text-xs font-semibold text-slate-600">{cand.act_name}</span>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${cand.is_recorded_in_fir
                        ? 'bg-blue-50 text-blue-800 border-blue-200' : 'bg-violet-50 text-violet-800 border-violet-200'}`}>
                        {cand.label || cand.status_label}
                      </span>
                      {cand.officer_decision === 'ACCEPTED' && <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-600 text-white">Accepted</span>}
                      {cand.officer_decision === 'REJECTED' && <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-600 text-white">Rejected</span>}
                    </div>
                    <h3 className="font-bold text-sm text-slate-900">{cand.section_title}</h3>
                    {cand.offence && <p className="text-[11px] text-slate-500">{cand.offence}</p>}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => openDecision(cand, 'ACCEPTED')}
                      disabled={!cand.can_accept}
                      title={cand.can_accept ? '' : 'This provision is not in the legal corpus yet'}
                      className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Accept Section</span>
                    </button>
                    <button
                      onClick={() => openDecision(cand, 'REJECTED')}
                      disabled={!cand.can_accept}
                      className="px-3 py-1.5 bg-slate-100 hover:bg-red-50 text-slate-700 hover:text-red-700 rounded-lg text-xs font-semibold border border-slate-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      <span>Reject</span>
                    </button>
                  </div>
                </div>

                {cand.warnings?.length > 0 && (
                  <div className="space-y-1">
                    {cand.warnings.map((w: string, wIdx: number) => (
                      <p key={wIdx} className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1 flex items-start gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />{w}
                      </p>
                    ))}
                  </div>
                )}

                {/* Statutory text: verified only when imported from an official source */}
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
                  <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded border mb-1.5 ${badge.cls}`}>
                    {cand.text_status === 'VERIFIED_STATUTORY_TEXT' ? <ShieldCheck className="w-3 h-3" /> : <FileText className="w-3 h-3" />}
                    {badge.label}
                  </span>
                  {cand.full_text ? (
                    <p className={`leading-relaxed ${cand.text_status === 'VERIFIED_STATUTORY_TEXT' ? 'text-slate-800 italic' : 'text-slate-600'}`}>
                      {cand.text_status === 'VERIFIED_STATUTORY_TEXT' ? `"${cand.full_text}"` : cand.full_text}
                    </p>
                  ) : (
                    <p className="text-slate-500">The text of this provision has not been imported into the legal corpus.</p>
                  )}
                  {cand.text_status === 'UNVERIFIED_SUMMARY' && (
                    <p className="mt-1 text-[10px] text-amber-700">Summary only — the official text of this Act has not been imported yet. Verify against the Gazette before relying on it.</p>
                  )}
                  {cand.penalty_text && (
                    <p className="mt-2 text-[11px] font-semibold text-red-700">Prescribed penalty: {cand.penalty_text}</p>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div className="p-3 bg-emerald-50/60 rounded-lg border border-emerald-200/60 space-y-1.5">
                    <h4 className="font-bold text-emerald-900 flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                      <span>Ingredients established by the recorded facts</span>
                    </h4>
                    {(cand.matched_ingredients || cand.matched_facts || []).length > 0 ? (
                      (cand.matched_ingredients || cand.matched_facts).map((f: string, fIdx: number) => (
                        <p key={fIdx} className="text-emerald-800 text-[11px]">• {f}</p>
                      ))
                    ) : (
                      <p className="text-slate-500 text-[11px] italic">No ingredient could be matched to the recorded facts.</p>
                    )}
                  </div>
                  <div className="p-3 bg-amber-50/60 rounded-lg border border-amber-200/60 space-y-1.5">
                    <h4 className="font-bold text-amber-900 flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                      <span>Ingredients not yet established</span>
                    </h4>
                    {(cand.missing_ingredients || cand.missing_elements || []).length > 0 ? (
                      (cand.missing_ingredients || cand.missing_elements).map((m: string, mIdx: number) => (
                        <p key={mIdx} className="text-amber-800 text-[11px]">• {m}</p>
                      ))
                    ) : (
                      <p className="text-emerald-700 text-[11px] italic">Every listed ingredient is supported by the recorded facts.</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                  <span>Effective date: {cand.effective_date || 'not recorded'}</span>
                  {cand.source_url && (
                    <a href={cand.source_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline flex items-center gap-1">
                      <span>Official source</span>
                      <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  )}
                </div>
              </div>
            );
          })}
          {recommendations?.candidates?.some((c: any) => c.officer_decision === 'ACCEPTED') && (
            <p className="text-xs text-slate-500">
              Accepted sections appear in the chargesheet under “Charges framed under laws”.{' '}
              <Link to={`/chargesheet?caseId=${selectedCaseId}`} className="text-blue-700 hover:underline">Open the chargesheet</Link>
            </p>
          )}
        </div>
      )}

      {/* Decision Modal */}
      {decisionModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 border border-slate-200">
            <h3 className="font-bold text-sm text-slate-900">
              {decisionModal.decision === 'ACCEPTED' ? 'Accept' : 'Reject'}: {decisionModal.cand.section_number} ({decisionModal.cand.act_name})
            </h3>
            <p className="text-xs text-slate-500">
              Your decision is recorded in the append-only audit trail with your reasoning.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Officer reasoning:</label>
              <textarea
                rows={3}
                value={decisionReason}
                onChange={(e) => setDecisionReason(e.target.value)}
                className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            {decisionError && <p className="text-xs text-red-700">{decisionError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setDecisionModal(null)}
                className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50">
                Cancel
              </button>
              <button type="button" disabled={savingDecision || !decisionReason.trim()} onClick={handleDecisionSubmit}
                className={`px-4 py-2 text-white rounded-lg text-xs font-semibold shadow-sm disabled:opacity-50 ${decisionModal.decision === 'ACCEPTED'
                  ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-red-600 hover:bg-red-500'}`}>
                {savingDecision ? 'Saving...' : decisionModal.decision === 'ACCEPTED' ? 'Accept as applicable' : 'Reject section'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

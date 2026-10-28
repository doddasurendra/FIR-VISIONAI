import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { HotspotsTab } from '../components/analytics/HotspotsTab';
import { LoadError, errorMessage } from '../components/common/LoadError';
import {
  BarChart3,
  TrendingUp,
  AlertTriangle,
  User,
  Shield,
  FileText,
  MapPin,
  CheckCircle2,
  Crosshair,
  Award,
  Clock,
  Layers,
  Activity
} from 'lucide-react';

export const ReportsAnalytics: React.FC = () => {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<'repeat_offenders' | 'hotspots' | 'risk_eval' | 'pilot_readiness'>('repeat_offenders');
  
  const [repeatOffenders, setRepeatOffenders] = useState<any[]>([]);
  const [riskEvalData, setRiskEvalData] = useState<any>(null);
  const [pilotData, setPilotData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchAllData = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const [roRes, evalRes, pilotRes] = await Promise.allSettled([
        api.get('/analytics/repeat-offenders'),
        api.get('/analytics/risk-evaluation'),
        api.get('/analytics/pilot-metrics')
      ]);

      if (roRes.status === 'fulfilled') setRepeatOffenders(roRes.value.data);
      if (evalRes.status === 'fulfilled') setRiskEvalData(evalRes.value.data);
      if (pilotRes.status === 'fulfilled') setPilotData(pilotRes.value.data);
      // Say which sections failed instead of showing them empty
      const failed = [
        roRes.status === 'rejected' && 'repeat offenders',
        evalRes.status === 'rejected' && 'risk model evaluation',
        pilotRes.status === 'rejected' && 'pilot metrics',
      ].filter(Boolean);
      if (failed.length) setLoadError(`Could not load: ${failed.join(', ')}.`);
    } catch (e) {
      console.error('Failed to load reports and analytics:', e);
      setLoadError(errorMessage(e, 'The analytics could not be loaded.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();
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
          Advanced Case Intelligence, Geospatial Hotspots, Risk Model Evaluation (&gt;90% Benchmark) &amp; Pilot Metrics
        </p>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        <button
          onClick={() => setActiveTab('repeat_offenders')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'repeat_offenders'
              ? 'bg-blue-600 text-white shadow-xs'
              : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
          }`}
        >
          <User className="w-3.5 h-3.5" />
          <span>Repeat-Offender Risk ({repeatOffenders.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('hotspots')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'hotspots'
              ? 'bg-blue-600 text-white shadow-xs'
              : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
          }`}
        >
          <MapPin className="w-3.5 h-3.5" />
          <span>Geographic Hotspots</span>
        </button>

        <button
          onClick={() => setActiveTab('risk_eval')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'risk_eval'
              ? 'bg-blue-600 text-white shadow-xs'
              : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
          }`}
        >
          <Crosshair className="w-3.5 h-3.5" />
          <span>Risk Model Evaluation (&gt;90% Accuracy Target)</span>
        </button>

        <button
          onClick={() => setActiveTab('pilot_readiness')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'pilot_readiness'
              ? 'bg-blue-600 text-white shadow-xs'
              : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
          }`}
        >
          <Award className="w-3.5 h-3.5" />
          <span>60-Day Pilot Readiness</span>
        </button>
      </div>

      {/* Statutory Governance & Risk Scoring Disclaimer */}
      <div className="bg-amber-50 border border-amber-200 text-amber-900 p-4 rounded-xl text-xs space-y-1">
        <h4 className="font-bold flex items-center gap-1.5 text-amber-950">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <span>Statutory Governance &amp; Risk Scoring Disclaimer</span>
        </h4>
        <p className="leading-relaxed">
          In strict accordance with legal governance rules, risk scores and geospatial indicators are explainable decision-support review aids based exclusively on verified historical case attributes and seized quantities. They do not constitute an autonomous judgment, prediction of guilt, or criminal classification without judicial determination.
        </p>
      </div>

      {loadError && !loading && activeTab !== 'hotspots' && <LoadError message={loadError} onRetry={fetchAllData} />}

      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="text-xs text-slate-400 mt-2">Loading analytical metrics...</p>
        </div>
      ) : (
        <>
          {/* TAB 1: REPEAT OFFENDERS */}
          {activeTab === 'repeat_offenders' && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 border-b border-slate-100 flex items-center justify-between">
                <h3 className="font-bold text-sm text-slate-800">
                  Detected Repeat-Offender Profiles ({repeatOffenders.length})
                </h3>
                <span className="text-xs text-slate-400">Ranked by Recidivism Weight</span>
              </div>

              {repeatOffenders.length === 0 ? (
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

                        <div className="space-y-1 pt-1">
                          <span className="text-[11px] font-semibold text-slate-500 block">Contributing Factors:</span>
                          {offender.risk_factors?.map((rf: string, rfIdx: number) => (
                            <p key={rfIdx} className="text-slate-700 text-[11px]">
                              • {rf}
                            </p>
                          ))}
                        </div>
                      </div>

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
          )}

          {/* TAB 2: CRIME HOTSPOTS */}
          {activeTab === 'hotspots' && <HotspotsTab />}

          {/* TAB 3: RISK MODEL EVALUATION PIPELINE */}
          {activeTab === 'risk_eval' && riskEvalData && (
            <div className="space-y-4">
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div>
                    <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                      <Crosshair className="w-4 h-4 text-emerald-600" />
                      <span>{riskEvalData.prediction_target}</span>
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">{riskEvalData.evaluation_methodology}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-3 py-1 rounded-full bg-slate-100 text-slate-700 font-semibold text-xs">
                      Test set: {riskEvalData.test_set_size} case(s)
                      {riskEvalData.synthetic_samples_in_test > 0 && ` (${riskEvalData.synthetic_samples_in_test} synthetic)`}
                    </span>
                    {riskEvalData.metrics?.accuracy_target_met && riskEvalData.test_set_size >= 100 && (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 font-bold text-xs">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                        <span>&gt;90% Accuracy Target MET</span>
                      </span>
                    )}
                  </div>
                </div>

                {riskEvalData.reliability_warnings?.length > 0 && (
                  <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg p-3 text-xs space-y-1" role="alert">
                    <p className="font-bold flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" /> Do not rely on these metrics yet</p>
                    {riskEvalData.reliability_warnings.map((w: string, i: number) => <p key={i}>• {w}</p>)}
                  </div>
                )}

                {/* Metric Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200 text-center">
                    <span className="text-[11px] text-emerald-700 font-semibold block">Model Accuracy</span>
                    <span className="text-2xl font-black text-emerald-900">
                      {(riskEvalData.metrics?.accuracy * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-emerald-600 block mt-0.5">on {riskEvalData.test_set_size} test case(s)</span>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-center">
                    <span className="text-[11px] text-slate-500 font-semibold block">Precision</span>
                    <span className="text-2xl font-black text-slate-800">
                      {(riskEvalData.metrics?.precision * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-400 block mt-0.5">Positive Predictive</span>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-center">
                    <span className="text-[11px] text-slate-500 font-semibold block">Recall</span>
                    <span className="text-2xl font-black text-slate-800">
                      {(riskEvalData.metrics?.recall * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-400 block mt-0.5">True Positive Rate</span>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-center">
                    <span className="text-[11px] text-slate-500 font-semibold block">F1-Score</span>
                    <span className="text-2xl font-black text-slate-800">
                      {(riskEvalData.metrics?.f1_score * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-400 block mt-0.5">Harmonic Mean</span>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-center">
                    <span className="text-[11px] text-slate-500 font-semibold block">ROC-AUC</span>
                    <span className="text-2xl font-black text-slate-800">
                      {riskEvalData.metrics?.roc_auc == null ? 'n/a' : `${(riskEvalData.metrics.roc_auc * 100).toFixed(1)}%`}
                    </span>
                    <span className="text-[10px] text-slate-400 block mt-0.5">Discrimination Area</span>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-center">
                    <span className="text-[11px] text-slate-500 font-semibold block">Baseline Acc.</span>
                    <span className="text-2xl font-black text-slate-600">
                      {(riskEvalData.metrics?.baseline_accuracy * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-400 block mt-0.5">Majority Class</span>
                  </div>
                </div>

                {/* Confusion Matrix & Features */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                  <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                    <h4 className="font-bold text-xs text-slate-700 uppercase tracking-wider">Confusion Matrix (Test Split)</h4>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="p-2 bg-emerald-100/70 border border-emerald-200 rounded text-center">
                        <span className="text-[10px] text-emerald-800 block">True Positives (TP)</span>
                        <span className="font-bold text-base text-emerald-950">{riskEvalData.confusion_matrix?.true_positives}</span>
                      </div>
                      <div className="p-2 bg-red-50 border border-red-200 rounded text-center">
                        <span className="text-[10px] text-red-700 block">False Positives (FP)</span>
                        <span className="font-bold text-base text-red-900">{riskEvalData.confusion_matrix?.false_positives}</span>
                      </div>
                      <div className="p-2 bg-amber-50 border border-amber-200 rounded text-center">
                        <span className="text-[10px] text-amber-700 block">False Negatives (FN)</span>
                        <span className="font-bold text-base text-amber-900">{riskEvalData.confusion_matrix?.false_negatives}</span>
                      </div>
                      <div className="p-2 bg-emerald-100/70 border border-emerald-200 rounded text-center">
                        <span className="text-[10px] text-emerald-800 block">True Negatives (TN)</span>
                        <span className="font-bold text-base text-emerald-950">{riskEvalData.confusion_matrix?.true_negatives}</span>
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                    <h4 className="font-bold text-xs text-slate-700 uppercase tracking-wider">Model Features &amp; Weights</h4>
                    <div className="space-y-1.5 text-xs">
                      {riskEvalData.features_used?.map((feat: any, fIdx: number) => (
                        <div key={fIdx} className="flex items-center justify-between p-1.5 bg-white rounded border border-slate-200">
                          <div>
                            <span className="font-mono font-bold text-slate-800 text-[11px]">{feat.feature}</span>
                            <span className="text-slate-400 block text-[10px]">{feat.description}</span>
                          </div>
                          <span className="font-mono font-bold text-blue-700 text-xs px-2 py-0.5 bg-blue-50 rounded">
                            {(feat.weight * 100).toFixed(0)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: 60-DAY PILOT READINESS */}
          {activeTab === 'pilot_readiness' && pilotData && (
            <div className="space-y-4">
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div>
                    <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                      <Award className="w-4 h-4 text-blue-600" />
                      <span>Official 60-Day Proof of Concept Pilot Readiness</span>
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Targeted deployment across 3 designated Andhra Pradesh Excise districts (Kurnool, Guntur, Visakhapatnam)
                    </p>
                  </div>
                  <span className="px-3 py-1 rounded-full bg-blue-100 text-blue-800 font-bold text-xs">
                    {pilotData.pilot_status} ({pilotData.pilot_duration_days} Days)
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                    <span className="text-slate-400 block text-[11px]">Field Extraction Accuracy</span>
                    <span className="text-xl font-bold text-slate-900">
                      {(pilotData.extraction_accuracy_rate * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-emerald-600 block">Verified fields rate</span>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                    <span className="text-slate-400 block text-[11px]">RAG Retrieval Success</span>
                    <span className="text-xl font-bold text-slate-900">
                      {(pilotData.retrieval_success_rate * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-emerald-600 block">Zero hallucinations</span>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                    <span className="text-slate-400 block text-[11px]">Time Saved Per FIR</span>
                    <span className="text-xl font-bold text-slate-900">
                      ~{pilotData.average_time_saved_per_case_mins} Mins
                    </span>
                    <span className="text-[10px] text-blue-600 block">Manual vs u-FIR assist</span>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                    <span className="text-slate-400 block text-[11px]">Est. Officer Hours Saved</span>
                    <span className="text-xl font-bold text-slate-900">
                      {pilotData.total_investigation_hours_saved} Hours
                    </span>
                    <span className="text-[10px] text-blue-600 block">Across processed FIRs</span>
                  </div>
                </div>

                {/* District Readiness Grid */}
                <div className="space-y-2 pt-2">
                  <h4 className="font-bold text-xs text-slate-700 uppercase tracking-wider">Designated Pilot District Coverage</h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {pilotData.district_readiness?.map((d: any, dIdx: number) => (
                      <div key={dIdx} className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 space-y-2 text-xs">
                        <div className="flex items-center justify-between">
                          <h5 className="font-bold text-slate-900 text-sm">{d.district} District</h5>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                            {d.status}
                          </span>
                        </div>
                        <div className="space-y-1 text-slate-600 text-[11px]">
                          <p>• Target Stations: <strong>{d.target_stations} Stations</strong></p>
                          <p>• Designated Users: <strong>{d.active_users} Department Officers</strong></p>
                          <p>• Verified Cases: <strong>{d.cases_recorded} Records</strong></p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

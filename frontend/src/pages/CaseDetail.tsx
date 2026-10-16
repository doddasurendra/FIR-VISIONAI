import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { PDFViewerModal } from '../components/pdf/PDFViewerModal';
import {
  FileText,
  Scale,
  BookOpen,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  Eye,
  Edit2,
  Trash2,
  User,
  Car,
  Calendar,
  MapPin,
  Check,
  Clock,
  Loader2,
  ShieldCheck,
  Activity
} from 'lucide-react';

export const CaseDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { t } = useLanguage();
  const { user } = useAuth();

  const [caseData, setCaseData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeViewerDocId, setActiveViewerDocId] = useState<string | null>(null);
  const [overrideField, setOverrideField] = useState<any>(null);
  const [overrideValue, setOverrideValue] = useState('');
  const [savingOverride, setSavingOverride] = useState(false);
  const [workflowStages, setWorkflowStages] = useState<any[]>([]);
  const [approvingCase, setApprovingCase] = useState(false);
  const [approveMsg, setApproveMsg] = useState<string | null>(null);

  const fetchDetail = async () => {
    try {
      setLoading(true);
      const res = await api.get(`/cases/${id}`);
      setCaseData(res.data);
    } catch (e) {
      console.error('Failed to load case details:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchWorkflow = async () => {
    if (!id) return;
    try {
      const res = await api.get(`/folders/workflow/${id}`);
      setWorkflowStages(res.data || []);
    } catch (_e) {
      // Workflow may not be available for older cases — silently skip
    }
  };

  const handleApproveCase = async () => {
    if (!id) return;
    try {
      setApprovingCase(true);
      setApproveMsg(null);
      await api.post(`/cases/${id}/approve`);
      setApproveMsg('Case approved and marked complete.');
      await fetchDetail();
      await fetchWorkflow();
    } catch (e: any) {
      setApproveMsg('Approval failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setApprovingCase(false);
    }
  };

  useEffect(() => {
    if (id) {
      fetchDetail();
      fetchWorkflow();
    }
  }, [id]);

  const handleFieldOverrideSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!overrideField || !id) return;
    try {
      setSavingOverride(true);
      await api.post(`/cases/${id}/fields/${overrideField.id}/override`, {
        human_override_value: overrideValue,
        verification_status: 'OVERRIDDEN'
      });
      setOverrideField(null);
      await fetchDetail();
    } catch (e) {
      console.error('Failed to save field override:', e);
    } finally {
      setSavingOverride(false);
    }
  };

  if (loading) {
    return (
      <div className="p-12 text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <p className="text-xs text-slate-500 mt-2">Loading case record...</p>
      </div>
    );
  }

  if (!caseData || !caseData.case) {
    return (
      <div className="p-8 bg-red-50 text-red-700 rounded-xl border border-red-200 text-sm">
        Case not found or permission denied.
      </div>
    );
  }

  const { case: c, fields, documents, entities } = caseData;

  return (
    <div className="space-y-6">
      {/* Top Banner with Quick Actions */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-xs font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
              {c.fir_number}
            </span>
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                c.status === 'APPROVED'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-amber-50 text-amber-700 border-amber-200'
              }`}
            >
              {c.status}
            </span>
          </div>
          <h2 className="text-lg font-bold text-slate-900">{c.offence_nature}</h2>
          <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-3">
            <span className="flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5 text-slate-400" />
              {c.station}, {c.district} District
            </span>
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              Reg Date: {new Date(c.registration_date).toLocaleDateString()}
            </span>
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/legal?caseId=${c.id}`}
            className="px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <Scale className="w-4 h-4" />
            <span>Suggest Legal Sections</span>
          </Link>

          <Link
            to={`/case-diary?caseId=${c.id}`}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-100 rounded-lg text-xs font-medium shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <BookOpen className="w-4 h-4" />
            <span>Draft Case Diary</span>
          </Link>

          <Link
            to={`/chargesheet?caseId=${c.id}`}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-100 rounded-lg text-xs font-medium shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <FileSpreadsheet className="w-4 h-4" />
            <span>Draft Chargesheet</span>
          </Link>

          {c.status !== 'APPROVED' && (
            <button
              onClick={handleApproveCase}
              disabled={approvingCase}
              className="px-3 py-2 bg-emerald-700 hover:bg-emerald-600 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              {approvingCase
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <ShieldCheck className="w-4 h-4" />}
              <span>{approvingCase ? 'Approving...' : 'Approve & Complete Case'}</span>
            </button>
          )}
        </div>

        {approveMsg && (
          <p className={`text-xs mt-1 px-2 py-1 rounded ${approveMsg.startsWith('Case approved') ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
            {approveMsg}
          </p>
        )}
      </div>

      {/* Case Intelligence Workflow Pipeline */}
      {workflowStages.length > 0 && (
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <h3 className="font-bold text-xs text-slate-700 flex items-center gap-1.5 mb-3">
            <Activity className="w-4 h-4 text-blue-600" />
            AI Intelligence Workflow Pipeline
          </h3>
          <div className="flex flex-wrap gap-2">
            {workflowStages.map((stage: any) => {
              const statusColor =
                stage.status === 'COMPLETED' ? 'bg-emerald-50 border-emerald-200 text-emerald-700' :
                stage.status === 'FAILED' ? 'bg-red-50 border-red-200 text-red-700' :
                stage.status === 'RUNNING' ? 'bg-blue-50 border-blue-200 text-blue-700' :
                'bg-slate-50 border-slate-200 text-slate-500';
              const icon =
                stage.status === 'COMPLETED' ? <CheckCircle2 className="w-3 h-3" /> :
                stage.status === 'FAILED' ? <AlertCircle className="w-3 h-3" /> :
                stage.status === 'RUNNING' ? <Loader2 className="w-3 h-3 animate-spin" /> :
                <Clock className="w-3 h-3" />;
              return (
                <div key={stage.stage} className={`flex items-center gap-1 px-3 py-1.5 rounded-full border text-[11px] font-semibold ${statusColor}`}>
                  {icon}
                  <span>{stage.stage.replace('_', ' ')}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Main Grid: Details + Extracted Fields Provenance */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Crime Facts & Entities */}
        <div className="lg:col-span-2 space-y-6">
          {/* Seizure Facts Card */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
            <h3 className="font-bold text-sm text-slate-800 border-b border-slate-100 pb-2.5">
              Material Seizure & Crime Particulars
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
              <div>
                <span className="text-slate-400 block text-[11px]">Contraband Type</span>
                <span className="font-semibold text-slate-800">{c.contraband_type || 'N/A'}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">Seized Quantity</span>
                <span className="font-semibold text-slate-800">{c.seized_quantity} {c.seized_unit}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">Conveyance / Vehicle</span>
                <span className="font-semibold text-slate-800 font-mono">{c.vehicle_details || 'None'}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">Offence Date</span>
                <span className="font-semibold text-slate-800">{c.offence_date ? new Date(c.offence_date).toLocaleString() : 'Under investigation'}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">Seizing Officer</span>
                <span className="font-semibold text-slate-800">{c.seizing_officer_name || 'Sub-Inspector'}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">Occurrence Location</span>
                <span className="font-semibold text-slate-800">{c.location_description || `${c.village}, ${c.mandal}`}</span>
              </div>
            </div>

            <div>
              <span className="text-slate-400 block text-[11px] mb-1">Investigation Narrative</span>
              <p className="bg-slate-50 p-3 rounded-lg text-slate-700 text-xs leading-relaxed border border-slate-100">
                {c.narrative || 'No detailed narrative provided yet.'}
              </p>
            </div>
          </div>

          {/* Accused & Vehicles Entities */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
            <h3 className="font-bold text-sm text-slate-800 border-b border-slate-100 pb-2.5 mb-3 flex items-center justify-between">
              <span>Linked Accused & Conveyances</span>
              <span className="text-xs text-slate-400">{entities.length} Mentions</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {entities.map((entObj: any, idx: number) => {
                const ent = entObj.entity;
                const mention = entObj.mention;
                const isPerson = ent.entity_type === 'PERSON';
                return (
                  <div key={idx} className="p-3 bg-slate-50 rounded-lg border border-slate-100 flex items-start gap-3">
                    <div className={`p-2 rounded-lg ${isPerson ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'}`}>
                      {isPerson ? <User className="w-4 h-4" /> : <Car className="w-4 h-4" />}
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-xs text-slate-900">{ent.canonical_name}</span>
                        <span className="text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.2 rounded font-mono">
                          {mention.role_in_case}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        Type: {ent.entity_type} | Risk Score: <span className="font-bold text-slate-700">{ent.risk_score}</span>
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Column: Evidence Documents & Extracted Fields Verification */}
        <div className="space-y-6">
          {/* Documents Evidence Card */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
            <h3 className="font-bold text-sm text-slate-800 mb-3 flex items-center justify-between">
              <span>Original Evidence Documents</span>
              <span className="text-xs text-blue-600 font-semibold">{documents.length} Records</span>
            </h3>
            {documents.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No evidence PDFs attached yet.</p>
            ) : (
              <div className="space-y-2.5">
                {documents.map((doc: any) => (
                  <div
                    key={doc.id}
                    className="p-3 bg-slate-50 rounded-lg border border-slate-200 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center space-x-2.5">
                      <FileText className="w-5 h-5 text-red-600 flex-shrink-0" />
                      <div className="overflow-hidden">
                        <p className="font-semibold text-slate-900 truncate max-w-[150px]">{doc.original_filename}</p>
                        <p className="text-[10px] text-slate-400">Pages: {doc.physical_page_count} | Status: {doc.ingestion_status}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => setActiveViewerDocId(doc.id)}
                      className="px-2.5 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-[11px] font-semibold flex items-center gap-1 transition-colors"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      <span>View PDF</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Extracted Fields Human Verification / Provenance Card */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
            <h3 className="font-bold text-sm text-slate-800 mb-2">Extracted Field Provenance</h3>
            <p className="text-[11px] text-slate-500 mb-3">
              Review AI extracted values, model confidence, and override incorrect fields with human sign-off.
            </p>
            <div className="space-y-2.5">
              {fields.map((f: any) => {
                const isOverridden = f.verification_status === 'OVERRIDDEN';
                const isVerified = f.verification_status === 'VERIFIED';
                return (
                  <div
                    key={f.id}
                    className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[11px] font-bold text-slate-700 uppercase">{f.field_name}</span>
                      <span
                        className={`text-[9px] px-1.5 py-0.2 rounded font-bold border ${
                          isVerified
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : isOverridden
                            ? 'bg-blue-50 text-blue-700 border-blue-200'
                            : 'bg-amber-50 text-amber-700 border-amber-200'
                        }`}
                      >
                        {f.verification_status}
                      </span>
                    </div>
                    <p className="text-slate-900 font-medium truncate">
                      {f.human_override_value || f.original_value || 'None'}
                    </p>
                    <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-100">
                      <span>Conf: {Math.round(f.confidence_score * 100)}% ({f.extraction_method})</span>
                      <button
                        onClick={() => {
                          setOverrideField(f);
                          setOverrideValue(f.human_override_value || f.original_value || '');
                        }}
                        className="text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-0.5"
                      >
                        <Edit2 className="w-2.5 h-2.5" />
                        <span>Override</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Field Override Dialog */}
      {overrideField && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 border border-slate-200">
            <h3 className="font-bold text-base text-slate-900">
              Verify & Override Field: <span className="font-mono text-blue-700">{overrideField.field_name}</span>
            </h3>
            <p className="text-xs text-slate-500">
              Recorded Original Value: <span className="font-semibold text-slate-800">{overrideField.original_value}</span>
            </p>
            <form onSubmit={handleFieldOverrideSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Human Verified / Corrected Value:
                </label>
                <input
                  type="text"
                  required
                  value={overrideValue}
                  onChange={(e) => setOverrideValue(e.target.value)}
                  className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setOverrideField(null)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingOverride}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-500 shadow-sm"
                >
                  {savingOverride ? 'Saving...' : 'Save & Sign-off'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* PDF Viewer Modal */}
      {activeViewerDocId && (
        <PDFViewerModal
          documentId={activeViewerDocId}
          onClose={() => setActiveViewerDocId(null)}
        />
      )}
    </div>
  );
};

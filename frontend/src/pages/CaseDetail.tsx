import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { PDFViewerModal } from '../components/pdf/PDFViewerModal';
import { IncidentLocationMap } from '../components/incident/IncidentLocationMap';
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
  Activity,
  Download,
  FileCode,
  RefreshCw,
  RotateCcw,
  Share2,
  AlertTriangle,
  X,
  Upload
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
  const [overrideError, setOverrideError] = useState<string | null>(null);
  const [fieldChecks, setFieldChecks] = useState<Record<string, { level: string; code: string; message: string }[]>>({});
  const [detailError, setDetailError] = useState<string | null>(null);
  const [workflowStages, setWorkflowStages] = useState<any[]>([]);
  const [approvingCase, setApprovingCase] = useState(false);
  const [approveMsg, setApproveMsg] = useState<string | null>(null);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);

  // Document Replacement
  const [showReplaceDocModal, setShowReplaceDocModal] = useState(false);
  const [replaceDocFile, setReplaceDocFile] = useState<File | null>(null);
  const [replaceDocReason, setReplaceDocReason] = useState('');
  const [replaceDocLoading, setReplaceDocLoading] = useState(false);

  // Case Archival / Deletion
  const [showArchiveModal, setShowArchiveModal] = useState(false);
  const [archiveReason, setArchiveReason] = useState('');
  const [archiveConfirmText, setArchiveConfirmText] = useState('');
  const [archiveLoading, setArchiveLoading] = useState(false);

  // Edit Case Fields
  const [showEditFieldsModal, setShowEditFieldsModal] = useState(false);
  const [editFormData, setEditFormData] = useState<any>({});
  const [saveFieldsLoading, setSaveFieldsLoading] = useState(false);

  // Action status banner
  const [actionNotice, setActionNotice] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  const handleExport = async (format: 'xlsx' | 'docx' | 'csv' | 'json' | 'pdf') => {
    if (!id) return;
    setExportingFormat(format);
    try {
      const res = await api.get(`/cases/${id}/export/${format}`, { responseType: 'blob' });
      let filename = '';
      const disposition = res.headers['content-disposition'];
      if (disposition) {
        const match = disposition.match(/filename="?([^";]+)"?/);
        if (match && match[1]) filename = match[1].trim();
      }
      if (!filename) {
        filename = `${(caseData?.case?.fir_number || 'FIR_Case').replace(/[^a-zA-Z0-9_-]/g, '_')}_export.${format}`;
      }
      const blob = new Blob([res.data], { type: String(res.headers['content-type'] || 'application/octet-stream') });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Export failed (${format.toUpperCase()}): ` + (err.response?.data?.detail || err.message));
    } finally {
      setExportingFormat(null);
    }
  };

  const fetchDetail = async () => {
    try {
      setLoading(true);
      setDetailError(null);
      const res = await api.get(`/cases/${id}`, { timeout: 45000 });
      setCaseData(res.data);
      fetchFieldChecks();
    } catch (e: any) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      setDetailError(status === 403 || status === 404
        ? (typeof detail === 'string' ? detail : 'Case not found or permission denied.')
        : `The case could not be loaded: ${typeof detail === 'string' ? detail : e?.message || 'unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  // Format / consistency flags for each stored field (shown next to the field)
  const fetchFieldChecks = async () => {
    try {
      const res = await api.get(`/cases/${id}/field-checks`);
      setFieldChecks(Object.fromEntries((res.data.fields || []).map((f: any) => [f.field_id, f.issues])));
    } catch {
      setFieldChecks({});
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
      setOverrideError(null);
      await api.post(`/cases/${id}/fields/${overrideField.id}/override`, {
        human_override_value: overrideValue,
        verification_status: 'OVERRIDDEN'
      });
      setOverrideField(null);
      await fetchDetail();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setOverrideError(typeof detail === 'string' ? detail : e?.message || 'The override could not be saved.');
    } finally {
      setSavingOverride(false);
    }
  };

  const handleReplaceDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!replaceDocFile || !replaceDocReason.trim() || !id) return;
    try {
      setReplaceDocLoading(true);
      const fd = new FormData();
      fd.append('file', replaceDocFile);
      fd.append('reason', replaceDocReason.trim());
      const res = await api.post(`/cases/${id}/replace-document`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setActionNotice({ type: 'success', msg: res.data.message || 'Document replaced successfully. Case set to In Review.' });
      setShowReplaceDocModal(false);
      setReplaceDocFile(null);
      setReplaceDocReason('');
      await fetchDetail();
      await fetchWorkflow();
    } catch (err: any) {
      setActionNotice({ type: 'error', msg: err?.response?.data?.detail || 'Failed to replace document.' });
    } finally {
      setReplaceDocLoading(false);
    }
  };

  const handleArchiveCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (archiveConfirmText.trim() !== 'ARCHIVE' || !archiveReason.trim() || !id) return;
    try {
      setArchiveLoading(true);
      const res = await api.delete(`/cases/${id}`, {
        params: { reason: archiveReason.trim() },
      });
      setActionNotice({ type: 'success', msg: res.data.message || 'Case safely archived.' });
      setShowArchiveModal(false);
      setArchiveReason('');
      setArchiveConfirmText('');
      await fetchDetail();
    } catch (err: any) {
      setActionNotice({ type: 'error', msg: err?.response?.data?.detail || 'Failed to archive case.' });
    } finally {
      setArchiveLoading(false);
    }
  };

  const handleRestoreCase = async () => {
    if (!id) return;
    try {
      const res = await api.post(`/cases/${id}/restore`);
      setActionNotice({ type: 'success', msg: res.data.message || 'Case restored to active records.' });
      await fetchDetail();
    } catch (err: any) {
      setActionNotice({ type: 'error', msg: err?.response?.data?.detail || 'Failed to restore case.' });
    }
  };

  const handleOpenEditFields = () => {
    if (!caseData?.case) return;
    setEditFormData({
      offence_nature: caseData.case.offence_nature || '',
      contraband_type: caseData.case.contraband_type || '',
      seized_quantity: caseData.case.seized_quantity ?? '',
      seized_unit: caseData.case.seized_unit || '',
      vehicle_details: caseData.case.vehicle_details || '',
      location_description: caseData.case.location_description || '',
      narrative: caseData.case.narrative || '',
    });
    setShowEditFieldsModal(true);
  };

  const handleSaveFields = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    try {
      setSaveFieldsLoading(true);
      const payload: any = { ...editFormData };
      if (payload.seized_quantity !== '') {
        payload.seized_quantity = parseFloat(payload.seized_quantity) || 0;
      } else {
        delete payload.seized_quantity;
      }
      await api.put(`/cases/${id}`, payload);
      setActionNotice({ type: 'success', msg: 'FIR record fields updated successfully.' });
      setShowEditFieldsModal(false);
      await fetchDetail();
    } catch (err: any) {
      setActionNotice({ type: 'error', msg: err?.response?.data?.detail || 'Failed to update fields.' });
    } finally {
      setSaveFieldsLoading(false);
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
      <div className="p-8 bg-red-50 text-red-700 rounded-xl border border-red-200 text-sm flex items-center justify-between gap-3" role="alert">
        <span>{detailError || 'Case not found or permission denied.'}</span>
        <button onClick={fetchDetail} className="px-3 py-1.5 bg-white border border-red-200 rounded-md text-xs font-semibold hover:bg-red-100">
          Retry
        </button>
      </div>
    );
  }

  const { case: c, fields, documents, entities } = caseData;

  return (
    <div className="space-y-6">
      {/* Action Notification Banner */}
      {actionNotice && (
        <div
          className={`p-3 rounded-xl border flex items-center justify-between text-xs font-medium animate-in fade-in duration-200 ${
            actionNotice.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <div className="flex items-center space-x-2">
            {actionNotice.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
            )}
            <span>{actionNotice.msg}</span>
          </div>
          <button
            onClick={() => setActionNotice(null)}
            className="text-slate-400 hover:text-slate-600"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Archived Warning Banner */}
      {c.is_archived && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-amber-100 rounded-lg text-amber-700">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            </div>
            <div>
              <p className="text-sm font-bold text-amber-900">
                This FIR Case is ARCHIVED (Soft-Deleted)
              </p>
              <p className="text-xs text-amber-700 mt-0.5">
                Audit Reason: {c.archived_reason || 'Departmental record archival'} &bull; Evidence preserved intact
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleRestoreCase}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-xs font-bold flex items-center justify-center space-x-1.5 transition-colors shadow-sm"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Restore Active Case</span>
          </button>
        </div>
      )}

      {/* Top Banner with Quick Actions */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-xs font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
              {c.fir_number}
            </span>
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                c.is_archived
                  ? 'bg-slate-100 text-slate-700 border-slate-300'
                  : c.status === 'APPROVED'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-amber-50 text-amber-700 border-amber-200'
              }`}
            >
              {c.is_archived ? 'ARCHIVED' : c.status}
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
          <button
            type="button"
            onClick={handleOpenEditFields}
            className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors border border-slate-300"
          >
            <Edit2 className="w-4 h-4 text-slate-600" />
            <span>Edit Fields</span>
          </button>

          <button
            type="button"
            onClick={() => setShowReplaceDocModal(true)}
            className="px-3 py-2 bg-amber-50 hover:bg-amber-100 text-amber-800 rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors border border-amber-300"
          >
            <Upload className="w-4 h-4 text-amber-600" />
            <span>Replace Doc</span>
          </button>

          <Link
            to={`/legal?caseId=${c.id}`}
            className="px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <Scale className="w-4 h-4" />
            <span>Legal Sections</span>
          </Link>

          <Link
            to={`/case-diary?caseId=${c.id}`}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-100 rounded-lg text-xs font-medium shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <BookOpen className="w-4 h-4" />
            <span>Case Diary</span>
          </Link>

          <Link
            to={`/chargesheet?caseId=${c.id}`}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-100 rounded-lg text-xs font-medium shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <FileSpreadsheet className="w-4 h-4" />
            <span>Chargesheet</span>
          </Link>

          {c.status !== 'APPROVED' && !c.is_archived && (
            <button
              onClick={handleApproveCase}
              disabled={approvingCase}
              className="px-3 py-2 bg-emerald-700 hover:bg-emerald-600 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              {approvingCase
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <ShieldCheck className="w-4 h-4" />}
              <span>{approvingCase ? 'Approving...' : 'Approve Case'}</span>
            </button>
          )}

          {c.is_archived ? (
            <button
              type="button"
              onClick={handleRestoreCase}
              className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Restore</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setShowArchiveModal(true)}
              className="px-3 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 transition-colors border border-rose-200"
              title="Soft-delete / archive this FIR case"
            >
              <Trash2 className="w-4 h-4 text-rose-600" />
              <span>Archive</span>
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
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
            <h3 className="font-bold text-xs text-slate-700 flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-blue-600" />
              AI Intelligence Workflow Pipeline (6 Stages)
            </h3>
            <Link
              to={`/network?case_id=${c.id}`}
              className="inline-flex items-center space-x-1.5 px-3 py-1 bg-slate-900 hover:bg-slate-800 text-amber-300 rounded-full text-xs font-semibold transition-colors self-start sm:self-auto"
            >
              <Share2 className="w-3.5 h-3.5 text-amber-400" />
              <span>Inspect Repeat Offender & Network Graph</span>
            </Link>
          </div>
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

      {/* Official Case Export Section */}
      <div className="bg-gradient-to-r from-slate-900 to-[#112d4e] text-white p-4 rounded-xl border border-slate-700 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 bg-emerald-600/30 text-emerald-400 border border-emerald-500/40 rounded-lg">
            <Download className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-white flex items-center gap-2">
              <span>Official Case Export / Download</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                {c.fir_number}
              </span>
            </h3>
            <p className="text-[11px] text-slate-300">
              Download complete verified records with evidence citations and Telugu/Hindi encoding.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            disabled={Boolean(exportingFormat)}
            onClick={() => handleExport('xlsx')}
            className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-md border border-slate-600 font-semibold inline-flex items-center space-x-1 transition-all disabled:opacity-50"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
            <span>Excel (.xlsx)</span>
          </button>
          <button
            type="button"
            disabled={Boolean(exportingFormat)}
            onClick={() => handleExport('docx')}
            className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-md border border-slate-600 font-semibold inline-flex items-center space-x-1 transition-all disabled:opacity-50"
          >
            <FileText className="w-3.5 h-3.5 text-blue-400" />
            <span>Word (.docx)</span>
          </button>
          <button
            type="button"
            disabled={Boolean(exportingFormat)}
            onClick={() => handleExport('pdf')}
            className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-md border border-slate-600 font-semibold inline-flex items-center space-x-1 transition-all disabled:opacity-50"
          >
            <FileText className="w-3.5 h-3.5 text-rose-400" />
            <span>PDF (.pdf)</span>
          </button>
          <button
            type="button"
            disabled={Boolean(exportingFormat)}
            onClick={() => handleExport('csv')}
            className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-md border border-slate-600 font-semibold inline-flex items-center space-x-1 transition-all disabled:opacity-50"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-amber-400" />
            <span>CSV</span>
          </button>
          <button
            type="button"
            disabled={Boolean(exportingFormat)}
            onClick={() => handleExport('json')}
            className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-md border border-slate-600 font-semibold inline-flex items-center space-x-1 transition-all disabled:opacity-50"
          >
            <FileCode className="w-3.5 h-3.5 text-purple-400" />
            <span>JSON</span>
          </button>
        </div>
      </div>

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

          {/* Incident Location & Interactive Map */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
            <IncidentLocationMap caseId={c.id} firNumber={c.fir_number} />
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
                      {f.human_override_value || f.normalized_value || f.original_value || 'None'}
                    </p>
                    {fieldChecks[f.id]?.map((issue, iIdx) => (
                      <p key={iIdx} className="text-[10px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5">
                        Needs review: {issue.message}
                      </p>
                    ))}
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
              {overrideError && <p className="text-xs text-red-700" role="alert">{overrideError}</p>}
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { setOverrideField(null); setOverrideError(null); }}
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

      {/* Replace Document Modal */}
      {showReplaceDocModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6 space-y-4 border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-amber-50 rounded-lg text-amber-700">
                  <Upload className="w-5 h-5" />
                </div>
                <h3 className="font-bold text-base text-slate-900">Replace FIR Document</h3>
              </div>
              <button
                onClick={() => setShowReplaceDocModal(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 space-y-1">
              <p className="font-semibold">Chain-of-Custody & Audit Assurance:</p>
              <p>
                The existing evidence document is never erased. It is cryptographically archived with a timestamp and your user ID.
                Uploading a replacement will mark this case as <strong>IN_REVIEW</strong> and rerun the intelligence pipeline.
              </p>
            </div>

            <form onSubmit={handleReplaceDocument} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Select New Document (PDF, JPEG, PNG, WEBP):
                </label>
                <input
                  type="file"
                  required
                  accept=".pdf,image/jpeg,image/png,image/webp"
                  onChange={(e) => setReplaceDocFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-slate-900 file:text-white hover:file:bg-slate-800 cursor-pointer border border-slate-200 rounded-lg p-2"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Mandatory Replacement Reason:
                </label>
                <textarea
                  required
                  rows={3}
                  value={replaceDocReason}
                  onChange={(e) => setReplaceDocReason(e.target.value)}
                  placeholder="e.g. Initial scan was illegible; officer uploaded full certified copy from court..."
                  className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-amber-500 focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowReplaceDocModal(false)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={replaceDocLoading || !replaceDocFile || !replaceDocReason.trim()}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center space-x-1.5 disabled:opacity-50"
                >
                  {replaceDocLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>{replaceDocLoading ? 'Uploading & Re-indexing...' : 'Confirm Replacement'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Archive / Delete Modal */}
      {showArchiveModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-4 border border-rose-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-rose-100 pb-3">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-rose-50 rounded-lg text-rose-700">
                  <Trash2 className="w-5 h-5" />
                </div>
                <h3 className="font-bold text-base text-rose-900">Archive / Soft-Delete Case</h3>
              </div>
              <button
                onClick={() => setShowArchiveModal(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 space-y-1">
              <p className="font-semibold">Legal Retention Notice:</p>
              <p>
                FIR records cannot be permanently destroyed. Soft-deleting will remove this case from active folders and search lists,
                while preserving all evidence PDFs, hash chains, and audit logs.
              </p>
            </div>

            <form onSubmit={handleArchiveCase} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Mandatory Archival Reason:
                </label>
                <textarea
                  required
                  rows={2}
                  value={archiveReason}
                  onChange={(e) => setArchiveReason(e.target.value)}
                  placeholder="e.g. Transferred to another jurisdiction; duplicate registration; quashed by High Court order..."
                  className="w-full text-xs border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-rose-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Type <span className="font-mono font-bold text-rose-600">ARCHIVE</span> to confirm:
                </label>
                <input
                  type="text"
                  required
                  value={archiveConfirmText}
                  onChange={(e) => setArchiveConfirmText(e.target.value)}
                  placeholder="ARCHIVE"
                  className="w-full text-xs border border-slate-300 rounded-lg p-2.5 font-mono focus:ring-2 focus:ring-rose-500 focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowArchiveModal(false)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={archiveLoading || archiveConfirmText.trim() !== 'ARCHIVE' || !archiveReason.trim()}
                  className="px-4 py-2 bg-rose-700 hover:bg-rose-600 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center space-x-1.5 disabled:opacity-50"
                >
                  {archiveLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>{archiveLoading ? 'Archiving...' : 'Archive Case'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Case Fields Modal */}
      {showEditFieldsModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full p-6 space-y-4 border border-slate-200 max-h-[90vh] overflow-y-auto animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-blue-50 rounded-lg text-blue-700">
                  <Edit2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-base text-slate-900">Edit FIR Case Particulars</h3>
                  <p className="text-xs text-slate-500">Case FIR: {c.fir_number}</p>
                </div>
              </div>
              <button
                onClick={() => setShowEditFieldsModal(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveFields} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Offence Nature:</label>
                  <input
                    type="text"
                    required
                    value={editFormData.offence_nature || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, offence_nature: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Contraband Type:</label>
                  <input
                    type="text"
                    value={editFormData.contraband_type || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, contraband_type: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Seized Quantity:</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editFormData.seized_quantity ?? ''}
                    onChange={(e) => setEditFormData({ ...editFormData, seized_quantity: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Seized Unit:</label>
                  <input
                    type="text"
                    placeholder="e.g. Litres, Kg, Bottles"
                    value={editFormData.seized_unit || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, seized_unit: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block font-semibold text-slate-700 mb-1">Vehicle / Conveyance Details:</label>
                  <input
                    type="text"
                    placeholder="e.g. AP04 AB 1234 - Hero Splendor Motorcycle"
                    value={editFormData.vehicle_details || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, vehicle_details: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block font-semibold text-slate-700 mb-1">Occurrence Location:</label>
                  <input
                    type="text"
                    value={editFormData.location_description || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, location_description: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block font-semibold text-slate-700 mb-1">Investigation Narrative:</label>
                  <textarea
                    rows={4}
                    value={editFormData.narrative || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, narrative: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowEditFieldsModal(false)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saveFieldsLoading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center space-x-1.5 disabled:opacity-50"
                >
                  {saveFieldsLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>{saveFieldsLoading ? 'Saving...' : 'Save Changes'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

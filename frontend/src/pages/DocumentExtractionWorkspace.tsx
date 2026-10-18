import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  FileText, UploadCloud, Sparkles, CheckCircle2, AlertCircle, Save,
  Download, RefreshCw, ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight,
  ChevronDown, Settings2, ShieldCheck, Database, ListChecks, Layers,
  ExternalLink, Search, Copy, Check, Plus, Trash2, ArrowRight, Eye, Code, FileSpreadsheet
} from 'lucide-react';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';

// ─────────────────────────────────────────────────────────────────────────────
// Interfaces & Types
// ─────────────────────────────────────────────────────────────────────────────

interface ExtractionField {
  id: string;
  key: string;
  label: string;
  data_type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  required: boolean;
  description?: string;
  validation_rules?: string;
  value?: any;
  source_page?: number;
  reviewed?: boolean;
}

interface ExtractionEntity {
  id: string;
  name: string;
  type: string;
  source_page: number;
  confidence: number;
  status: string;
}

interface KeyPoint {
  id: string;
  point: string;
  source_page?: number;
}

interface ExtractionRunData {
  run_id?: string;
  document_id: string;
  original_filename: string;
  mime_type?: string;
  page_count?: number;
  config_id?: string;
  config_version?: number;
  status?: string;
  case_id?: string;
  sarvam_job_id?: string;
  provider?: string;
  document_content?: string;
  document_metadata?: {
    document_type?: string;
    original_filename?: string;
    mime_type?: string;
    total_pages?: number;
    ocr_applied?: boolean;
    ocr_quality?: number | null;
    extraction_date?: string;
    provider?: string;
    sarvam_job_id?: string;
    author?: string | null;
    document_date?: string | null;
    district?: string | null;
    station?: string | null;
    raw_text_summary?: string | null;
  };
  structured_fields: ExtractionField[];
  entities: ExtractionEntity[];
  key_points: KeyPoint[];
  warnings: string[];
  created_at?: string;
}

interface ConfigData {
  id: string;
  name: string;
  version: number;
  schema_json: string;
  instructions: string;
  sarvam_config_id?: string;
  updated_at?: string;
}

export function formatErrorMessage(err: any, fallback: string = 'An unexpected error occurred.'): string {
  if (!err) return fallback;
  if (typeof err === 'string') return err;

  const detail = err.response?.data?.detail ?? err.message ?? err;
  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item: any) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          const loc = Array.isArray(item.loc) ? item.loc.filter((x: any) => x !== 'body').join('.') : '';
          const msg = item.msg || item.message || JSON.stringify(item);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(item);
      })
      .join(', ');
  }

  if (typeof detail === 'object' && detail !== null) {
    if (detail.message && typeof detail.message === 'string') return detail.message;
    if (detail.msg && typeof detail.msg === 'string') return detail.msg;
    return JSON.stringify(detail);
  }

  return String(detail);
}

export function getFieldValueString(val: any): string {
  if (val === null || val === undefined) return '';
  if (typeof val === 'string') return val;
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  if (Array.isArray(val)) {
    return val.map((x: any) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join(', ');
  }
  if (typeof val === 'object') return JSON.stringify(val);
  return String(val);
}

export const DocumentExtractionWorkspace: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialDocId = searchParams.get('docId');

  // Main Workspace State
  const [activeTab, setActiveTab] = useState<'results' | 'config'>('results');
  const [runData, setRunData] = useState<ExtractionRunData | null>(null);
  const [configData, setConfigData] = useState<ConfigData | null>(null);
  const [recentDocs, setRecentDocs] = useState<any[]>([]);

  // Loading States
  const [loading, setLoading] = useState<boolean>(false);
  const [uploading, setUploading] = useState<boolean>(false);
  const [extracting, setExtracting] = useState<boolean>(false);
  const [savingDraft, setSavingDraft] = useState<boolean>(false);
  const [confirmingCase, setConfirmingCase] = useState<boolean>(false);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);
  const [exportMenuOpen, setExportMenuOpen] = useState<boolean>(false);

  // Notifications
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Document Viewer State
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [isImage, setIsImage] = useState<boolean>(false);

  // Accordion Expand States
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    metadata: true,
    content: false,
    entities: true,
    keyPoints: true,
    fields: true,
    warnings: true,
  });

  // Search & Filter
  const [entityFilter, setEntityFilter] = useState('');
  const [fieldFilter, setFieldFilter] = useState('');
  const [copiedContent, setCopiedContent] = useState(false);

  // Config Tab Editor State
  const [schemaFields, setSchemaFields] = useState<any[]>([]);
  const [instructionsText, setInstructionsText] = useState('');
  const [sarvamConfigId, setSarvamConfigId] = useState('');
  const [rawSchemaMode, setRawSchemaMode] = useState(false);
  const [rawSchemaText, setRawSchemaText] = useState('');
  const [validationResult, setValidationResult] = useState<{ valid: boolean; message: string } | null>(null);
  const [showAddFieldModal, setShowAddFieldModal] = useState(false);
  const [newFieldData, setNewFieldData] = useState<any>({
    key: '',
    label: '',
    data_type: 'string',
    required: false,
    description: '',
    validation_rules: ''
  });

  // Confirm Case Modal
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [confirmedResult, setConfirmedResult] = useState<{ caseId: string; firNumber: string } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  // Toast Auto-Dismiss
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  // Click outside to close export menu
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setExportMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // 1. Fetch Configuration & Recent Documents on Mount
  // ─────────────────────────────────────────────────────────────────────────
  const fetchConfig = useCallback(async () => {
    try {
      const res = await api.get('/extraction/config');
      setConfigData(res.data);
      setInstructionsText(res.data.instructions || '');
      setSarvamConfigId(res.data.sarvam_config_id || '');
      setRawSchemaText(res.data.schema_json);
      try {
        setSchemaFields(JSON.parse(res.data.schema_json));
      } catch {
        setSchemaFields([]);
      }
    } catch (err: any) {
      console.error('Failed to load extraction config:', err);
    }
  }, []);

  const fetchRecentDocs = useCallback(async () => {
    try {
      const res = await api.get('/documents/');
      setRecentDocs(res.data || []);
    } catch (err: any) {
      console.error('Failed to load recent documents:', err);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
    fetchRecentDocs();
  }, [fetchConfig, fetchRecentDocs]);

  // ─────────────────────────────────────────────────────────────────────────
  // 2. Load Document & Extraction Run
  // ─────────────────────────────────────────────────────────────────────────
  const loadDocumentExtraction = useCallback(async (docId: string) => {
    if (!docId) {
      setToast({ type: 'error', message: 'No document ID specified to load.' });
      return;
    }
    setLoading(true);
    try {
      // 1. Fetch extraction run data first
      const extRes = await api.get(`/extraction/document/${docId}`);
      setRunData(extRes.data);
      setTotalPages(extRes.data?.page_count || 1);
      setCurrentPage(1);

      // 2. Fetch authenticated binary stream for document viewer in safe sub-block
      try {
        const viewRes = await api.get(`/documents/${docId}/view`, { responseType: 'blob' });
        const mime = String(viewRes.headers['content-type'] || extRes.data?.mime_type || 'application/pdf');
        const isImg = mime.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(viewRes.config.url || extRes.data?.original_filename || '');
        setIsImage(isImg);

        const blob = new Blob([viewRes.data], { type: mime });
        const objectUrl = URL.createObjectURL(blob);
        setPdfBlobUrl(objectUrl);
      } catch (viewerErr) {
        console.warn('Viewer preview stream could not be loaded:', viewerErr);
      }

      setToast({
        type: 'success',
        message: `Document '${extRes.data?.original_filename || 'Record'}' loaded with verified extractions.`
      });
    } catch (err: any) {
      console.error('Failed to load document extraction:', err);
      setToast({
        type: 'error',
        message: formatErrorMessage(err, 'Failed to load document intelligence.')
      });
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle docId URL param if present
  useEffect(() => {
    if (initialDocId) {
      loadDocumentExtraction(initialDocId);
    }
  }, [initialDocId, loadDocumentExtraction]);

  // Clean up blob URL on unmount
  useEffect(() => {
    return () => {
      if (pdfBlobUrl) {
        URL.revokeObjectURL(pdfBlobUrl);
      }
    };
  }, [pdfBlobUrl]);

  // ─────────────────────────────────────────────────────────────────────────
  // 3. File Upload Handler (PDF, JPEG, PNG, WEBP)
  // ─────────────────────────────────────────────────────────────────────────
  const handleFileUpload = async (file: File) => {
    if (!file) return;

    // Validate size (50MB)
    if (file.size > 50 * 1024 * 1024) {
      setToast({ type: 'error', message: 'File exceeds 50MB limit. Please upload a smaller document.' });
      return;
    }

    setUploading(true);
    setExtracting(false);
    try {
      const formData = new FormData();
      formData.append('file', file);

      // Upload and index document
      const uploadRes = await api.post('/documents/upload', formData);
      const docId = uploadRes.data?.document_id || uploadRes.data?.id;

      if (!docId) {
        throw new Error('Upload succeeded but server did not return a valid document ID.');
      }

      setUploading(false);
      setExtracting(true);

      // Run AI Document Extraction Workspace pipeline
      const runRes = await api.post('/extraction/run', {
        document_id: docId,
        config_id: configData?.id
      });
      setExtracting(false);

      // Load into viewer
      await loadDocumentExtraction(docId);
      fetchRecentDocs();

      const fieldCount = runRes.data?.structured_fields?.length ?? 0;
      const entityCount = runRes.data?.entities?.length ?? 0;
      setToast({
        type: 'success',
        message: `Extraction complete: ${fieldCount} fields and ${entityCount} entities identified.`
      });
    } catch (err: any) {
      setUploading(false);
      setExtracting(false);
      console.error('Upload or extraction error:', err);
      setToast({
        type: 'error',
        message: formatErrorMessage(err, 'Upload or extraction failed. Ensure document is a valid PDF or Image.')
      });
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // 4. In-Place Field Editing & Draft Saving
  // ─────────────────────────────────────────────────────────────────────────
  const handleFieldChange = (fieldId: string, newValue: any) => {
    if (!runData) return;
    const updatedFields = runData.structured_fields.map(f => {
      if (f.id === fieldId) {
        return { ...f, value: newValue, reviewed: true };
      }
      return f;
    });
    setRunData({ ...runData, structured_fields: updatedFields });
  };

  const handleFieldReviewedToggle = (fieldId: string) => {
    if (!runData) return;
    const updatedFields = runData.structured_fields.map(f => {
      if (f.id === fieldId) {
        return { ...f, reviewed: !f.reviewed };
      }
      return f;
    });
    setRunData({ ...runData, structured_fields: updatedFields });
  };

  const handleSaveDraft = async () => {
    if (!runData?.run_id) return;
    setSavingDraft(true);
    try {
      await api.put(`/extraction/run/${runData.run_id}/review`, { reviewed_data: runData });
      setToast({ type: 'success', message: 'Officer review draft saved successfully.' });
    } catch (err: any) {
      setToast({ type: 'error', message: formatErrorMessage(err, 'Failed to save draft.') });
    } finally {
      setSavingDraft(false);
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // 5. Jump to Page Citation in Document Viewer
  // ─────────────────────────────────────────────────────────────────────────
  const handleJumpToPage = (pageNumber: number) => {
    if (pageNumber < 1 || pageNumber > totalPages) return;
    setCurrentPage(pageNumber);
    setToast({ type: 'info', message: `Navigated viewer to physical Page ${pageNumber}.` });
  };

  // ─────────────────────────────────────────────────────────────────────────
  // 6. Confirm & Register Case
  // ─────────────────────────────────────────────────────────────────────────
  const handleConfirmAndRegister = async () => {
    if (!runData?.run_id) return;
    setConfirmingCase(true);
    try {
      const res = await api.post(`/extraction/run/${runData.run_id}/confirm`, {
        case_id: runData.case_id,
        reviewed_data: runData
      });
      setShowConfirmModal(false);
      setConfirmedResult({ caseId: res.data.case_id, firNumber: res.data.fir_number });
      setToast({ type: 'success', message: res.data.message || 'Case confirmed and registered successfully!' });
    } catch (err: any) {
      setToast({ type: 'error', message: formatErrorMessage(err, 'Failed to confirm case.') });
    } finally {
      setConfirmingCase(false);
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // 7. Multi-Format Downloads (Excel, Word, CSV, JSON, Original File)
  // ─────────────────────────────────────────────────────────────────────────
  const handleDownload = async (format: 'xlsx' | 'docx' | 'csv' | 'json' | 'original') => {
    if (!runData) return;
    setExportingFormat(format);
    setExportMenuOpen(false);
    try {
      if (format === 'original') {
        const res = await api.get(`/extraction/document/${runData.document_id}/file`, { responseType: 'blob' });
        const blob = new Blob([res.data]);
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = runData.original_filename || 'Original_Document.pdf';
        link.click();
        URL.revokeObjectURL(link.href);
      } else {
        if (!runData.run_id) {
          throw new Error('Please run extraction before downloading reports.');
        }
        const res = await api.get(`/extraction/run/${runData.run_id}/export/${format}`, { responseType: 'blob' });
        const extMap: Record<string, string> = { xlsx: 'xlsx', docx: 'docx', csv: 'csv', json: 'json' };
        const baseName = (runData.original_filename || 'FIR_Report').replace(/\.[^/.]+$/, '');
        const filename = `${baseName}_extraction.${extMap[format]}`;

        const blob = new Blob([res.data]);
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        URL.revokeObjectURL(link.href);
      }
      setToast({ type: 'success', message: `Exported ${format.toUpperCase()} successfully.` });
    } catch (err: any) {
      setToast({ type: 'error', message: formatErrorMessage(err, `Failed to export ${format.toUpperCase()}.`) });
    } finally {
      setExportingFormat(null);
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // 8. Config Tab Operations (Schema Add/Edit/Save, Regenerate)
  // ─────────────────────────────────────────────────────────────────────────
  const handleValidateSchema = async (jsonString: string) => {
    try {
      const res = await api.post('/extraction/config/validate', { schema_json: jsonString });
      setValidationResult(res.data);
      return res.data.valid;
    } catch (err: any) {
      setValidationResult({ valid: false, message: formatErrorMessage(err, 'Validation failed.') });
      return false;
    }
  };

  const handleSaveConfig = async () => {
    const finalSchemaJson = rawSchemaMode ? rawSchemaText : JSON.stringify(schemaFields, null, 2);
    const isValid = await handleValidateSchema(finalSchemaJson);
    if (!isValid) {
      setToast({ type: 'error', message: 'Schema contains validation errors. Please resolve before saving.' });
      return;
    }

    try {
      const res = await api.put('/extraction/config', {
        name: configData?.name || 'FIR Standard Extraction',
        schema_json: finalSchemaJson,
        instructions: instructionsText,
        sarvam_config_id: sarvamConfigId.trim() || undefined
      });
      setConfigData(res.data);
      if (res.data.sarvam_config_id !== undefined) {
        setSarvamConfigId(res.data.sarvam_config_id || '');
      }
      setToast({ type: 'success', message: res.data.message || 'Configuration saved successfully.' });
    } catch (err: any) {
      setToast({ type: 'error', message: formatErrorMessage(err, 'Failed to save configuration.') });
    }
  };

  const handleRegenerate = async () => {
    if (!runData?.document_id) {
      setToast({ type: 'error', message: 'No document loaded to regenerate.' });
      return;
    }
    // Save active config first
    await handleSaveConfig();

    setExtracting(true);
    try {
      const runRes = await api.post('/extraction/run', {
        document_id: runData.document_id,
        config_id: configData?.id
      });
      setRunData(runRes.data);
      setActiveTab('results');
      setToast({ type: 'success', message: 'Document re-extracted with updated schema configuration!' });
    } catch (err: any) {
      setToast({ type: 'error', message: formatErrorMessage(err, 'Re-extraction failed.') });
    } finally {
      setExtracting(false);
    }
  };

  const handleAddField = () => {
    if (!newFieldData.key.trim() || !newFieldData.label.trim()) {
      setToast({ type: 'error', message: 'Field Key and Label are mandatory.' });
      return;
    }
    const cleanKey = newFieldData.key.trim().toLowerCase().replace(/\s+/g, '_');
    const newField = {
      id: `f_${cleanKey}_${Date.now()}`,
      key: cleanKey,
      label: newFieldData.label.trim(),
      data_type: newFieldData.data_type,
      required: Boolean(newFieldData.required),
      description: newFieldData.description || '',
      validation_rules: newFieldData.validation_rules || ''
    };
    const updated = [...schemaFields, newField];
    setSchemaFields(updated);
    setRawSchemaText(JSON.stringify(updated, null, 2));
    setShowAddFieldModal(false);
    setNewFieldData({ key: '', label: '', data_type: 'string', required: false, description: '', validation_rules: '' });
    setToast({ type: 'success', message: `Field '${newField.label}' added to schema.` });
  };

  const handleDeleteField = (index: number) => {
    const updated = schemaFields.filter((_, i) => i !== index);
    setSchemaFields(updated);
    setRawSchemaText(JSON.stringify(updated, null, 2));
  };

  // Filtered lists
  const filteredEntities = (runData?.entities || []).filter(e =>
    e.name.toLowerCase().includes(entityFilter.toLowerCase()) ||
    e.type.toLowerCase().includes(entityFilter.toLowerCase())
  );

  const filteredFields = (runData?.structured_fields || []).filter(f =>
    f.label.toLowerCase().includes(fieldFilter.toLowerCase()) ||
    f.key.toLowerCase().includes(fieldFilter.toLowerCase()) ||
    String(f.value || '').toLowerCase().includes(fieldFilter.toLowerCase())
  );

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-[calc(100vh-64px)] bg-slate-100 text-slate-800">
      {/* ── TOP HEADER & WORKSPACE TOOLBAR ─────────────────────────────────── */}
      <header className="bg-white border-b border-slate-200 px-5 py-3 flex-shrink-0 flex items-center justify-between shadow-sm">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-lg bg-[#112d4e] flex items-center justify-center text-white shadow-sm">
              <Sparkles className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-base font-bold text-slate-900 leading-none">
                  FIR Document Extraction Workspace
                </h1>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-[#0f5132] border border-emerald-300">
                  AP Govt Verified
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Grounded multimodal intelligence extraction with page-level citations & multi-format export
              </p>
            </div>
          </div>

          {/* Stepper indicator */}
          <div className="hidden xl:flex items-center space-x-2 pl-6 border-l border-slate-200 text-xs">
            <span className={`flex items-center space-x-1 font-semibold ${runData ? 'text-emerald-700' : 'text-blue-700'}`}>
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>1. Upload</span>
            </span>
            <span className="text-slate-300">→</span>
            <span className={`flex items-center space-x-1 font-semibold ${runData ? 'text-emerald-700' : 'text-slate-400'}`}>
              <Sparkles className="w-3.5 h-3.5" />
              <span>2. Extraction</span>
            </span>
            <span className="text-slate-300">→</span>
            <span className={`flex items-center space-x-1 font-semibold ${activeTab === 'results' && runData ? 'text-blue-700 font-bold' : 'text-slate-400'}`}>
              <ListChecks className="w-3.5 h-3.5" />
              <span>3. Review & Edit</span>
            </span>
            <span className="text-slate-300">→</span>
            <span className={`flex items-center space-x-1 font-semibold ${runData?.case_id ? 'text-emerald-700' : 'text-slate-400'}`}>
              <Database className="w-3.5 h-3.5" />
              <span>4. Confirm Case</span>
            </span>
          </div>
        </div>

        {/* Right Action Buttons */}
        <div className="flex items-center space-x-2.5">
          {/* Recent Docs Dropdown */}
          {recentDocs.length > 0 && (
            <select
              aria-label="Load Existing FIR Document"
              value={runData?.document_id || ''}
              onChange={(e) => {
                if (e.target.value) loadDocumentExtraction(e.target.value);
              }}
              className="text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 focus:ring-2 focus:ring-[#112d4e] focus:outline-none max-w-[180px] truncate"
            >
              <option value="">Choose Existing FIR…</option>
              {recentDocs.map((d: any) => (
                <option key={d.id} value={d.id}>
                  {d.original_filename}
                </option>
              ))}
            </select>
          )}

          {/* Upload New Document Button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || extracting}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-[#112d4e] hover:bg-[#0c223c] text-white text-xs font-semibold rounded-lg shadow-sm transition-colors disabled:opacity-50"
          >
            <UploadCloud className="w-4 h-4 text-amber-300" />
            <span>{uploading ? 'Uploading…' : extracting ? 'Extracting…' : 'Upload FIR'}</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.webp"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFileUpload(file);
            }}
          />

          {runData && (
            <>
              {/* Save Draft Button */}
              <button
                onClick={handleSaveDraft}
                disabled={savingDraft}
                className="flex items-center space-x-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 text-xs font-semibold rounded-lg shadow-sm transition-colors disabled:opacity-50"
              >
                <Save className="w-3.5 h-3.5 text-blue-600" />
                <span>{savingDraft ? 'Saving…' : 'Save Draft'}</span>
              </button>

              {/* Download / Export Dropdown */}
              <div className="relative" ref={exportMenuRef}>
                <button
                  onClick={() => setExportMenuOpen(!exportMenuOpen)}
                  disabled={Boolean(exportingFormat)}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 text-xs font-semibold rounded-lg shadow-sm transition-colors"
                >
                  <Download className="w-3.5 h-3.5 text-emerald-600" />
                  <span>{exportingFormat ? `Exporting ${exportingFormat.toUpperCase()}…` : 'Download / Export'}</span>
                  <ChevronDown className="w-3 h-3 text-slate-400" />
                </button>

                {exportMenuOpen && (
                  <div className="absolute right-0 mt-1 w-56 bg-white rounded-lg shadow-xl border border-slate-200 py-1.5 z-50 animate-in fade-in slide-in-from-top-1 text-xs">
                    <div className="px-3 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                      Export Extraction Results
                    </div>
                    <button
                      onClick={() => handleDownload('xlsx')}
                      className="w-full flex items-center space-x-2.5 px-3 py-2 text-slate-700 hover:bg-emerald-50 hover:text-[#0f5132] transition-colors"
                    >
                      <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                      <div className="text-left">
                        <div className="font-semibold">Excel Spreadsheet (.xlsx)</div>
                        <div className="text-[10px] text-slate-400">Multi-sheet details & entities</div>
                      </div>
                    </button>
                    <button
                      onClick={() => handleDownload('docx')}
                      className="w-full flex items-center space-x-2.5 px-3 py-2 text-slate-700 hover:bg-blue-50 hover:text-blue-800 transition-colors"
                    >
                      <FileText className="w-4 h-4 text-blue-600" />
                      <div className="text-left">
                        <div className="font-semibold">Word Document (.docx)</div>
                        <div className="text-[10px] text-slate-400">Official AP Police formatted report</div>
                      </div>
                    </button>
                    <button
                      onClick={() => handleDownload('csv')}
                      className="w-full flex items-center space-x-2.5 px-3 py-2 text-slate-700 hover:bg-slate-100 transition-colors"
                    >
                      <Database className="w-4 h-4 text-amber-600" />
                      <div className="text-left">
                        <div className="font-semibold">CSV Table (.csv)</div>
                        <div className="text-[10px] text-slate-400">Flat tabular structured fields</div>
                      </div>
                    </button>
                    <button
                      onClick={() => handleDownload('json')}
                      className="w-full flex items-center space-x-2.5 px-3 py-2 text-slate-700 hover:bg-purple-50 hover:text-purple-800 transition-colors"
                    >
                      <Code className="w-4 h-4 text-purple-600" />
                      <div className="text-left">
                        <div className="font-semibold">JSON Payload (.json)</div>
                        <div className="text-[10px] text-slate-400">Complete indented extraction JSON</div>
                      </div>
                    </button>
                    <div className="border-t border-slate-100 my-1" />
                    <button
                      onClick={() => handleDownload('original')}
                      className="w-full flex items-center space-x-2.5 px-3 py-2 text-slate-700 hover:bg-slate-100 transition-colors"
                    >
                      <FileText className="w-4 h-4 text-slate-500" />
                      <div className="text-left">
                        <div className="font-semibold">Original Document</div>
                        <div className="text-[10px] text-slate-400">Download unaltered evidence file</div>
                      </div>
                    </button>
                  </div>
                )}
              </div>

              {/* Confirm Case Button */}
              <button
                onClick={() => setShowConfirmModal(true)}
                className="flex items-center space-x-1.5 px-3.5 py-1.5 bg-[#0f5132] hover:bg-[#0a3d26] text-white text-xs font-bold rounded-lg shadow-sm transition-colors"
              >
                <ShieldCheck className="w-4 h-4 text-emerald-300" />
                <span>Confirm & Register Case</span>
              </button>
            </>
          )}
        </div>
      </header>

      {/* ── TOAST NOTIFICATIONS ───────────────────────────────────────────── */}
      {toast && (
        <div className={`px-4 py-2.5 flex items-center justify-between text-xs font-semibold ${
          toast.type === 'success' ? 'bg-emerald-50 text-emerald-900 border-b border-emerald-200' :
          toast.type === 'error' ? 'bg-red-50 text-red-900 border-b border-red-200' :
          'bg-blue-50 text-blue-900 border-b border-blue-200'
        }`}>
          <div className="flex items-center space-x-2">
            {toast.type === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
            {toast.type === 'error' && <AlertCircle className="w-4 h-4 text-red-600" />}
            {toast.type === 'info' && <Sparkles className="w-4 h-4 text-blue-600" />}
            <span>{typeof toast.message === 'string' ? toast.message : JSON.stringify(toast.message)}</span>
          </div>
          <button onClick={() => setToast(null)} className="text-slate-400 hover:text-slate-700 font-bold ml-4">
            ×
          </button>
        </div>
      )}

      {/* ── MAIN WORKSPACE CONTENT ────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* If uploading or extracting, show dedicated animated processing state */}
        {(uploading || extracting) ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 bg-slate-50">
            <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200 p-8 text-center shadow-lg space-y-4">
              <div className="w-16 h-16 rounded-full bg-emerald-50 text-[#0f5132] flex items-center justify-center mx-auto border-2 border-emerald-500/30">
                {uploading ? (
                  <UploadCloud className="w-8 h-8 text-[#0f5132] animate-bounce" />
                ) : (
                  <Sparkles className="w-8 h-8 text-amber-500 animate-spin" />
                )}
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  {uploading ? 'Uploading Evidence Document…' : 'Running Multimodal Extraction & OCR…'}
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  {uploading
                    ? 'Storing authenticated document securely and indexing physical pages.'
                    : 'Applying zero-assumption grounding rules, extracting entities, key facts and page citations.'}
                </p>
              </div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                <div className={`h-full bg-[#0f5132] rounded-full transition-all duration-500 ${uploading ? 'w-2/5 animate-pulse' : 'w-4/5 animate-pulse'}`} />
              </div>
              <div className="text-[11px] font-semibold text-slate-400">
                Please wait while the AI intelligence engine processes the document…
              </div>
            </div>
          </div>
        ) : !runData && !loading ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 bg-slate-50">
            <div className="max-w-xl w-full bg-white rounded-2xl border-2 border-dashed border-slate-300 p-10 text-center shadow-sm">
              <div className="w-16 h-16 rounded-2xl bg-emerald-50 text-[#0f5132] flex items-center justify-center mx-auto mb-4 border border-emerald-100">
                <UploadCloud className="w-8 h-8" />
              </div>
              <h2 className="text-lg font-bold text-slate-900">
                Upload FIR Evidence Document
              </h2>
              <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                Drag and drop your FIR PDF, scanned image, or photograph (PDF, JPEG, PNG, WEBP).
                The AI extraction workspace will extract structured fields, entities, and citations side-by-side.
              </p>

              <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-6 py-2.5 bg-[#112d4e] hover:bg-[#0c223c] text-white text-xs font-bold rounded-lg shadow transition-colors flex items-center space-x-2"
                >
                  <FileText className="w-4 h-4 text-amber-400" />
                  <span>Choose File from Computer</span>
                </button>
                {recentDocs.length > 0 && (
                  <button
                    onClick={() => loadDocumentExtraction(recentDocs[0].id)}
                    className="px-5 py-2.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg transition-colors flex items-center space-x-2"
                  >
                    <Eye className="w-4 h-4 text-blue-600" />
                    <span>Open Recent: {recentDocs[0].original_filename}</span>
                  </button>
                )}
              </div>

              <div className="mt-8 pt-6 border-t border-slate-100 grid grid-cols-3 gap-4 text-left">
                <div className="p-3 bg-slate-50 rounded-lg">
                  <div className="text-[11px] font-bold text-slate-800">1. Side-by-Side</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Original document viewer on left, extractions on right</div>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg">
                  <div className="text-[11px] font-bold text-slate-800">2. Schema Config</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Customize output format and prompt instructions</div>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg">
                  <div className="text-[11px] font-bold text-slate-800">3. 4-Format Export</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Download as Excel, Word, CSV, or JSON</div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* Side-by-side workspace: Left (Viewer) | Right (Tabs) */
          <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
            {/* ── LEFT PANEL: DOCUMENT VIEWER ──────────────────────────────── */}
            <div className="w-full lg:w-1/2 flex flex-col bg-slate-800 border-r border-slate-300 overflow-hidden">
              {/* Document Viewer Toolbar */}
              <div className="bg-slate-900 text-white px-4 py-2.5 flex items-center justify-between border-b border-slate-700 flex-shrink-0 text-xs">
                <div className="flex items-center space-x-2 truncate max-w-[260px]">
                  <FileText className="w-4 h-4 text-blue-400 flex-shrink-0" />
                  <span className="font-semibold text-slate-200 truncate" title={runData?.original_filename}>
                    {runData?.original_filename}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-700 text-slate-300">
                    {isImage ? 'IMAGE' : 'PDF'}
                  </span>
                </div>

                {/* Page Navigation & Zoom Controls */}
                <div className="flex items-center space-x-3">
                  {!isImage && (
                    <div className="flex items-center space-x-1 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                      <button
                        disabled={currentPage <= 1}
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        className="p-1 text-slate-400 hover:text-white disabled:opacity-30"
                        title="Previous Page"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>
                      <span className="text-slate-300 font-mono text-[11px] px-1">
                        {currentPage} / {totalPages}
                      </span>
                      <button
                        disabled={currentPage >= totalPages}
                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        className="p-1 text-slate-400 hover:text-white disabled:opacity-30"
                        title="Next Page"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                  {/* Zoom */}
                  <div className="flex items-center space-x-1 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">
                    <button
                      onClick={() => setZoomLevel(z => Math.max(50, z - 15))}
                      className="p-1 text-slate-400 hover:text-white"
                      title="Zoom Out"
                    >
                      <ZoomOut className="w-3.5 h-3.5" />
                    </button>
                    <span className="text-slate-300 font-mono text-[11px] px-1">{zoomLevel}%</span>
                    <button
                      onClick={() => setZoomLevel(z => Math.min(200, z + 15))}
                      className="p-1 text-slate-400 hover:text-white"
                      title="Zoom In"
                    >
                      <ZoomIn className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setZoomLevel(100)}
                      className="p-1 text-slate-400 hover:text-white"
                      title="Reset Zoom"
                    >
                      <Maximize2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Viewer Canvas Container */}
              <div className="flex-1 bg-slate-900/90 overflow-auto flex items-center justify-center p-4 relative">
                {loading ? (
                  <div className="flex flex-col items-center justify-center text-slate-400 space-y-2">
                    <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
                    <span className="text-xs">Loading authenticated document…</span>
                  </div>
                ) : pdfBlobUrl ? (
                  isImage ? (
                    <div
                      className="transition-transform duration-150 flex items-center justify-center"
                      style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: 'top center' }}
                    >
                      <img
                        src={pdfBlobUrl}
                        alt="FIR Evidence Record"
                        className="max-w-full rounded shadow-2xl border border-slate-700"
                      />
                    </div>
                  ) : (
                    <iframe
                      src={`${pdfBlobUrl}#page=${currentPage}&zoom=${zoomLevel}`}
                      title="FIR Document Viewer"
                      className="w-full h-full rounded shadow-xl bg-white border border-slate-700"
                    />
                  )
                ) : (
                  <div className="text-center text-slate-500 text-xs">
                    No document stream available.
                  </div>
                )}
              </div>
            </div>

            {/* ── RIGHT PANEL: TABBED EXTRACTION & CONFIG WORKSPACE ─────────── */}
            <div className="w-full lg:w-1/2 flex flex-col bg-white overflow-hidden">
              {/* Tab Header Bar */}
              <div className="flex items-center justify-between border-b border-slate-200 px-5 pt-2 bg-slate-50 flex-shrink-0">
                <div className="flex space-x-2">
                  <button
                    onClick={() => setActiveTab('results')}
                    className={`flex items-center space-x-2 px-4 py-2.5 text-xs font-bold border-b-2 transition-all ${
                      activeTab === 'results'
                        ? 'border-[#112d4e] text-[#112d4e] bg-white rounded-t-lg shadow-sm'
                        : 'border-transparent text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    <ListChecks className="w-4 h-4 text-emerald-600" />
                    <span>Extraction results</span>
                    {runData?.structured_fields && (
                      <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-emerald-100 text-[#0f5132]">
                        {runData.structured_fields.length}
                      </span>
                    )}
                  </button>

                  <button
                    onClick={() => setActiveTab('config')}
                    className={`flex items-center space-x-2 px-4 py-2.5 text-xs font-bold border-b-2 transition-all ${
                      activeTab === 'config'
                        ? 'border-[#112d4e] text-[#112d4e] bg-white rounded-t-lg shadow-sm'
                        : 'border-transparent text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    <Settings2 className="w-4 h-4 text-blue-600" />
                    <span>Config</span>
                    {configData && (
                      <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-blue-100 text-blue-800">
                        v{configData.version}
                      </span>
                    )}
                  </button>
                </div>

                <div className="text-[11px] text-slate-400 pb-2">
                  {activeTab === 'results' ? 'Click citations to jump document pages' : 'Configure schema output & prompt'}
                </div>
              </div>

              {/* Tab Body */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4">
                {/* ═════════════════════════════════════════════════════════════ */}
                {/* TAB 1: EXTRACTION RESULTS                                    */}
                {/* ═════════════════════════════════════════════════════════════ */}
                {activeTab === 'results' && runData && (
                  <>
                    {/* Warnings Banner if any */}
                    {runData.warnings && runData.warnings.length > 0 && (
                      <div className="border border-amber-200 bg-amber-50 rounded-xl p-3.5">
                        <div
                          className="flex items-center justify-between cursor-pointer"
                          onClick={() => setExpanded(e => ({ ...e, warnings: !e.warnings }))}
                        >
                          <div className="flex items-center space-x-2">
                            <AlertCircle className="w-4 h-4 text-amber-600" />
                            <span className="text-xs font-bold text-amber-900">
                              Extraction Quality Warnings ({runData.warnings.length})
                            </span>
                          </div>
                          <ChevronDown className={`w-4 h-4 text-amber-600 transition-transform ${expanded.warnings ? 'rotate-180' : ''}`} />
                        </div>
                        {expanded.warnings && (
                          <ul className="mt-2 space-y-1 pl-6 list-disc text-xs text-amber-800">
                            {runData.warnings.map((w, idx) => (
                              <li key={idx}>{w}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    {/* Section 1: Document Content (Expandable) */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div
                        className="bg-slate-50 px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => setExpanded(e => ({ ...e, content: !e.content }))}
                      >
                        <div className="flex items-center space-x-2">
                          <FileText className="w-4 h-4 text-[#112d4e]" />
                          <span className="text-xs font-bold text-slate-800">Document Content</span>
                          <span className="text-[11px] text-slate-400">
                            ({runData.document_content ? `${runData.document_content.split(/\s+/).length} words` : '0 words'})
                          </span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <button
                            type="button"
                            onClick={(ev) => {
                              ev.stopPropagation();
                              if (runData.document_content) {
                                navigator.clipboard.writeText(runData.document_content);
                                setCopiedContent(true);
                                setTimeout(() => setCopiedContent(false), 2000);
                              }
                            }}
                            className="p-1 text-slate-400 hover:text-slate-700"
                            title="Copy full text"
                          >
                            {copiedContent ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                          <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${expanded.content ? 'rotate-180' : ''}`} />
                        </div>
                      </div>
                      {expanded.content && (
                        <div className="p-4 bg-white border-t border-slate-100">
                          <pre className="text-xs font-mono text-slate-700 whitespace-pre-wrap max-h-60 overflow-y-auto bg-slate-50 p-3 rounded-lg border border-slate-200">
                            {runData.document_content || 'No text extracted from document.'}
                          </pre>
                        </div>
                      )}
                    </div>

                    {/* Section 2: Document Metadata (Expandable) */}
                    {runData.document_metadata && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div
                          className="bg-slate-50 px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                          onClick={() => setExpanded(e => ({ ...e, metadata: !(e as any).metadata }))}
                        >
                          <div className="flex items-center space-x-2">
                            <FileText className="w-4 h-4 text-slate-500" />
                            <span className="text-xs font-bold text-slate-800">Document Metadata</span>
                          </div>
                          <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${(expanded as any).metadata ? 'rotate-180' : ''}`} />
                        </div>
                        {(expanded as any).metadata && (
                          <div className="p-4 bg-white border-t border-slate-100 space-y-3">
                            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                              {runData.document_metadata.document_type && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Document Type</span>
                                  <div className="text-slate-800 mt-0.5">{runData.document_metadata.document_type}</div>
                                </div>
                              )}
                              {runData.document_metadata.total_pages != null && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Total Pages</span>
                                  <div className="text-slate-800 mt-0.5">{runData.document_metadata.total_pages}</div>
                                </div>
                              )}
                              {runData.document_metadata.document_date && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Document Date</span>
                                  <div className="text-slate-800 mt-0.5">{runData.document_metadata.document_date}</div>
                                </div>
                              )}
                              {runData.document_metadata.extraction_date && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Extraction Date</span>
                                  <div className="text-slate-800 mt-0.5">{runData.document_metadata.extraction_date}</div>
                                </div>
                              )}
                              {runData.document_metadata.author && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Author / Officer</span>
                                  <div className="text-slate-800 mt-0.5">{runData.document_metadata.author}</div>
                                </div>
                              )}
                              {runData.document_metadata.district && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">District</span>
                                  <div className="text-slate-800 mt-0.5">{runData.document_metadata.district}</div>
                                </div>
                              )}
                              {runData.document_metadata.station && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Station</span>
                                  <div className="text-slate-800 mt-0.5">{runData.document_metadata.station}</div>
                                </div>
                              )}
                              {runData.document_metadata.ocr_applied != null && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">OCR Applied</span>
                                  <div className="mt-0.5">
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${runData.document_metadata.ocr_applied ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'}`}>
                                      {runData.document_metadata.ocr_applied ? 'Yes (Scanned)' : 'No (Text PDF)'}
                                    </span>
                                  </div>
                                </div>
                              )}
                              {runData.document_metadata.ocr_quality != null && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">OCR Quality</span>
                                  <div className="text-slate-800 mt-0.5">{Math.round(runData.document_metadata.ocr_quality * 100)}%</div>
                                </div>
                              )}
                              {(runData.document_metadata.provider || runData.provider) && (
                                <div>
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Extraction Engine</span>
                                  <div className="mt-0.5">
                                    <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-900 border border-purple-200">
                                      <Sparkles className="w-3 h-3 text-purple-600" />
                                      <span>{runData.document_metadata.provider || runData.provider}</span>
                                    </span>
                                  </div>
                                </div>
                              )}
                              {(runData.document_metadata.sarvam_job_id || runData.sarvam_job_id) && (
                                <div className="col-span-2">
                                  <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Sarvam Doc AI Job ID</span>
                                  <div className="font-mono text-[11px] text-slate-700 mt-0.5 truncate bg-slate-50 px-2 py-1 rounded border border-slate-200">
                                    {runData.document_metadata.sarvam_job_id || runData.sarvam_job_id}
                                  </div>
                                </div>
                              )}
                            </div>
                            {runData.document_metadata.raw_text_summary && (
                              <div className="mt-3 pt-3 border-t border-slate-100">
                                <span className="font-semibold text-slate-500 uppercase text-[10px] tracking-wide">Raw-Text Summary</span>
                                <p className="text-xs text-slate-700 mt-1 leading-relaxed bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                                  {runData.document_metadata.raw_text_summary}
                                </p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Section 3: Extracted Entities (Expandable) */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div
                        className="bg-slate-50 px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => setExpanded(e => ({ ...e, entities: !e.entities }))}
                      >
                        <div className="flex items-center space-x-2">
                          <Layers className="w-4 h-4 text-emerald-600" />
                          <span className="text-xs font-bold text-slate-800">Entities</span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-[#0f5132]">
                            {runData.entities?.length || 0}
                          </span>
                        </div>
                        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${expanded.entities ? 'rotate-180' : ''}`} />
                      </div>

                      {expanded.entities && (
                        <div className="p-4 bg-white border-t border-slate-100 space-y-3">
                          {/* Search entities */}
                          <div className="relative">
                            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                            <input
                              type="text"
                              placeholder="Filter entities by name or type…"
                              value={entityFilter}
                              onChange={(e) => setEntityFilter(e.target.value)}
                              className="w-full text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                            />
                          </div>

                          {filteredEntities.length === 0 ? (
                            <div className="text-center py-6 text-slate-400 text-xs">No matching entities found.</div>
                          ) : (
                            <div className="divide-y divide-slate-100 border border-slate-100 rounded-lg overflow-hidden">
                              {filteredEntities.map((ent) => (
                                <div key={ent.id} className="p-2.5 flex items-center justify-between hover:bg-slate-50 transition-colors">
                                  <div className="space-y-0.5">
                                    <div className="text-xs font-bold text-slate-800">{ent.name}</div>
                                    {(ent as any).context && (
                                      <div className="text-[10px] text-slate-500 italic">{(ent as any).context}</div>
                                    )}
                                    <div className="flex items-center space-x-2">
                                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                        ent.type === 'ACCUSED' ? 'bg-red-100 text-red-800' :
                                        ent.type === 'COMPLAINANT' ? 'bg-orange-100 text-orange-800' :
                                        ent.type === 'WITNESS' ? 'bg-yellow-100 text-yellow-800' :
                                        ent.type === 'OFFICER' ? 'bg-blue-100 text-blue-800' :
                                        ent.type === 'VEHICLE' ? 'bg-cyan-100 text-cyan-800' :
                                        ent.type === 'LOCATION' ? 'bg-emerald-100 text-emerald-800' :
                                        ent.type === 'JURISDICTION' ? 'bg-teal-100 text-teal-800' :
                                        ent.type === 'FINANCIAL' ? 'bg-green-100 text-green-800' :
                                        ent.type === 'PHONE' ? 'bg-indigo-100 text-indigo-800' :
                                        ent.type === 'SECTION' ? 'bg-purple-100 text-purple-800' :
                                        'bg-slate-100 text-slate-700'
                                      }`}>
                                        {ent.type}
                                      </span>
                                      <span className="text-[10px] text-slate-400">
                                        Conf: {Math.round(ent.confidence * 100)}%
                                      </span>
                                    </div>
                                  </div>

                                  <button
                                    onClick={() => handleJumpToPage(ent.source_page)}
                                    className="flex items-center space-x-1 px-2 py-1 rounded bg-blue-50 hover:bg-blue-100 text-blue-700 text-[11px] font-semibold transition-colors"
                                    title="Jump left viewer to this page"
                                  >
                                    <span>Page {ent.source_page}</span>
                                    <ArrowRight className="w-3 h-3" />
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Section 3: Factual Key Points (Expandable) */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div
                        className="bg-slate-50 px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => setExpanded(e => ({ ...e, keyPoints: !e.keyPoints }))}
                      >
                        <div className="flex items-center space-x-2">
                          <CheckCircle2 className="w-4 h-4 text-amber-600" />
                          <span className="text-xs font-bold text-slate-800">Key Points</span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">
                            {runData.key_points?.length || 0}
                          </span>
                        </div>
                        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${expanded.keyPoints ? 'rotate-180' : ''}`} />
                      </div>

                      {expanded.keyPoints && (
                        <div className="p-4 bg-white border-t border-slate-100">
                          <div className="space-y-2">
                            {runData.key_points?.map((kp, idx) => (
                              <div key={kp.id || idx} className="p-2.5 bg-slate-50 rounded-lg flex items-start justify-between space-x-2">
                                <div className="flex items-start space-x-2">
                                  <span className="text-xs font-bold text-amber-700 mt-0.5">{idx + 1}.</span>
                                  <span className="text-xs text-slate-800 leading-relaxed">{kp.point}</span>
                                </div>
                                {kp.source_page && (
                                  <button
                                    onClick={() => handleJumpToPage(kp.source_page!)}
                                    className="flex-shrink-0 text-[10px] font-bold text-blue-600 hover:text-blue-800 bg-blue-50 px-1.5 py-0.5 rounded"
                                  >
                                    Pg {kp.source_page}
                                  </button>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Section 4: Structured Fields Table (Editable & Grounded) */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div
                        className="bg-slate-50 px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => setExpanded(e => ({ ...e, fields: !e.fields }))}
                      >
                        <div className="flex items-center space-x-2">
                          <Database className="w-4 h-4 text-[#112d4e]" />
                          <span className="text-xs font-bold text-slate-800">Structured Fields</span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800">
                            {runData.structured_fields?.length || 0}
                          </span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="text-[11px] text-slate-400">Click field to edit value</span>
                          <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${expanded.fields ? 'rotate-180' : ''}`} />
                        </div>
                      </div>

                      {expanded.fields && (
                        <div className="p-4 bg-white border-t border-slate-100 space-y-3">
                          <div className="relative">
                            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                            <input
                              type="text"
                              placeholder="Search structured fields…"
                              value={fieldFilter}
                              onChange={(e) => setFieldFilter(e.target.value)}
                              className="w-full text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                            />
                          </div>

                          <div className="divide-y divide-slate-100 border border-slate-100 rounded-lg overflow-hidden">
                            {filteredFields.map((field) => (
                              <div key={field.id} className="p-3 hover:bg-slate-50/80 transition-colors space-y-2">
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center space-x-2">
                                    <span className="text-xs font-bold text-slate-900">{field.label}</span>
                                    {field.required && (
                                      <span className="text-[10px] font-bold text-red-600 bg-red-50 px-1 rounded">
                                        Required
                                      </span>
                                    )}
                                    <span className="text-[10px] font-mono text-slate-400">
                                      [{field.data_type}]
                                    </span>
                                  </div>

                                  <div className="flex items-center space-x-2">
                                    {field.source_page && (
                                      <button
                                        onClick={() => handleJumpToPage(field.source_page!)}
                                        className="flex items-center space-x-1 px-2 py-0.5 rounded bg-blue-50 hover:bg-blue-100 text-blue-700 text-[10px] font-bold transition-colors"
                                        title="View on page"
                                      >
                                        <span>Page {field.source_page}</span>
                                        <ArrowRight className="w-2.5 h-2.5" />
                                      </button>
                                    )}

                                    <label className="flex items-center space-x-1 cursor-pointer" title="Mark as reviewed by officer">
                                      <input
                                        type="checkbox"
                                        checked={Boolean(field.reviewed)}
                                        onChange={() => handleFieldReviewedToggle(field.id)}
                                        className="w-3.5 h-3.5 rounded text-[#0f5132] focus:ring-0 cursor-pointer"
                                      />
                                      <span className="text-[10px] text-slate-500 font-semibold">Reviewed</span>
                                    </label>
                                  </div>
                                </div>

                                {/* Field Value Input */}
                                <div>
                                  {field.data_type === 'array' ? (
                                    <input
                                      type="text"
                                      value={Array.isArray(field.value) ? field.value.map((x: any) => typeof x === 'object' ? JSON.stringify(x) : String(x)).join(', ') : getFieldValueString(field.value)}
                                      onChange={(e) => {
                                        const arr = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
                                        handleFieldChange(field.id, arr);
                                      }}
                                      placeholder="Comma-separated items…"
                                      className="w-full text-xs px-2.5 py-1.5 border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                                    />
                                  ) : (
                                    <input
                                      type={field.data_type === 'number' ? 'number' : 'text'}
                                      value={getFieldValueString(field.value)}
                                      onChange={(e) => handleFieldChange(field.id, field.data_type === 'number' ? parseFloat(e.target.value) || 0 : e.target.value)}
                                      placeholder={`Enter ${field.label.toLowerCase()}…`}
                                      className="w-full text-xs px-2.5 py-1.5 border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                                    />
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {/* ═════════════════════════════════════════════════════════════ */}
                {/* TAB 2: CONFIG & SCHEMA BUILDER                               */}
                {/* ═════════════════════════════════════════════════════════════ */}
                {activeTab === 'config' && (
                  <div className="space-y-5">
                    {/* Project Settings Banner */}
                    <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center space-x-2">
                            <h2 className="text-xs font-bold text-slate-900">
                              {configData?.name || 'FIR Standard Extraction'}
                            </h2>
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800">
                              v{configData?.version || 1}
                            </span>
                            {sarvamConfigId ? (
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-800 border border-purple-200">
                                Sarvam Config ID: {sarvamConfigId}
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-[#0f5132] border border-emerald-200">
                                Inline Schema (Active)
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-500 mt-0.5">
                            Local Config ID: <code className="font-mono text-slate-700">{configData?.id || 'cfg-default-fir'}</code>
                          </p>
                        </div>

                        <div className="flex items-center space-x-2">
                          <button
                            onClick={() => setRawSchemaMode(!rawSchemaMode)}
                            className="px-2.5 py-1 bg-white border border-slate-300 hover:bg-slate-100 rounded text-xs font-semibold text-slate-700 flex items-center space-x-1"
                          >
                            <Code className="w-3.5 h-3.5 text-purple-600" />
                            <span>{rawSchemaMode ? 'Visual Form' : 'Raw JSON Schema'}</span>
                          </button>
                        </div>
                      </div>

                      {/* Optional Sarvam Workbench Config ID Input */}
                      <div className="pt-2 border-t border-slate-200/80 flex items-center space-x-3 text-xs">
                        <label className="text-slate-600 font-medium whitespace-nowrap">
                          Sarvam Workbench Config ID (Optional):
                        </label>
                        <input
                          type="text"
                          value={sarvamConfigId}
                          onChange={(e) => setSarvamConfigId(e.target.value)}
                          placeholder="e.g. cfg_01a14d41... (Leave blank to use inline schema)"
                          className="flex-1 px-2.5 py-1 text-xs border border-slate-300 rounded-md font-mono focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                        />
                      </div>
                    </div>

                    {/* Output Format / Schema Section */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div className="bg-slate-50 px-4 py-3 flex items-center justify-between border-b border-slate-200">
                        <div>
                          <div className="text-xs font-bold text-slate-800">
                            Output Format / Structured Schema
                          </div>
                          <div className="text-[10px] text-slate-400">
                            Define the target JSON schema fields extracted from FIR evidence
                          </div>
                        </div>

                        {!rawSchemaMode && (
                          <button
                            onClick={() => setShowAddFieldModal(true)}
                            className="flex items-center space-x-1 px-2.5 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-semibold shadow-sm transition-colors"
                          >
                            <Plus className="w-3.5 h-3.5" />
                            <span>Add Field</span>
                          </button>
                        )}
                      </div>

                      <div className="p-4 bg-white">
                        {rawSchemaMode ? (
                          <div className="space-y-2">
                            <textarea
                              rows={14}
                              value={rawSchemaText}
                              onChange={(e) => {
                                setRawSchemaText(e.target.value);
                                setValidationResult(null);
                              }}
                              className="w-full text-xs font-mono p-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#112d4e]"
                            />
                            <div className="flex items-center justify-between">
                              <button
                                onClick={() => handleValidateSchema(rawSchemaText)}
                                className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-semibold"
                              >
                                Validate Schema JSON
                              </button>
                              {validationResult && (
                                <span className={`text-xs font-semibold ${validationResult.valid ? 'text-emerald-700' : 'text-red-700'}`}>
                                  {validationResult.valid ? `✓ Valid JSON (${validationResult.message})` : `✗ ${validationResult.message}`}
                                </span>
                              )}
                            </div>
                          </div>
                        ) : (
                          <div className="divide-y divide-slate-100 border border-slate-100 rounded-lg overflow-hidden">
                            {schemaFields.map((field, idx) => (
                              <div key={field.id || idx} className="p-3 flex items-center justify-between hover:bg-slate-50 transition-colors">
                                <div className="space-y-0.5">
                                  <div className="flex items-center space-x-2">
                                    <span className="text-xs font-bold text-slate-900">{field.label}</span>
                                    <span className="text-[10px] font-mono text-slate-400">({field.key})</span>
                                    {field.required && (
                                      <span className="text-[10px] font-bold text-red-600 bg-red-50 px-1 rounded">Required</span>
                                    )}
                                  </div>
                                  <div className="text-[11px] text-slate-500">
                                    Type: <span className="font-semibold text-slate-700">{field.data_type}</span>
                                    {field.description ? ` • ${field.description}` : ''}
                                  </div>
                                </div>

                                <button
                                  onClick={() => handleDeleteField(idx)}
                                  className="p-1 text-slate-400 hover:text-red-600 transition-colors"
                                  title="Delete field"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Additional Extraction Instructions */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div className="bg-slate-50 px-4 py-3 border-b border-slate-200">
                        <div className="text-xs font-bold text-slate-800">
                          Additional Extraction Instructions
                        </div>
                        <div className="text-[10px] text-slate-400">
                          Defensive system prompt directives enforcing factual grounding & zero unauthorized assumptions
                        </div>
                      </div>

                      <div className="p-4 bg-white">
                        <textarea
                          rows={6}
                          value={instructionsText}
                          onChange={(e) => setInstructionsText(e.target.value)}
                          className="w-full text-xs font-mono p-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#112d4e]"
                          placeholder="Enter extraction prompt rules…"
                        />
                      </div>
                    </div>

                    {/* Bottom Action Bar */}
                    <div className="flex items-center justify-end space-x-3 pt-2">
                      <button
                        onClick={handleSaveConfig}
                        className="flex items-center space-x-1.5 px-4 py-2 bg-[#112d4e] hover:bg-[#0c223c] text-white text-xs font-bold rounded-lg shadow-sm transition-colors"
                      >
                        <Save className="w-4 h-4 text-amber-300" />
                        <span>Save Configuration</span>
                      </button>

                      {runData && (
                        <button
                          onClick={handleRegenerate}
                          disabled={extracting}
                          className="flex items-center space-x-1.5 px-4 py-2 bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold rounded-lg shadow-sm transition-colors disabled:opacity-50"
                        >
                          <RefreshCw className={`w-4 h-4 ${extracting ? 'animate-spin' : ''}`} />
                          <span>{extracting ? 'Extracting…' : 'Regenerate Extraction'}</span>
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── MODAL: ADD SCHEMA FIELD ────────────────────────────────────────── */}
      {showAddFieldModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-5 space-y-4 border border-slate-200 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900">Add Schema Field</h3>
              <button onClick={() => setShowAddFieldModal(false)} className="text-slate-400 hover:text-slate-700 font-bold">
                ×
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Field Label *</label>
                <input
                  type="text"
                  placeholder="e.g. Seizure Panchanama Date"
                  value={newFieldData.label}
                  onChange={(e) => {
                    const l = e.target.value;
                    const autoKey = l.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_');
                    setNewFieldData({ ...newFieldData, label: l, key: newFieldData.key ? newFieldData.key : autoKey });
                  }}
                  className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Field Key (JSON property) *</label>
                <input
                  type="text"
                  placeholder="e.g. panchanama_date"
                  value={newFieldData.key}
                  onChange={(e) => setNewFieldData({ ...newFieldData, key: e.target.value })}
                  className="w-full px-3 py-1.5 border border-slate-300 rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Data Type</label>
                  <select
                    value={newFieldData.data_type}
                    onChange={(e) => setNewFieldData({ ...newFieldData, data_type: e.target.value })}
                    className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                  >
                    <option value="string">String</option>
                    <option value="number">Number</option>
                    <option value="boolean">Boolean</option>
                    <option value="array">Array (List)</option>
                    <option value="object">Object</option>
                  </select>
                </div>

                <div className="flex items-center pt-5">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newFieldData.required}
                      onChange={(e) => setNewFieldData({ ...newFieldData, required: e.target.checked })}
                      className="w-4 h-4 rounded text-red-600 focus:ring-0"
                    />
                    <span className="font-semibold text-slate-700">Required Field</span>
                  </label>
                </div>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Description</label>
                <input
                  type="text"
                  placeholder="Extraction instructions for AI model…"
                  value={newFieldData.description}
                  onChange={(e) => setNewFieldData({ ...newFieldData, description: e.target.value })}
                  className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#112d4e]"
                />
              </div>
            </div>

            <div className="flex items-center justify-end space-x-2 pt-3 border-t border-slate-100">
              <button
                onClick={() => setShowAddFieldModal(false)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={handleAddField}
                className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg shadow-sm"
              >
                Add Field
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: CONFIRM & REGISTER CASE ─────────────────────────────────── */}
      {showConfirmModal && runData && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6 space-y-4 border border-slate-200 animate-in fade-in zoom-in-95">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-emerald-100 text-[#0f5132] rounded-lg">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">Confirm & Register Case</h3>
                <p className="text-xs text-slate-500">Save reviewed particulars to the official Case Management registry</p>
              </div>
            </div>

            <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200 text-xs space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-500">FIR / Crime Number:</span>
                <span className="font-bold text-slate-900">
                  {runData.structured_fields.find(f => f.key === 'fir_number')?.value || 'Auto-generated'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Station & District:</span>
                <span className="font-semibold text-slate-800">
                  {runData.structured_fields.find(f => f.key === 'station')?.value || user?.station} | {runData.structured_fields.find(f => f.key === 'district')?.value || user?.district}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Offence Nature:</span>
                <span className="font-semibold text-slate-800 truncate max-w-[260px]">
                  {runData.structured_fields.find(f => f.key === 'offence_nature')?.value || 'Under Investigation'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Accused Persons:</span>
                <span className="font-semibold text-slate-800">
                  {runData.entities.filter(e => e.type === 'ACCUSED').length} identified
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-600">
              Confirming will store these particulars in the database, associate the evidence document,
              and trigger the automated FIR Folders classification workflow.
            </p>

            <div className="flex items-center justify-end space-x-2 pt-3 border-t border-slate-100">
              <button
                onClick={() => setShowConfirmModal(false)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmAndRegister}
                disabled={confirmingCase}
                className="px-4 py-1.5 bg-[#0f5132] hover:bg-[#0a3d26] text-white text-xs font-bold rounded-lg shadow-sm flex items-center space-x-1.5 disabled:opacity-50"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-300" />
                <span>{confirmingCase ? 'Registering…' : 'Confirm & Save Case'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: CONFIRMATION SUCCESS ────────────────────────────────────── */}
      {confirmedResult && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 text-center space-y-4 border border-slate-200">
            <div className="w-12 h-12 bg-emerald-100 text-[#0f5132] rounded-full flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-slate-900">Case Successfully Registered</h3>
            <p className="text-xs text-slate-600">
              FIR <span className="font-mono font-bold text-[#0f5132]">{confirmedResult.firNumber}</span> has been saved and classified into FIR folders.
            </p>
            <div className="flex items-center justify-center space-x-3 pt-2">
              <button
                onClick={() => navigate(`/cases/${confirmedResult.caseId}`)}
                className="px-4 py-2 bg-[#112d4e] hover:bg-[#0c223c] text-white text-xs font-bold rounded-lg shadow-sm flex items-center space-x-1"
              >
                <span>Open Case Detail</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setConfirmedResult(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg"
              >
                Stay in Workspace
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DocumentExtractionWorkspace;

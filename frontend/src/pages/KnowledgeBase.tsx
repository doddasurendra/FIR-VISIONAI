import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  BookOpen, Plus, Search, FileText, RefreshCw, Trash2, RotateCcw, AlertTriangle, CheckCircle2,
  ExternalLink, Eye, X, Upload, ShieldCheck, Scale, ChevronDown, ChevronUp, ChevronLeft, ChevronRight,
  BookMarked, Gavel, Info, Clock, Layers, SlidersHorizontal,
} from 'lucide-react';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';

interface KBDocument {
  id: string;
  case_id: string | null;
  original_filename: string;
  document_title: string;
  doc_category: string;
  source_department: string | null;
  version_date: string | null;
  district: string;
  station: string | null;
  physical_page_count: number;
  mime_type: string;
  file_hash: string;
  is_verified_official: boolean;
  source_type: string;
  record_kind: string | null;
  source_url: string | null;
  issuing_authority: string | null;
  reference_number: string | null;
  jurisdiction: string | null;
  publication_date: string | null;
  commencement_date: string | null;
  legal_status: string | null;
  is_archived: boolean;
  archive_reason: string | null;
  archived_at: string | null;
  replaced_by_id: string | null;
  replaces_id: string | null;
  replacement_reason: string | null;
  status: string;
  index_status: string;
  indexed_chunk_count: number;
  embedded_chunk_count: number;
  error_message: string | null;
  match: { excerpt: string; physical_page_number: number } | null;
  created_at: string;
  created_by: string;
}

interface IngestionJob {
  id: string;
  status: string;
  stage: string | null;
  trigger: string | null;
  pages_total: number;
  pages_with_text: number;
  chunks_written: number;
  chunks_embedded: number;
  error_message: string | null;
  warnings: string[];
  started_at: string | null;
  finished_at: string | null;
}

interface DocumentDetail {
  id: string;
  document_title: string;
  original_filename: string;
  doc_category: string;
  mime_type: string;
  file_hash: string;
  source_type: string;
  record_kind: string | null;
  source_url: string | null;
  issuing_authority: string | null;
  reference_number: string | null;
  jurisdiction: string | null;
  publication_date: string | null;
  commencement_date: string | null;
  version_date: string | null;
  legal_status: string | null;
  language: string | null;
  last_verified_at: string | null;
  verification_note: string | null;
  is_archived: boolean;
  status: string;
  index_status: string;
  error_message: string | null;
  physical_page_count: number;
  pages_total: number;
  pages_with_text: number;
  chunk_count: number;
  embedded_chunk_count: number;
  embedding_model: string | null;
  indexed_at: string | null;
  sections: string[];
  legal_provisions: number;
  can_manage: boolean;
  ingestion_jobs: IngestionJob[];
  page_from: number;
  page_size: number;
  pages: { physical_page_number: number; text: string; ocr_applied: boolean; is_unreadable: boolean }[];
}

interface KBStats {
  total: number;
  by_category: Record<string, number>;
  by_index_status: Record<string, number>;
  by_source_type: Record<string, number>;
}

interface LegalAct {
  act_name: string;
  document_title: string;
  category: string;
  jurisdiction: string;
  effective_date: string | null;
  repeal_date: string | null;
  version: string | null;
  source_url: string | null;
  document_id: string | null;
  source_type: string;
  section_count: number;
  is_historical: boolean;
}

interface LegalSection {
  id: string;
  section_number: string;
  section_title: string;
  full_text: string;
  explanation: string | null;
  essential_ingredients_json: string;
  penalty_text: string | null;
  effective_date: string | null;
  repeal_date: string | null;
  jurisdiction: string;
  source_url: string | null;
  source_gazette: string | null;
  category: string;
  is_historical: boolean;
  source_type: string;
  document_id: string | null;
  physical_page_number: number | null;
}

interface LegalStats {
  total_sections: number;
  total_acts: number;
  active_sections: number;
  historical_sections: number;
  by_category: Record<string, number>;
}

const PAGE_SIZE = 25;
const DETAIL_PAGE_SIZE = 5;

const CATEGORY_LABELS: Record<string, { label: string; color: string }> = {
  ALL: { label: 'All Documents', color: 'bg-slate-100 text-slate-700' },
  LEGAL_ACT: { label: 'Official Laws & Sections', color: 'bg-emerald-100 text-emerald-800' },
  CIRCULAR: { label: 'Circulars & Orders', color: 'bg-blue-100 text-blue-800' },
  SEIZURE_REPORT: { label: 'Seizure Reports', color: 'bg-amber-100 text-amber-800' },
  INVESTIGATION_GUIDE: { label: 'Investigation Guides & SOPs', color: 'bg-purple-100 text-purple-800' },
  REFERENCE: { label: 'Reference Materials', color: 'bg-indigo-100 text-indigo-800' },
  HISTORICAL_FIR: { label: 'Historical FIR Records', color: 'bg-rose-100 text-rose-800' },
  EVIDENCE: { label: 'Approved Evidence', color: 'bg-cyan-100 text-cyan-800' },
};

const SOURCE_META: Record<string, { label: string; color: string; hint: string }> = {
  OFFICIAL: { label: 'Official source', color: 'bg-emerald-50 text-emerald-800 border-emerald-300', hint: 'Imported from a verified government source' },
  SECONDARY: { label: 'Secondary', color: 'bg-sky-50 text-sky-800 border-sky-300', hint: 'Explanatory or training material, not the authoritative text' },
  SYNTHETIC: { label: 'Synthetic / demo', color: 'bg-fuchsia-50 text-fuchsia-800 border-fuchsia-300', hint: 'Sample data for demonstration or testing, not a government record' },
  UNVERIFIED: { label: 'Unverified', color: 'bg-slate-50 text-slate-600 border-slate-300', hint: 'Provenance has not been verified' },
};

const INDEX_META: Record<string, { label: string; color: string }> = {
  INDEXED: { label: 'Indexed', color: 'bg-emerald-100 text-emerald-800' },
  PARTIALLY_INDEXED: { label: 'Partially indexed', color: 'bg-amber-100 text-amber-800' },
  NEEDS_REVIEW: { label: 'Needs review', color: 'bg-orange-100 text-orange-800' },
  FAILED: { label: 'Failed', color: 'bg-red-100 text-red-800' },
  NOT_INDEXED: { label: 'Not indexed', color: 'bg-slate-100 text-slate-600' },
};

const LEGAL_STATUS_LABELS: Record<string, string> = {
  IN_FORCE: 'In force', AMENDED: 'Amended', REPEALED: 'Repealed', SUPERSEDED: 'Superseded',
  HISTORICAL: 'Historical', UNKNOWN: 'Status unknown',
};

const LEGAL_CATEGORY_COLORS: Record<string, string> = {
  CONSTITUTIONAL: 'bg-orange-100 text-orange-800 border-orange-200',
  CRIMINAL_CENTRAL: 'bg-red-100 text-red-800 border-red-200',
  CRIMINAL_HISTORICAL: 'bg-gray-100 text-gray-600 border-gray-200',
  SPECIAL_CENTRAL: 'bg-blue-100 text-blue-800 border-blue-200',
  STATE_EXCISE_PROHIBITION: 'bg-emerald-100 text-emerald-800 border-emerald-200',
};

const LEGAL_CATEGORY_LABELS: Record<string, string> = {
  CONSTITUTIONAL: 'Constitution of India',
  CRIMINAL_CENTRAL: 'Core Criminal Laws (BNS/BNSS/BSA)',
  CRIMINAL_HISTORICAL: 'Historical Laws (IPC/CrPC/IEA)',
  SPECIAL_CENTRAL: 'Special Central Acts',
  STATE_EXCISE_PROHIBITION: 'AP State Laws & Procedures',
};

const RETRYABLE = new Set(['FAILED', 'NEEDS_REVIEW', 'STALLED', 'PARTIALLY_INDEXED']);

function errorText(err: any, fallback: string): string {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object' && d.message) return d.message;
  return fallback;
}

function viewUrl(docId: string, page?: number | null): string {
  const token = encodeURIComponent(localStorage.getItem('fir_sahayak_token') || '');
  return `/api/v1/documents/${docId}/view?token=${token}${page ? `#page=${page}` : ''}`;
}

const StatusBadge: React.FC<{ doc: { status: string; index_status: string; is_archived?: boolean } }> = ({ doc }) => {
  if (doc.is_archived) {
    return <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">Archived</span>;
  }
  if (doc.status === 'PROCESSING' || doc.status === 'PENDING') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800">
        <RefreshCw className="w-3 h-3 animate-spin" /> Processing
      </span>
    );
  }
  if (doc.status === 'STALLED') {
    return (
      <span title="Processing stopped without finishing; retry to resume" className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800">
        <Clock className="w-3 h-3" /> Stalled
      </span>
    );
  }
  const key = doc.status === 'FAILED' ? 'FAILED' : doc.status === 'NEEDS_REVIEW' ? 'NEEDS_REVIEW' : (doc.index_status || 'NOT_INDEXED');
  const meta = INDEX_META[key] || INDEX_META.NOT_INDEXED;
  return <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${meta.color}`}>{meta.label}</span>;
};

const SourceBadge: React.FC<{ sourceType: string }> = ({ sourceType }) => {
  const meta = SOURCE_META[sourceType] || SOURCE_META.UNVERIFIED;
  return (
    <span title={meta.hint} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-semibold ${meta.color}`}>
      {sourceType === 'OFFICIAL' && <ShieldCheck className="w-3 h-3" />}
      {meta.label}
    </span>
  );
};

export const KnowledgeBase: React.FC = () => {
  const { user } = useAuth();
  const isState = user?.role === 'STATE';
  const canAddStatewide = user?.role === 'STATE' || user?.role === 'DISTRICT';

  // ── List, filters and paging ─────────────────────────────────────────────
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<KBStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [searchContent, setSearchContent] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [showArchived, setShowArchived] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [indexStatus, setIndexStatus] = useState('');
  const [sourceType, setSourceType] = useState('');
  const [legalStatus, setLegalStatus] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sort, setSort] = useState('newest');
  const [page, setPage] = useState(0);

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Debounce the search box
  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput.trim()); setPage(0); }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => { setPage(0); }, [selectedCategory, showArchived, indexStatus, sourceType, legalStatus, jurisdiction, dateFrom, dateTo, sort, searchContent]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get('/documents/kb-stats', { params: { include_archived: showArchived } });
      setStats(res.data);
    } catch { /* counts are informational */ }
  }, [showArchived]);

  const fetchDocuments = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setListError(null);
    try {
      const params: Record<string, any> = { include_archived: showArchived, limit: PAGE_SIZE, skip: page * PAGE_SIZE, sort };
      if (selectedCategory !== 'ALL') params.category = selectedCategory;
      if (search) { params.search = search; params.search_content = searchContent; }
      if (indexStatus) params.index_status = indexStatus;
      if (sourceType) params.source_type = sourceType;
      if (legalStatus) params.legal_status = legalStatus;
      if (jurisdiction.trim()) params.jurisdiction = jurisdiction.trim();
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await api.get('/documents/', { params });
      setDocuments(res.data?.documents || []);
      setTotal(res.data?.total || 0);
    } catch (err: any) {
      setListError(errorText(err, 'Could not load Knowledge Base documents.'));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [selectedCategory, search, searchContent, showArchived, indexStatus, sourceType, legalStatus, jurisdiction, dateFrom, dateTo, sort, page]);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  // Keep refreshing while any visible document is still processing
  const processing = documents.some((d) => d.status === 'PROCESSING' || d.status === 'PENDING');
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(() => { fetchDocuments(true); fetchStats(); }, 4000);
    return () => clearInterval(t);
  }, [processing, fetchDocuments, fetchStats]);

  const refreshAll = () => { fetchDocuments(); fetchStats(); };

  const categoryCount = (key: string): number | undefined => {
    if (!stats) return undefined;
    if (key === 'ALL') return stats.total;
    if (key === 'HISTORICAL_FIR') return (stats.by_category.HISTORICAL_FIR || 0) + (stats.by_category.FIR || 0);
    return stats.by_category[key] || 0;
  };

  const activeFilterCount = [indexStatus, sourceType, legalStatus, jurisdiction, dateFrom, dateTo].filter(Boolean).length;
  const clearFilters = () => { setIndexStatus(''); setSourceType(''); setLegalStatus(''); setJurisdiction(''); setDateFrom(''); setDateTo(''); };

  // ── Legal Act & Section browser ──────────────────────────────────────────
  const [showLegalBrowser, setShowLegalBrowser] = useState(false);
  const [legalStats, setLegalStats] = useState<LegalStats | null>(null);
  const [legalActs, setLegalActs] = useState<LegalAct[]>([]);
  const [legalActsLoading, setLegalActsLoading] = useState(false);
  const [selectedLegalCategory, setSelectedLegalCategory] = useState<string>('');
  const [selectedAct, setSelectedAct] = useState<LegalAct | null>(null);
  const [actSections, setActSections] = useState<LegalSection[]>([]);
  const [sectionsLoading, setSectionsLoading] = useState(false);
  const [sectionFilter, setSectionFilter] = useState('');
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  const fetchLegalStats = useCallback(async () => {
    try { setLegalStats((await api.get('/legal/stats')).data); } catch { /* informational */ }
  }, []);

  const fetchLegalActs = useCallback(async () => {
    setLegalActsLoading(true);
    try {
      const params: Record<string, string> = {};
      if (selectedLegalCategory) params.category = selectedLegalCategory;
      setLegalActs((await api.get('/legal/acts', { params })).data.acts || []);
    } catch { setLegalActs([]); } finally { setLegalActsLoading(false); }
  }, [selectedLegalCategory]);

  const fetchActSections = useCallback(async (act: LegalAct) => {
    setSelectedAct(act);
    setSectionsLoading(true);
    setActSections([]);
    setSectionFilter('');
    try {
      const params: Record<string, string> = { act_name: act.act_name };
      if (act.document_id) params.document_id = act.document_id;
      setActSections((await api.get('/legal/acts/sections', { params })).data.sections || []);
    } catch { setActSections([]); } finally { setSectionsLoading(false); }
  }, []);

  useEffect(() => {
    if (showLegalBrowser) { fetchLegalStats(); fetchLegalActs(); }
  }, [showLegalBrowser, fetchLegalStats, fetchLegalActs]);

  // ── Upload ────────────────────────────────────────────────────────────────
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadCategory, setUploadCategory] = useState(canAddStatewide ? 'CIRCULAR' : 'SEIZURE_REPORT');
  const [uploadSourceType, setUploadSourceType] = useState('UNVERIFIED');
  const [uploadRecordKind, setUploadRecordKind] = useState('');
  const [uploadAuthority, setUploadAuthority] = useState('');
  const [uploadReference, setUploadReference] = useState('');
  const [uploadJurisdiction, setUploadJurisdiction] = useState('');
  const [uploadSourceUrl, setUploadSourceUrl] = useState('');
  const [uploadPublication, setUploadPublication] = useState('');
  const [uploadCommencement, setUploadCommencement] = useState('');
  const [uploadLegalStatus, setUploadLegalStatus] = useState('');
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [duplicateOf, setDuplicateOf] = useState<{ id: string; title: string } | null>(null);

  const resetUpload = () => {
    setUploadFile(null); setUploadTitle(''); setUploadSourceType('UNVERIFIED'); setUploadRecordKind('');
    setUploadAuthority(''); setUploadReference(''); setUploadJurisdiction(''); setUploadSourceUrl('');
    setUploadPublication(''); setUploadCommencement(''); setUploadLegalStatus('');
    setUploadProgress(0); setUploadError(null); setDuplicateOf(null);
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !uploadTitle.trim()) { setUploadError('Choose a file and enter the document title.'); return; }
    if (uploadSourceType === 'OFFICIAL' && !uploadSourceUrl.trim()) { setUploadError('Official documents need the official source URL.'); return; }
    setUploadLoading(true); setUploadError(null); setDuplicateOf(null); setUploadProgress(0);
    try {
      const fd = new FormData();
      fd.append('file', uploadFile);
      fd.append('document_title', uploadTitle.trim());
      fd.append('category', uploadCategory);
      fd.append('source_type', uploadSourceType);
      const optional: Record<string, string> = {
        record_kind: uploadRecordKind, issuing_authority: uploadAuthority, reference_number: uploadReference,
        jurisdiction: uploadJurisdiction, source_url: uploadSourceUrl, publication_date: uploadPublication,
        commencement_date: uploadCommencement, legal_status: uploadLegalStatus,
      };
      Object.entries(optional).forEach(([k, v]) => { if (v.trim()) fd.append(k, v.trim()); });
      if (uploadAuthority.trim()) fd.append('source_department', uploadAuthority.trim());
      if (uploadPublication) fd.append('version_date', uploadPublication);
      const res = await api.post('/documents/knowledge-base/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (p) => { if (p.total) setUploadProgress(Math.round((p.loaded / p.total) * 100)); },
      });
      setActionSuccess(`"${res.data.document_title}" was uploaded. Text extraction and indexing are running; the status updates automatically.`);
      setShowUploadModal(false);
      resetUpload();
      refreshAll();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 409 && detail?.duplicate_document_id) {
        setDuplicateOf({ id: detail.duplicate_document_id, title: detail.duplicate_title });
        setUploadError(detail.message);
      } else {
        setUploadError(errorText(err, 'Upload failed. Use a PDF, DOCX, TXT, JPG, PNG or WEBP file up to 50 MB.'));
      }
    } finally {
      setUploadLoading(false);
    }
  };

  // ── Replace / archive / restore / retry ──────────────────────────────────
  const [selectedDocForAction, setSelectedDocForAction] = useState<KBDocument | null>(null);
  const [showReplaceModal, setShowReplaceModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [actionReason, setActionReason] = useState('');
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [replaceReason, setReplaceReason] = useState('');
  const [replaceLoading, setReplaceLoading] = useState(false);

  const handleReplaceSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDocForAction || !replaceFile || !replaceReason.trim()) {
      setActionError('Choose the replacement file and enter the reason for replacement.');
      return;
    }
    setReplaceLoading(true); setActionError(null);
    try {
      const fd = new FormData();
      fd.append('file', replaceFile);
      fd.append('reason', replaceReason.trim());
      await api.post(`/documents/${selectedDocForAction.id}/replace`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setActionSuccess(`Document replaced with "${replaceFile.name}". The previous version was archived.`);
      setShowReplaceModal(false); setSelectedDocForAction(null); setReplaceFile(null); setReplaceReason('');
      refreshAll();
    } catch (err: any) {
      setActionError(errorText(err, 'Document replacement failed.'));
    } finally {
      setReplaceLoading(false);
    }
  };

  const handleArchiveConfirm = async () => {
    if (!selectedDocForAction || deleteConfirmText !== 'ARCHIVE' || !actionReason.trim()) return;
    try {
      await api.delete(`/documents/${selectedDocForAction.id}`, { params: { reason: actionReason.trim() } });
      setActionSuccess(`"${selectedDocForAction.document_title}" was archived and removed from search and the assistant.`);
      setShowDeleteModal(false); setSelectedDocForAction(null); setActionReason(''); setDeleteConfirmText('');
      refreshAll();
    } catch (err: any) {
      setActionError(errorText(err, 'Could not archive the document.'));
    }
  };

  const handleRestore = async (doc: KBDocument) => {
    try {
      await api.post(`/documents/${doc.id}/restore`);
      setActionSuccess(`"${doc.document_title}" was restored.`);
      refreshAll();
    } catch (err: any) {
      setActionError(errorText(err, 'Could not restore the document.'));
    }
  };

  const handleRetry = async (docId: string, mode: 'full' | 'reindex') => {
    try {
      await api.post(`/documents/${docId}/reprocess`, null, { params: { mode } });
      setActionSuccess(mode === 'full' ? 'Re-extraction started from the original file.' : 'Re-indexing started from the stored text.');
      refreshAll();
      if (detail?.id === docId) loadDetail(docId, 1);
    } catch (err: any) {
      setActionError(errorText(err, 'Could not start reprocessing.'));
    }
  };

  // ── Document detail panel ────────────────────────────────────────────────
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailIdRef = useRef<string | null>(null);

  const loadDetail = useCallback(async (docId: string, pageFrom: number) => {
    detailIdRef.current = docId;
    setDetailLoading(true); setDetailError(null);
    try {
      const res = await api.get(`/documents/${docId}/detail`, { params: { page_from: pageFrom, page_size: DETAIL_PAGE_SIZE } });
      if (detailIdRef.current === docId) setDetail(res.data);
    } catch (err: any) {
      setDetailError(errorText(err, 'Could not load document details.'));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const closeDetail = () => { detailIdRef.current = null; setDetail(null); setDetailError(null); };

  // ── Render ────────────────────────────────────────────────────────────────
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filteredSections = sectionFilter.trim()
    ? actSections.filter((s) => `${s.section_number} ${s.section_title} ${s.full_text}`.toLowerCase().includes(sectionFilter.toLowerCase()))
    : actSections;

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-[#0f5132]/10 rounded-xl text-[#0f5132]">
            <BookOpen className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-slate-900">Knowledge Base & Legal Corpus</h1>
              {stats && (
                <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full border border-emerald-300">
                  {stats.by_source_type.OFFICIAL || 0} official source{(stats.by_source_type.OFFICIAL || 0) === 1 ? '' : 's'}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Laws, circulars, seizure formats, investigation guides and records you are authorised to see. Each document shows where it came from and whether it is searchable.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowLegalBrowser(!showLegalBrowser)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold transition-colors border ${
              showLegalBrowser ? 'bg-indigo-700 text-white border-indigo-700' : 'bg-white text-indigo-700 border-indigo-300 hover:bg-indigo-50'
            }`}
          >
            <Scale className="w-4 h-4" />
            <span>Act & Section Browser</span>
            {legalStats && <span className="bg-indigo-500/20 text-xs px-1.5 py-0.5 rounded-full font-bold">{legalStats.total_acts} Acts</span>}
          </button>
          <button
            onClick={() => { resetUpload(); setShowUploadModal(true); }}
            className="flex items-center gap-1.5 px-4 py-2 bg-[#0f5132] text-white rounded-lg text-xs font-semibold hover:bg-[#0a3d26] transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>Upload Document</span>
          </button>
        </div>
      </div>

      {/* ─── LEGAL ACT & SECTION BROWSER ─── */}
      {showLegalBrowser && (
        <div className="bg-white rounded-xl border border-indigo-200 shadow-sm overflow-hidden">
          <div className="bg-indigo-700 text-white px-5 py-3.5 flex items-center justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              <Gavel className="w-5 h-5 text-indigo-200" />
              <h2 className="font-bold text-sm">Acts & Sections</h2>
              {legalStats && (
                <div className="flex items-center gap-2 ml-3">
                  <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full">{legalStats.total_acts} Acts</span>
                  <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full">{legalStats.total_sections} Sections</span>
                </div>
              )}
            </div>
            <button onClick={() => setShowLegalBrowser(false)} className="text-white/70 hover:text-white" aria-label="Close Act browser">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex flex-col md:flex-row" style={{ minHeight: '420px' }}>
            <div className="md:w-80 flex-shrink-0 border-b md:border-b-0 md:border-r border-slate-200 bg-slate-50 flex flex-col">
              <div className="p-3 border-b border-slate-200">
                <select
                  value={selectedLegalCategory}
                  onChange={(e) => { setSelectedLegalCategory(e.target.value); setSelectedAct(null); setActSections([]); }}
                  className="w-full text-xs border border-slate-300 rounded-md px-2 py-1.5 bg-white focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                >
                  <option value="">All Categories</option>
                  {Object.entries(LEGAL_CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div className="flex-1 overflow-y-auto max-h-[520px]">
                {legalActsLoading ? (
                  <div className="py-8 text-center text-xs text-slate-400">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-400" /> Loading acts...
                  </div>
                ) : legalActs.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-400">No acts found.</div>
                ) : (
                  legalActs.map((act) => {
                    const key = `${act.act_name}|${act.document_id || ''}`;
                    const isSel = selectedAct && `${selectedAct.act_name}|${selectedAct.document_id || ''}` === key;
                    return (
                      <button
                        key={key}
                        onClick={() => fetchActSections(act)}
                        className={`w-full text-left px-3 py-3 border-b border-slate-100 transition-colors hover:bg-indigo-50 ${isSel ? 'bg-indigo-100 border-l-2 border-l-indigo-600' : ''}`}
                      >
                        <div className="flex items-start justify-between gap-1">
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-semibold text-slate-800 leading-tight line-clamp-2">{act.document_title || act.act_name}</p>
                            <div className="flex items-center gap-1 mt-1 flex-wrap">
                              <SourceBadge sourceType={act.source_type} />
                              {act.category && (
                                <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${LEGAL_CATEGORY_COLORS[act.category] || 'bg-slate-100 text-slate-600 border-slate-200'}`}>
                                  {act.category.replace(/_/g, ' ')}
                                </span>
                              )}
                              {act.is_historical && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200 font-bold">REPEALED</span>}
                            </div>
                            <p className="text-[10px] text-slate-400 mt-0.5">{act.jurisdiction}{act.effective_date ? ` • in force from ${act.effective_date}` : ''}</p>
                          </div>
                          <span className="text-[10px] text-indigo-600 font-bold bg-indigo-50 px-1.5 py-0.5 rounded flex-shrink-0">{act.section_count}</span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            <div className="flex-1 min-w-0 overflow-y-auto max-h-[560px]">
              {!selectedAct ? (
                <div className="py-16 text-center text-slate-400 px-4">
                  <BookMarked className="w-12 h-12 mx-auto mb-3 text-indigo-200" />
                  <p className="text-sm font-semibold text-slate-500">Select an Act</p>
                  <p className="text-xs mt-1 text-slate-400">Choose an Act on the left to read its sections. Official sources show the exact page in the original document.</p>
                </div>
              ) : sectionsLoading ? (
                <div className="py-16 text-center">
                  <RefreshCw className="w-7 h-7 animate-spin mx-auto mb-2 text-indigo-500" />
                  <p className="text-xs text-slate-400">Loading sections...</p>
                </div>
              ) : (
                <div>
                  <div className="px-5 py-4 bg-indigo-50 border-b border-indigo-100 space-y-2">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="min-w-0">
                        <h3 className="text-sm font-bold text-indigo-900 leading-tight">{selectedAct.document_title || selectedAct.act_name}</h3>
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          <SourceBadge sourceType={selectedAct.source_type} />
                          <span className="text-xs text-indigo-600">{selectedAct.jurisdiction} • In force from: {selectedAct.effective_date || 'not recorded'}</span>
                        </div>
                        {selectedAct.source_type !== 'OFFICIAL' && (
                          <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1 mt-2">
                            These sections are summaries without a verified official source. Rely on official text for legal decisions.
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-xs text-indigo-700 font-bold bg-indigo-100 px-2 py-1 rounded">{actSections.length} Sections</span>
                        {selectedAct.source_url && (
                          <a href={selectedAct.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline flex items-center gap-1">
                            <ExternalLink className="w-3 h-3" /> Source
                          </a>
                        )}
                      </div>
                    </div>
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                      <input
                        id="kb-section-filter"
                        value={sectionFilter}
                        onChange={(e) => setSectionFilter(e.target.value)}
                        placeholder="Filter sections by number or words…"
                        className="w-full pl-8 pr-3 py-1.5 text-xs border border-indigo-200 rounded-md bg-white focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="divide-y divide-slate-100">
                    {filteredSections.map((sec) => {
                      const isExpanded = expandedSection === sec.id;
                      let ingredients: string[] = [];
                      try { ingredients = JSON.parse(sec.essential_ingredients_json || '[]'); } catch { /* ignore */ }
                      return (
                        <div key={sec.id} className={sec.is_historical ? 'bg-amber-50/30' : ''}>
                          <button onClick={() => setExpandedSection(isExpanded ? null : sec.id)} className="w-full text-left px-5 py-3 hover:bg-slate-50 transition-colors">
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="text-xs font-bold text-indigo-700 flex-shrink-0">{sec.section_number}</span>
                                <span className="text-xs font-semibold text-slate-800 truncate">{sec.section_title}</span>
                              </div>
                              <div className="flex items-center gap-2 flex-shrink-0">
                                {sec.physical_page_number && <span className="text-[10px] text-slate-500">p. {sec.physical_page_number}</span>}
                                {sec.is_historical && <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded border border-amber-200 font-semibold">REPEALED</span>}
                                {isExpanded ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
                              </div>
                            </div>
                          </button>
                          {isExpanded && (
                            <div className="px-5 pb-4 space-y-3 bg-white border-t border-slate-100">
                              <div>
                                <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-1">
                                  {sec.source_type === 'OFFICIAL' ? 'Official text' : 'Summary text (not verified)'}
                                </p>
                                <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">{sec.full_text}</p>
                              </div>
                              {sec.explanation && (
                                <div className="bg-blue-50 rounded-lg p-3 border border-blue-100">
                                  <p className="text-[10px] font-bold uppercase tracking-wide text-blue-600 mb-1">Practical Application</p>
                                  <p className="text-xs text-blue-800">{sec.explanation}</p>
                                </div>
                              )}
                              {ingredients.length > 0 && (
                                <div className="bg-amber-50 rounded-lg p-3 border border-amber-100">
                                  <p className="text-[10px] font-bold uppercase tracking-wide text-amber-700 mb-2">Essential Ingredients to Prove</p>
                                  <ul className="space-y-1">
                                    {ingredients.map((ing, idx) => (
                                      <li key={idx} className="flex items-start gap-1.5 text-xs text-amber-800"><span className="text-amber-500 font-bold">•</span><span>{ing}</span></li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {sec.penalty_text && (
                                <div className="bg-red-50 rounded-lg p-3 border border-red-100">
                                  <p className="text-[10px] font-bold uppercase tracking-wide text-red-600 mb-1">Penalty</p>
                                  <p className="text-xs text-red-800 font-medium">{sec.penalty_text}</p>
                                </div>
                              )}
                              <div className="flex items-center gap-3 pt-1 text-[10px] text-slate-500 flex-wrap">
                                {sec.source_gazette && <span>{sec.source_gazette}</span>}
                                {sec.document_id && sec.physical_page_number && (
                                  <a href={viewUrl(sec.document_id, sec.physical_page_number)} target="_blank" rel="noopener noreferrer" className="text-[#0f5132] hover:underline flex items-center gap-0.5 font-semibold">
                                    <Eye className="w-3 h-3" /> Open page {sec.physical_page_number}
                                  </a>
                                )}
                                {sec.source_url && (
                                  <a href={sec.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline flex items-center gap-0.5">
                                    <ExternalLink className="w-3 h-3" /> Official source
                                  </a>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {filteredSections.length === 0 && (
                      <p className="px-5 py-8 text-center text-xs text-slate-400">No sections match “{sectionFilter}”.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Notifications */}
      {actionSuccess && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" /><span>{actionSuccess}</span></div>
          <button onClick={() => setActionSuccess(null)} aria-label="Dismiss"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}
      {actionError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" /><span>{actionError}</span></div>
          <button onClick={() => setActionError(null)} aria-label="Dismiss"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {/* Search, filters and categories */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
        <div className="flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              id="kb-search"
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={searchContent ? 'Search titles, act numbers, authorities and the full text…' : 'Search titles, act numbers and authorities…'}
              className="w-full pl-9 pr-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none">
              <input id="kb-search-content" type="checkbox" checked={searchContent} onChange={(e) => setSearchContent(e.target.checked)} className="rounded text-[#0f5132] focus:ring-[#0f5132]" />
              <span>Search inside documents</span>
            </label>
            <select id="kb-sort" value={sort} onChange={(e) => setSort(e.target.value)} className="px-2 py-2 text-xs border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-[#0f5132] focus:outline-none">
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="title">Title A–Z</option>
              <option value="effective_date">Effective date</option>
            </select>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`px-3 py-2 border rounded-lg text-xs flex items-center gap-1 ${activeFilterCount ? 'border-[#0f5132] text-[#0f5132] bg-emerald-50' : 'border-slate-300 text-slate-700 hover:bg-slate-50'}`}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Filters{activeFilterCount ? ` (${activeFilterCount})` : ''}</span>
            </button>
            <button onClick={refreshAll} className="px-3 py-2 border border-slate-300 rounded-lg text-xs text-slate-700 hover:bg-slate-50 flex items-center gap-1">
              <RefreshCw className="w-3.5 h-3.5" /><span>Refresh</span>
            </button>
          </div>
        </div>

        {showFilters && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-3 border-t border-slate-100">
            <label className="text-[11px] font-semibold text-slate-600 space-y-1">
              <span>Index status</span>
              <select id="kb-filter-index" value={indexStatus} onChange={(e) => setIndexStatus(e.target.value)} className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md bg-white">
                <option value="">Any</option>
                <option value="INDEXED">Indexed{stats ? ` (${stats.by_index_status.INDEXED || 0})` : ''}</option>
                <option value="PARTIALLY_INDEXED">Partially indexed{stats ? ` (${stats.by_index_status.PARTIALLY_INDEXED || 0})` : ''}</option>
                <option value="NEEDS_REVIEW">Needs review{stats ? ` (${stats.by_index_status.NEEDS_REVIEW || 0})` : ''}</option>
                <option value="FAILED">Failed{stats ? ` (${stats.by_index_status.FAILED || 0})` : ''}</option>
                <option value="STALLED">Stalled processing</option>
                <option value="NOT_INDEXED">Not indexed</option>
              </select>
            </label>
            <label className="text-[11px] font-semibold text-slate-600 space-y-1">
              <span>Source</span>
              <select id="kb-filter-source" value={sourceType} onChange={(e) => setSourceType(e.target.value)} className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md bg-white">
                <option value="">Any</option>
                {Object.entries(SOURCE_META).map(([k, v]) => <option key={k} value={k}>{v.label}{stats ? ` (${stats.by_source_type[k] || 0})` : ''}</option>)}
              </select>
            </label>
            <label className="text-[11px] font-semibold text-slate-600 space-y-1">
              <span>Legal status</span>
              <select id="kb-filter-legal" value={legalStatus} onChange={(e) => setLegalStatus(e.target.value)} className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md bg-white">
                <option value="">Any</option>
                {Object.entries(LEGAL_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="text-[11px] font-semibold text-slate-600 space-y-1">
              <span>Jurisdiction</span>
              <input id="kb-filter-jurisdiction" value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} placeholder="Central, Andhra Pradesh, Kurnool…" className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md" />
            </label>
            <label className="text-[11px] font-semibold text-slate-600 space-y-1">
              <span>Effective from</span>
              <input id="kb-filter-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md" />
            </label>
            <label className="text-[11px] font-semibold text-slate-600 space-y-1">
              <span>Effective to</span>
              <input id="kb-filter-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md" />
            </label>
            <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none self-end pb-2">
              <input id="kb-show-archived" type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} className="rounded text-[#0f5132] focus:ring-[#0f5132]" />
              <span>Include archived documents</span>
            </label>
            <button onClick={clearFilters} disabled={!activeFilterCount} className="self-end px-3 py-1.5 text-xs border border-slate-300 rounded-md text-slate-600 hover:bg-slate-50 disabled:opacity-40">
              Clear filters
            </button>
          </div>
        )}

        <div className="flex flex-wrap gap-1.5 pt-1 border-t border-slate-100">
          {Object.entries(CATEGORY_LABELS).map(([catKey, catMeta]) => {
            const isSelected = selectedCategory === catKey;
            const count = categoryCount(catKey);
            return (
              <button
                key={catKey}
                onClick={() => setSelectedCategory(catKey)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors inline-flex items-center gap-1.5 ${
                  isSelected ? 'bg-[#0f5132] text-white shadow-xs font-semibold' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                <span>{catMeta.label}</span>
                {count !== undefined && (
                  <span className={`text-[10px] px-1.5 rounded-full font-bold ${isSelected ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-600'}`}>{count}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Document Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between gap-2 flex-wrap">
          <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
            {total} document{total !== 1 ? 's' : ''}{search ? ` matching “${search}”` : ''}
          </span>
          <span className="text-[11px] text-slate-500">
            Your access: <span className="font-semibold text-slate-700">{user?.role === 'STATE' ? 'Statewide' : user?.role === 'DISTRICT' ? `${user?.district} district` : `${user?.station || ''}, ${user?.district || ''}`}</span>
          </span>
        </div>

        {loading ? (
          <div className="py-16 text-center">
            <RefreshCw className="w-8 h-8 text-[#0f5132] animate-spin mx-auto mb-2" />
            <p className="text-xs text-slate-500">Loading documents…</p>
          </div>
        ) : listError ? (
          <div className="py-16 text-center space-y-3">
            <AlertTriangle className="w-12 h-12 text-red-400 mx-auto" />
            <p className="text-sm font-semibold text-red-700">{listError}</p>
            <button onClick={refreshAll} className="px-4 py-2 bg-[#0f5132] text-white rounded-lg text-xs font-semibold hover:bg-[#0a3d26] inline-flex items-center gap-1.5">
              <RefreshCw className="w-3.5 h-3.5" /><span>Try again</span>
            </button>
          </div>
        ) : documents.length === 0 ? (
          <div className="py-16 text-center space-y-2 px-4">
            <BookOpen className="w-12 h-12 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-700">No documents found</p>
            <p className="text-xs text-slate-500">
              {search || selectedCategory !== 'ALL' || activeFilterCount ? 'Try a different search, category or filter.' : 'Upload laws, circulars, guides and reference material with the Upload Document button.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3">Document</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Scope</th>
                  <th className="px-4 py-3">Pages / Index</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {documents.map((doc) => {
                  const catKey = doc.doc_category === 'FIR' ? 'HISTORICAL_FIR' : doc.doc_category;
                  const catMeta = CATEGORY_LABELS[catKey] || { label: doc.doc_category, color: 'bg-slate-100 text-slate-700' };
                  const canRetry = !doc.is_archived && (RETRYABLE.has(doc.status) || RETRYABLE.has(doc.index_status));
                  return (
                    <tr key={doc.id} className={`hover:bg-slate-50 transition-colors align-top ${doc.is_archived ? 'bg-amber-50/40 text-slate-500' : ''}`}>
                      <td className="px-4 py-3 max-w-md">
                        <div className="flex items-start gap-2">
                          <FileText className={`w-4 h-4 flex-shrink-0 mt-0.5 ${doc.is_archived ? 'text-slate-400' : 'text-[#0f5132]'}`} />
                          <div className="min-w-0">
                            <button onClick={() => loadDetail(doc.id, 1)} className="font-semibold text-slate-900 hover:text-[#0f5132] hover:underline text-left">
                              {doc.document_title || doc.original_filename}
                            </button>
                            <div className="text-[11px] text-slate-500 mt-0.5">
                              {[doc.reference_number, doc.original_filename].filter(Boolean).join(' • ')}
                            </div>
                            {doc.match && (
                              <div className="mt-1.5 text-[11px] text-slate-600 bg-yellow-50 border border-yellow-200 rounded px-2 py-1">
                                <span className="font-semibold text-yellow-800">Page {doc.match.physical_page_number}:</span> “{doc.match.excerpt}”
                              </div>
                            )}
                            {doc.error_message && !doc.is_archived && (
                              <div className="mt-1 text-[11px] text-red-700">{doc.error_message}</div>
                            )}
                            {doc.replacement_reason && <div className="text-[10px] text-blue-600 italic mt-0.5">Replacement: {doc.replacement_reason}</div>}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-medium ${catMeta.color}`}>{catMeta.label}</span>
                        {doc.record_kind && <div className="text-[10px] text-slate-500 mt-1">Record: {doc.record_kind.toLowerCase()}</div>}
                      </td>
                      <td className="px-4 py-3 text-slate-600 space-y-1">
                        <SourceBadge sourceType={doc.source_type} />
                        <div className="text-[11px]">{doc.issuing_authority || doc.source_department || '—'}</div>
                        <div className="text-[10px] text-slate-400">
                          {[doc.legal_status ? LEGAL_STATUS_LABELS[doc.legal_status] || doc.legal_status : null,
                            doc.commencement_date ? `from ${doc.commencement_date}` : doc.version_date].filter(Boolean).join(' • ')}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-[11px] font-semibold text-slate-700">{doc.jurisdiction || doc.district || 'Statewide'}</span>
                        {doc.station && <div className="text-[10px] text-slate-500">{doc.station}</div>}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        <div>{doc.physical_page_count || 0} page{doc.physical_page_count !== 1 ? 's' : ''}</div>
                        <div className="text-[10px] text-slate-400" title="Searchable passages / passages with semantic embeddings">
                          {doc.indexed_chunk_count} passages • {doc.embedded_chunk_count} embedded
                        </div>
                      </td>
                      <td className="px-4 py-3"><StatusBadge doc={doc} /></td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button onClick={() => loadDetail(doc.id, 1)} title="Details, extracted text and indexing history" className="p-1 hover:bg-slate-100 text-slate-600 hover:text-[#0f5132] rounded">
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          <a href={viewUrl(doc.id)} target="_blank" rel="noopener noreferrer" title="Open the original file" className="p-1 hover:bg-slate-100 text-slate-600 hover:text-blue-600 rounded">
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                          {canRetry && (
                            <button onClick={() => handleRetry(doc.id, 'full')} title="Retry text extraction and indexing" className="p-1 hover:bg-blue-50 text-blue-600 rounded flex items-center gap-0.5 text-[11px] font-semibold">
                              <RotateCcw className="w-3.5 h-3.5" /><span>Retry</span>
                            </button>
                          )}
                          {!doc.is_archived && (
                            <>
                              <button onClick={() => { setSelectedDocForAction(doc); setShowReplaceModal(true); }} title="Replace with a corrected file" className="p-1 hover:bg-slate-100 text-slate-600 hover:text-amber-600 rounded">
                                <Upload className="w-3.5 h-3.5" />
                              </button>
                              <button onClick={() => { setSelectedDocForAction(doc); setShowDeleteModal(true); }} title="Archive" className="p-1 hover:bg-red-50 text-slate-400 hover:text-red-600 rounded">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </>
                          )}
                          {doc.is_archived && (
                            <button onClick={() => handleRestore(doc)} title="Restore" className="p-1 hover:bg-emerald-50 text-emerald-600 hover:text-emerald-800 rounded flex items-center gap-1 text-[11px] font-semibold">
                              <RotateCcw className="w-3.5 h-3.5" /><span>Restore</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {total > PAGE_SIZE && (
          <div className="px-5 py-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
            <span>Showing {page * PAGE_SIZE + 1}–{Math.min(total, (page + 1) * PAGE_SIZE)} of {total}</span>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0} className="px-2 py-1 border border-slate-300 rounded disabled:opacity-40 flex items-center gap-0.5">
                <ChevronLeft className="w-3.5 h-3.5" /> Previous
              </button>
              <span className="px-2">Page {page + 1} of {totalPages}</span>
              <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page + 1 >= totalPages} className="px-2 py-1 border border-slate-300 rounded disabled:opacity-40 flex items-center gap-0.5">
                Next <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-2xl w-full max-h-[92vh] flex flex-col overflow-hidden">
            <div className="bg-[#0f5132] text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2"><Upload className="w-5 h-5 text-emerald-300" /><h3 className="font-bold text-sm">Upload Knowledge Base Document</h3></div>
              <button onClick={() => setShowUploadModal(false)} className="text-white/80 hover:text-white" aria-label="Close"><X className="w-4 h-4" /></button>
            </div>

            <form onSubmit={handleUploadSubmit} className="p-5 space-y-4 overflow-y-auto">
              <div>
                <label htmlFor="kb-upload-file" className="block text-xs font-bold text-slate-700 mb-1">File (PDF, DOCX, TXT, JPG, PNG, WEBP · up to 50 MB)</label>
                <input
                  id="kb-upload-file"
                  type="file"
                  accept=".pdf,.docx,.txt,.md,.jpg,.jpeg,.png,.webp"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) { setUploadFile(f); if (!uploadTitle) setUploadTitle(f.name.replace(/\.[^/.]+$/, '')); }
                  }}
                  required
                  className="w-full text-xs text-slate-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-emerald-50 file:text-[#0f5132] hover:file:bg-emerald-100 cursor-pointer"
                />
              </div>

              <div>
                <label htmlFor="kb-upload-title" className="block text-xs font-bold text-slate-700 mb-1">Title</label>
                <input id="kb-upload-title" type="text" value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} required placeholder="e.g. Commissioner's Circular on seizure registers"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0f5132] focus:outline-none" />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="kb-upload-category" className="block text-xs font-bold text-slate-700 mb-1">Category</label>
                  <select id="kb-upload-category" value={uploadCategory} onChange={(e) => setUploadCategory(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white">
                    {canAddStatewide && <option value="LEGAL_ACT">Official Laws & Sections</option>}
                    {canAddStatewide && <option value="CIRCULAR">Circulars & Orders</option>}
                    <option value="SEIZURE_REPORT">Seizure Reports & Formats</option>
                    {canAddStatewide && <option value="INVESTIGATION_GUIDE">Investigation Guides & SOPs</option>}
                    {canAddStatewide && <option value="REFERENCE">Reference Materials</option>}
                    <option value="HISTORICAL_FIR">Historical FIR Records</option>
                    <option value="EVIDENCE">Approved Evidence</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="kb-upload-source-type" className="block text-xs font-bold text-slate-700 mb-1">Source</label>
                  <select id="kb-upload-source-type" value={uploadSourceType} onChange={(e) => setUploadSourceType(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white">
                    {isState && <option value="OFFICIAL">Official government source</option>}
                    <option value="SECONDARY">Secondary / explanatory material</option>
                    <option value="SYNTHETIC">Synthetic or demonstration data</option>
                    <option value="UNVERIFIED">Unverified</option>
                  </select>
                </div>
              </div>

              {(uploadCategory === 'HISTORICAL_FIR' || uploadCategory === 'EVIDENCE' || uploadCategory === 'SEIZURE_REPORT') && (
                <div>
                  <label htmlFor="kb-upload-record-kind" className="block text-xs font-bold text-slate-700 mb-1">Record type</label>
                  <select id="kb-upload-record-kind" value={uploadRecordKind} onChange={(e) => setUploadRecordKind(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white">
                    <option value="">Not specified</option>
                    <option value="ACTUAL">Actual record</option>
                    <option value="REDACTED">Redacted record</option>
                    <option value="SYNTHETIC">Synthetic / sample record</option>
                  </select>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="kb-upload-authority" className="block text-xs font-bold text-slate-700 mb-1">Issuing authority</label>
                  <input id="kb-upload-authority" value={uploadAuthority} onChange={(e) => setUploadAuthority(e.target.value)} placeholder="e.g. Commissioner of Prohibition & Excise" className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg" />
                </div>
                <div>
                  <label htmlFor="kb-upload-reference" className="block text-xs font-bold text-slate-700 mb-1">Act / order / circular number</label>
                  <input id="kb-upload-reference" value={uploadReference} onChange={(e) => setUploadReference(e.target.value)} placeholder="e.g. G.O.Ms.No. 123 or Act No. 17 of 1968" className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg" />
                </div>
                <div>
                  <label htmlFor="kb-upload-jurisdiction" className="block text-xs font-bold text-slate-700 mb-1">Jurisdiction</label>
                  <input id="kb-upload-jurisdiction" value={uploadJurisdiction} onChange={(e) => setUploadJurisdiction(e.target.value)} placeholder="Central, Andhra Pradesh, or a district" className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg" />
                </div>
                <div>
                  <label htmlFor="kb-upload-legal-status" className="block text-xs font-bold text-slate-700 mb-1">Legal status</label>
                  <select id="kb-upload-legal-status" value={uploadLegalStatus} onChange={(e) => setUploadLegalStatus(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white">
                    <option value="">Not applicable</option>
                    {Object.entries(LEGAL_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="kb-upload-publication" className="block text-xs font-bold text-slate-700 mb-1">Publication / issue date</label>
                  <input id="kb-upload-publication" type="date" value={uploadPublication} onChange={(e) => setUploadPublication(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg" />
                </div>
                <div>
                  <label htmlFor="kb-upload-commencement" className="block text-xs font-bold text-slate-700 mb-1">Effective / commencement date</label>
                  <input id="kb-upload-commencement" type="date" value={uploadCommencement} onChange={(e) => setUploadCommencement(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg" />
                </div>
              </div>

              <div>
                <label htmlFor="kb-upload-url" className="block text-xs font-bold text-slate-700 mb-1">
                  Official source URL {uploadSourceType === 'OFFICIAL' && <span className="text-red-600">(required)</span>}
                </label>
                <input id="kb-upload-url" type="url" value={uploadSourceUrl} onChange={(e) => setUploadSourceUrl(e.target.value)} placeholder="https://… (government portal where this document is published)" className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg" />
              </div>

              {!canAddStatewide && (
                <p className="text-[11px] text-slate-500 flex items-start gap-1.5"><Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />Station uploads are filed under your station. Laws, circulars, guides and reference material are added by district or state officers.</p>
              )}

              {uploadError && (
                <div className="p-2.5 bg-red-50 border border-red-200 rounded text-xs text-red-800">
                  {uploadError}
                  {duplicateOf && (
                    <button type="button" onClick={() => { setShowUploadModal(false); loadDetail(duplicateOf.id, 1); }} className="ml-1 underline font-semibold">
                      Open “{duplicateOf.title}”
                    </button>
                  )}
                </div>
              )}

              {uploadLoading && (
                <div className="space-y-1">
                  <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className="h-full bg-[#0f5132] transition-all" style={{ width: `${uploadProgress}%` }} /></div>
                  <p className="text-[11px] text-slate-500">{uploadProgress < 100 ? `Uploading… ${uploadProgress}%` : 'Upload complete, registering the document…'}</p>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button type="button" onClick={() => setShowUploadModal(false)} className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50">Cancel</button>
                <button type="submit" disabled={uploadLoading} className="px-4 py-2 bg-[#0f5132] text-white rounded-lg text-xs font-semibold hover:bg-[#0a3d26] disabled:opacity-50 flex items-center gap-1.5">
                  {uploadLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{uploadLoading ? 'Uploading…' : 'Upload'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Replace Modal */}
      {showReplaceModal && selectedDocForAction && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-lg w-full overflow-hidden">
            <div className="bg-amber-700 text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2"><RefreshCw className="w-5 h-5 text-amber-200" /><h3 className="font-bold text-sm">Replace Document</h3></div>
              <button onClick={() => setShowReplaceModal(false)} className="text-white/80 hover:text-white" aria-label="Close"><X className="w-4 h-4" /></button>
            </div>
            <form onSubmit={handleReplaceSubmit} className="p-5 space-y-4">
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs space-y-1">
                <p className="font-bold text-amber-900">Current document:</p>
                <p className="text-amber-800">{selectedDocForAction.document_title || selectedDocForAction.original_filename}</p>
                <p className="text-[10px] text-amber-700 font-mono break-all">SHA-256: {selectedDocForAction.file_hash}</p>
                <p className="text-[11px] text-amber-900 pt-1">The current version is archived with its history, and assistant answers based on it are refreshed.</p>
              </div>
              <div>
                <label htmlFor="kb-replace-file" className="block text-xs font-bold text-slate-700 mb-1">Replacement file</label>
                <input id="kb-replace-file" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={(e) => setReplaceFile(e.target.files?.[0] || null)} required
                  className="w-full text-xs text-slate-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-amber-50 file:text-amber-800 hover:file:bg-amber-100 cursor-pointer" />
              </div>
              <div>
                <label htmlFor="kb-replace-reason" className="block text-xs font-bold text-slate-700 mb-1">Reason for replacement (recorded in the audit trail)</label>
                <textarea id="kb-replace-reason" value={replaceReason} onChange={(e) => setReplaceReason(e.target.value)} required rows={3}
                  placeholder="e.g. Page 3 of the earlier scan was illegible; corrected notification uploaded."
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-amber-600 focus:outline-none" />
              </div>
              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button type="button" onClick={() => setShowReplaceModal(false)} className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50">Cancel</button>
                <button type="submit" disabled={replaceLoading} className="px-4 py-2 bg-amber-700 text-white rounded-lg text-xs font-semibold hover:bg-amber-800 disabled:opacity-50 flex items-center gap-1.5">
                  {replaceLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}<span>{replaceLoading ? 'Replacing…' : 'Replace document'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Archive Modal */}
      {showDeleteModal && selectedDocForAction && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="bg-red-700 text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-red-200" /><h3 className="font-bold text-sm">Archive Document</h3></div>
              <button onClick={() => setShowDeleteModal(false)} className="text-white/80 hover:text-white" aria-label="Close"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 leading-relaxed">
                <strong>{selectedDocForAction.document_title || selectedDocForAction.original_filename}</strong> will be removed from search and from the assistant. The file and its audit history are kept, and it can be restored later.
              </div>
              <div>
                <label htmlFor="kb-archive-reason" className="block text-xs font-bold text-slate-700 mb-1">Reason (required)</label>
                <input id="kb-archive-reason" type="text" value={actionReason} onChange={(e) => setActionReason(e.target.value)} placeholder="e.g. Superseded by the 2026 amendment"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-red-600 focus:outline-none" />
              </div>
              <div>
                <label htmlFor="kb-archive-confirm" className="block text-xs font-bold text-slate-700 mb-1">Type <span className="font-mono text-red-600">ARCHIVE</span> to confirm</label>
                <input id="kb-archive-confirm" type="text" value={deleteConfirmText} onChange={(e) => setDeleteConfirmText(e.target.value)} placeholder="ARCHIVE"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-red-600 focus:outline-none font-mono" />
              </div>
              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button type="button" onClick={() => setShowDeleteModal(false)} className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50">Cancel</button>
                <button type="button" onClick={handleArchiveConfirm} disabled={deleteConfirmText !== 'ARCHIVE' || !actionReason.trim()} className="px-4 py-2 bg-red-700 text-white rounded-lg text-xs font-semibold hover:bg-red-800 disabled:opacity-40">Archive</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Document Detail Panel */}
      {(detail || detailLoading || detailError) && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex justify-end">
          <div className="bg-white w-full max-w-3xl h-full flex flex-col shadow-2xl">
            <div className="bg-[#0f5132] text-white px-5 py-4 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-bold text-sm leading-snug">{detail?.document_title || 'Loading document…'}</h3>
                {detail && (
                  <p className="text-[11px] text-emerald-200 mt-0.5">
                    {CATEGORY_LABELS[detail.doc_category === 'FIR' ? 'HISTORICAL_FIR' : detail.doc_category]?.label || detail.doc_category} • {detail.pages_total} pages • {detail.original_filename}
                  </p>
                )}
              </div>
              <button onClick={closeDetail} className="text-white/80 hover:text-white flex-shrink-0" aria-label="Close details"><X className="w-5 h-5" /></button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {detailError && <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-800">{detailError}</div>}
              {detailLoading && !detail && (
                <div className="py-16 text-center"><RefreshCw className="w-6 h-6 text-[#0f5132] animate-spin mx-auto mb-2" /><p className="text-xs text-slate-500">Loading…</p></div>
              )}
              {detail && (
                <>
                  {/* Index state */}
                  <section className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[
                      { label: 'Status', value: <StatusBadge doc={detail} /> },
                      { label: 'Pages with text', value: `${detail.pages_with_text} / ${detail.pages_total}` },
                      { label: 'Searchable passages', value: detail.chunk_count },
                      { label: 'Semantic embeddings', value: detail.embedded_chunk_count ? `${detail.embedded_chunk_count}${detail.embedding_model ? ` (${detail.embedding_model})` : ''}` : 'None (keyword search only)' },
                    ].map((c) => (
                      <div key={c.label} className="border border-slate-200 rounded-lg p-2.5">
                        <div className="text-[10px] uppercase tracking-wide text-slate-500 font-bold">{c.label}</div>
                        <div className="text-xs font-semibold text-slate-800 mt-1">{c.value}</div>
                      </div>
                    ))}
                  </section>

                  {detail.error_message && <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-800">{detail.error_message}</div>}

                  {detail.can_manage && !detail.is_archived && (RETRYABLE.has(detail.status) || RETRYABLE.has(detail.index_status) || detail.index_status === 'INDEXED') && (
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => handleRetry(detail.id, 'full')} disabled={detail.status === 'PROCESSING'} className="px-3 py-1.5 text-xs font-semibold border border-blue-300 text-blue-700 rounded-md hover:bg-blue-50 disabled:opacity-40 flex items-center gap-1">
                        <RotateCcw className="w-3.5 h-3.5" /> Re-extract from original file
                      </button>
                      <button onClick={() => handleRetry(detail.id, 'reindex')} disabled={detail.status === 'PROCESSING' || detail.pages_with_text === 0} className="px-3 py-1.5 text-xs font-semibold border border-slate-300 text-slate-700 rounded-md hover:bg-slate-50 disabled:opacity-40 flex items-center gap-1">
                        <Layers className="w-3.5 h-3.5" /> Rebuild index from stored text
                      </button>
                    </div>
                  )}

                  {/* Provenance */}
                  <section className="border border-slate-200 rounded-lg">
                    <h4 className="px-3 py-2 text-xs font-bold text-slate-700 border-b border-slate-200 bg-slate-50 flex items-center gap-2">Source & provenance <SourceBadge sourceType={detail.source_type} /></h4>
                    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 p-3 text-xs">
                      {[
                        ['Issuing authority', detail.issuing_authority],
                        ['Reference number', detail.reference_number],
                        ['Jurisdiction', detail.jurisdiction],
                        ['Legal status', detail.legal_status ? LEGAL_STATUS_LABELS[detail.legal_status] || detail.legal_status : null],
                        ['Published', detail.publication_date || detail.version_date],
                        ['In force from', detail.commencement_date],
                        ['Language', detail.language],
                        ['Last verified', detail.last_verified_at ? new Date(detail.last_verified_at).toLocaleDateString() : null],
                        ['Record type', detail.record_kind],
                        ['Legal provisions parsed', detail.legal_provisions || null],
                      ].filter(([, v]) => v !== null && v !== undefined && v !== '').map(([k, v]) => (
                        <div key={k as string}><dt className="text-[10px] uppercase tracking-wide text-slate-500 font-bold">{k}</dt><dd className="text-slate-800">{v}</dd></div>
                      ))}
                    </dl>
                    {detail.verification_note && <p className="px-3 pb-3 text-[11px] text-slate-600">{detail.verification_note}</p>}
                    <div className="px-3 pb-3 flex flex-wrap gap-3 text-xs">
                      {detail.source_url && <a href={detail.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline flex items-center gap-1"><ExternalLink className="w-3 h-3" /> Official source</a>}
                      <a href={viewUrl(detail.id)} target="_blank" rel="noopener noreferrer" className="text-[#0f5132] hover:underline flex items-center gap-1"><Eye className="w-3 h-3" /> Open original file</a>
                      <span className="text-[10px] text-slate-500 font-mono break-all">SHA-256 {detail.file_hash}</span>
                    </div>
                  </section>

                  {detail.sections.length > 0 && (
                    <section>
                      <h4 className="text-xs font-bold text-slate-700 mb-1.5">Detected sections ({detail.sections.length})</h4>
                      <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto">
                        {detail.sections.map((s) => <span key={s} className="text-[10px] px-1.5 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded">{s}</span>)}
                      </div>
                    </section>
                  )}

                  {/* Ingestion history */}
                  <section>
                    <h4 className="text-xs font-bold text-slate-700 mb-1.5">Ingestion history</h4>
                    {detail.ingestion_jobs.length === 0 ? (
                      <p className="text-[11px] text-slate-500">No ingestion runs recorded (document added before ingestion tracking).</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {detail.ingestion_jobs.map((j) => (
                          <li key={j.id} className="border border-slate-200 rounded p-2 text-[11px]">
                            <div className="flex items-center justify-between gap-2 flex-wrap">
                              <span className="font-semibold text-slate-800">{j.trigger || 'RUN'} · {INDEX_META[j.status]?.label || j.status}</span>
                              <span className="text-slate-500">{j.started_at ? new Date(j.started_at + 'Z').toLocaleString() : ''}</span>
                            </div>
                            <div className="text-slate-600 mt-0.5">{j.pages_with_text}/{j.pages_total} pages with text • {j.chunks_written} passages • {j.chunks_embedded} embedded</div>
                            {j.error_message && <div className="text-red-700 mt-0.5">{j.error_message}</div>}
                            {j.warnings.length > 0 && (
                              <details className="mt-0.5"><summary className="cursor-pointer text-amber-700">{j.warnings.length} warning{j.warnings.length > 1 ? 's' : ''}</summary>
                                <ul className="list-disc pl-4 text-amber-800">{j.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                              </details>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  {/* Extracted text */}
                  <section>
                    <div className="flex items-center justify-between mb-1.5">
                      <h4 className="text-xs font-bold text-slate-700">Extracted text</h4>
                      {detail.pages_total > DETAIL_PAGE_SIZE && (
                        <div className="flex items-center gap-1 text-[11px]">
                          <button onClick={() => loadDetail(detail.id, Math.max(1, detail.page_from - DETAIL_PAGE_SIZE))} disabled={detail.page_from <= 1 || detailLoading} className="px-2 py-0.5 border border-slate-300 rounded disabled:opacity-40">Previous</button>
                          <span>Pages {detail.page_from}–{Math.min(detail.pages_total, detail.page_from + DETAIL_PAGE_SIZE - 1)} of {detail.pages_total}</span>
                          <button onClick={() => loadDetail(detail.id, detail.page_from + DETAIL_PAGE_SIZE)} disabled={detail.page_from + DETAIL_PAGE_SIZE > detail.pages_total || detailLoading} className="px-2 py-0.5 border border-slate-300 rounded disabled:opacity-40">Next</button>
                        </div>
                      )}
                    </div>
                    {detail.pages.length === 0 ? (
                      <p className="text-[11px] text-slate-500">No extracted text is stored for this document.</p>
                    ) : (
                      <div className="space-y-2">
                        {detail.pages.map((p) => (
                          <div key={p.physical_page_number} className="border border-slate-200 rounded-lg bg-slate-50">
                            <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 text-[11px] font-semibold text-slate-700">
                              <span>Page {p.physical_page_number}</span>
                              <span className="flex items-center gap-2">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${p.is_unreadable ? 'bg-orange-100 text-orange-800' : p.ocr_applied ? 'bg-purple-100 text-purple-800' : 'bg-emerald-100 text-emerald-800'}`}>
                                  {p.is_unreadable ? 'No readable text' : p.ocr_applied ? 'OCR' : 'Digital text'}
                                </span>
                                <a href={viewUrl(detail.id, p.physical_page_number)} target="_blank" rel="noopener noreferrer" className="text-[#0f5132] hover:underline">Open page</a>
                              </span>
                            </div>
                            <pre className="text-[11px] text-slate-700 whitespace-pre-wrap font-mono leading-relaxed p-3 max-h-56 overflow-y-auto">{p.text || '—'}</pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default KnowledgeBase;

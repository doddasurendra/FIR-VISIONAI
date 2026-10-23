import React, { useState, useEffect, useCallback } from 'react';
import {
  BookOpen, Plus, Search, Filter, FileText, Download,
  RefreshCw, Trash2, RotateCcw, AlertTriangle, CheckCircle2,
  ExternalLink, Eye, X, Upload, Shield, ShieldCheck,
  Building, Calendar, Clock, Layers, Sparkles
} from 'lucide-react';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';

interface KBDocument {
  id: string;
  case_id: string | null;
  original_filename: string;
  document_title: string;
  doc_category: string;
  source_department: string;
  version_date: string | null;
  district: string;
  station: string | null;
  physical_page_count: number;
  mime_type: string;
  file_hash: string;
  is_verified_official: boolean;
  is_archived: boolean;
  archive_reason: string | null;
  archived_at: string | null;
  replaced_by_id: string | null;
  replaces_id: string | null;
  replacement_reason: string | null;
  status: string;
  created_at: string;
  created_by: string;
}

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

export const KnowledgeBase: React.FC = () => {
  const { user } = useAuth();

  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [showArchived, setShowArchived] = useState(false);
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({});

  const fetchCategoryCounts = useCallback(async () => {
    try {
      const res = await api.get('/documents/', { params: { include_archived: false, limit: 200 } });
      const docs: KBDocument[] = res.data?.documents || [];
      const counts: Record<string, number> = { ALL: docs.length };
      docs.forEach((d) => {
        const cat = d.doc_category === 'FIR' ? 'HISTORICAL_FIR' : d.doc_category;
        counts[cat] = (counts[cat] || 0) + 1;
      });
      setCategoryCounts(counts);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchCategoryCounts();
  }, [fetchCategoryCounts]);

  // Modals
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showReplaceModal, setShowReplaceModal] = useState(false);
  const [selectedDocForAction, setSelectedDocForAction] = useState<KBDocument | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [actionReason, setActionReason] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadCategory, setUploadCategory] = useState('LEGAL_ACT');
  const [uploadSource, setUploadSource] = useState('Andhra Pradesh Prohibition & Excise Department');
  const [uploadVersionDate, setUploadVersionDate] = useState('');
  const [uploadIsOfficial, setUploadIsOfficial] = useState(true);
  const [uploadLoading, setUploadLoading] = useState(false);

  // Replace state
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [replaceReason, setReplaceReason] = useState('');
  const [replaceLoading, setReplaceLoading] = useState(false);

  // Preview Modal
  const [previewDoc, setPreviewDoc] = useState<KBDocument | null>(null);
  const [previewPages, setPreviewPages] = useState<any[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setActionError(null);
    try {
      const params: Record<string, any> = {
        include_archived: showArchived,
        limit: 100
      };
      if (selectedCategory !== 'ALL') {
        params.category = selectedCategory;
      }
      if (search.trim()) {
        params.search = search.trim();
      }
      const res = await api.get('/documents/', { params });
      setDocuments(res.data?.documents || []);
      setTotal(res.data?.total || 0);
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to fetch Knowledge Base documents.');
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, search, showArchived]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Upload handler
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !uploadTitle.trim()) {
      setActionError('Please provide a file and a document title.');
      return;
    }
    setUploadLoading(true);
    setActionError(null);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('document_title', uploadTitle);
      formData.append('category', uploadCategory);
      formData.append('source_department', uploadSource);
      if (uploadVersionDate) formData.append('version_date', uploadVersionDate);
      formData.append('is_verified_official', String(uploadIsOfficial));

      await api.post('/documents/knowledge-base/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setActionSuccess(`Document "${uploadTitle}" uploaded and indexed into Knowledge Base.`);
      setShowUploadModal(false);
      setUploadFile(null);
      setUploadTitle('');
      setUploadVersionDate('');
      fetchDocuments();
      fetchCategoryCounts();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Upload failed. Ensure file is a valid PDF or image.');
    } finally {
      setUploadLoading(false);
    }
  };

  // Replace handler
  const handleReplaceSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDocForAction || !replaceFile || !replaceReason.trim()) {
      setActionError('Please select the replacement file and specify the replacement reason.');
      return;
    }
    setReplaceLoading(true);
    setActionError(null);
    try {
      const formData = new FormData();
      formData.append('file', replaceFile);
      formData.append('reason', replaceReason.trim());

      await api.post(`/documents/${selectedDocForAction.id}/replace`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setActionSuccess(`Document successfully replaced with "${replaceFile.name}".`);
      setShowReplaceModal(false);
      setSelectedDocForAction(null);
      setReplaceFile(null);
      setReplaceReason('');
      fetchDocuments();
      fetchCategoryCounts();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Document replacement failed.');
    } finally {
      setReplaceLoading(false);
    }
  };

  // Archive / Soft-delete handler
  const handleArchiveConfirm = async () => {
    if (!selectedDocForAction) return;
    if (deleteConfirmText !== 'ARCHIVE') {
      setActionError('Please type ARCHIVE to confirm this destructive action.');
      return;
    }
    if (!actionReason.trim()) {
      setActionError('A mandatory departmental reason is required to archive this record.');
      return;
    }
    try {
      await api.delete(`/documents/${selectedDocForAction.id}`, {
        params: { reason: actionReason.trim() }
      });
      setActionSuccess(`Document "${selectedDocForAction.original_filename}" archived.`);
      setShowDeleteModal(false);
      setSelectedDocForAction(null);
      setActionReason('');
      setDeleteConfirmText('');
      fetchDocuments();
      fetchCategoryCounts();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to archive document.');
    }
  };

  // Restore handler
  const handleRestore = async (doc: KBDocument) => {
    try {
      await api.post(`/documents/${doc.id}/restore`);
      setActionSuccess(`Document "${doc.original_filename}" restored to active status.`);
      fetchDocuments();
      fetchCategoryCounts();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to restore document.');
    }
  };

  // Preview handler
  const handleOpenPreview = async (doc: KBDocument) => {
    setPreviewDoc(doc);
    setPreviewLoading(true);
    try {
      const res = await api.get(`/documents/${doc.id}/pages`);
      setPreviewPages(res.data?.pages || []);
    } catch {
      setPreviewPages([]);
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-[#0f5132]/10 rounded-xl text-[#0f5132]">
            <BookOpen className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">Knowledge Base & Legal Corpus</h1>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full border border-emerald-300">
                Official AP Prohibition & Excise
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Authorized legal acts, departmental circulars, standard seizure formats, investigation guides, and verified reference records.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowUploadModal(true)}
            className="flex items-center gap-1.5 px-4 py-2 bg-[#0f5132] text-white rounded-lg text-xs font-semibold hover:bg-[#0a3d26] transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>Upload Document</span>
          </button>
        </div>
      </div>

      {/* Notifications */}
      {actionSuccess && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)}><X className="w-3.5 h-3.5" /></button>
        </div>
      )}
      {actionError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <span>{actionError}</span>
          </div>
          <button onClick={() => setActionError(null)}><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
        <div className="flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by document title, filename, act or section..."
              className="w-full pl-9 pr-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                className="rounded text-[#0f5132] focus:ring-[#0f5132]"
              />
              <span>Show Archived ({showArchived ? 'Active + Archived' : 'Active Only'})</span>
            </label>
            <button
              onClick={fetchDocuments}
              className="px-3 py-2 border border-slate-300 rounded-lg text-xs text-slate-700 hover:bg-slate-50 flex items-center gap-1"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Category Pills */}
        <div className="flex flex-wrap gap-1.5 pt-1 border-t border-slate-100">
          {Object.entries(CATEGORY_LABELS).map(([catKey, catMeta]) => {
            const isSelected = selectedCategory === catKey;
            const count = categoryCounts[catKey];
            return (
              <button
                key={catKey}
                onClick={() => setSelectedCategory(catKey)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors inline-flex items-center gap-1.5 ${
                  isSelected
                    ? 'bg-[#0f5132] text-white shadow-xs font-semibold'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                <span>{catMeta.label}</span>
                {count !== undefined && (
                  <span
                    className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                      isSelected ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-600'
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Document Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between">
          <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
            {total} Authorized Knowledge Base Record{total !== 1 ? 's' : ''}
          </span>
          <span className="text-[11px] text-slate-500">
            Jurisdiction: <span className="font-semibold text-slate-700">{user?.district || 'Statewide'}</span>
          </span>
        </div>

        {loading ? (
          <div className="py-16 text-center">
            <RefreshCw className="w-8 h-8 text-[#0f5132] animate-spin mx-auto mb-2" />
            <p className="text-xs text-slate-500">Loading authorized knowledge documents...</p>
          </div>
        ) : actionError ? (
          <div className="py-16 text-center space-y-3">
            <AlertTriangle className="w-12 h-12 text-red-400 mx-auto" />
            <p className="text-sm font-semibold text-red-700">{actionError}</p>
            <p className="text-xs text-slate-500">Could not retrieve Knowledge Base records. Please check connectivity or refresh your session.</p>
            <button
              onClick={fetchDocuments}
              className="px-4 py-2 bg-[#0f5132] text-white rounded-lg text-xs font-semibold hover:bg-[#0a3d26] inline-flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry</span>
            </button>
          </div>
        ) : documents.length === 0 ? (
          <div className="py-16 text-center space-y-2">
            <BookOpen className="w-12 h-12 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-700">No Knowledge Base documents found</p>
            <p className="text-xs text-slate-500">
              {search || selectedCategory !== 'ALL'
                ? 'Try adjusting your search criteria or category filter.'
                : 'Upload official laws, guidelines, and reference materials using the button above.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3">Document Title & Filename</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">Source & Date</th>
                  <th className="px-4 py-3">Scope</th>
                  <th className="px-4 py-3">Pages / Size</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {documents.map((doc) => {
                  const catMeta = CATEGORY_LABELS[doc.doc_category] || { label: doc.doc_category, color: 'bg-slate-100 text-slate-700' };
                  return (
                    <tr
                      key={doc.id}
                      className={`hover:bg-slate-50 transition-colors ${
                        doc.is_archived ? 'bg-amber-50/40 text-slate-500' : ''
                      }`}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-start gap-2">
                          <FileText className={`w-4 h-4 flex-shrink-0 mt-0.5 ${doc.is_archived ? 'text-slate-400' : 'text-[#0f5132]'}`} />
                          <div>
                            <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                              <span>{doc.document_title || doc.original_filename}</span>
                              {doc.is_verified_official && (
                                <span title="Verified Official AP Document" className="inline-flex">
                                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                                </span>
                              )}
                              {doc.is_archived && (
                                <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.2 rounded font-bold">
                                  ARCHIVED
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] text-slate-500 font-mono mt-0.5">{doc.original_filename}</div>
                            {doc.replacement_reason && (
                              <div className="text-[10px] text-blue-600 italic mt-0.5">
                                Replacement: {doc.replacement_reason}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>

                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-medium ${catMeta.color}`}>
                          {catMeta.label}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-slate-600">
                        <div>{doc.source_department || 'AP Excise Dept'}</div>
                        {doc.version_date && (
                          <div className="text-[10px] text-slate-400">{doc.version_date}</div>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        <span className="text-[11px] font-semibold text-slate-700">
                          {doc.district || 'Statewide'}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-slate-600">
                        <div>{doc.physical_page_count} page{doc.physical_page_count !== 1 ? 's' : ''}</div>
                        <div className="text-[10px] text-slate-400 font-mono">{doc.file_hash.substring(0, 8)}...</div>
                      </td>

                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          doc.is_archived ? 'bg-amber-100 text-amber-800' :
                          doc.status === 'COMPLETED' ? 'bg-emerald-100 text-emerald-800' :
                          doc.status === 'FAILED' ? 'bg-red-100 text-red-800' :
                          'bg-blue-100 text-blue-800'
                        }`}>
                          {doc.is_archived ? 'Archived' : doc.status}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {/* Preview Pages */}
                          <button
                            onClick={() => handleOpenPreview(doc)}
                            title="Preview Pages & OCR Text"
                            className="p-1 hover:bg-slate-100 text-slate-600 hover:text-[#0f5132] rounded"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>

                          {/* Download / Open in tab */}
                          <a
                            href={`/api/v1/documents/${doc.id}/view?token=${encodeURIComponent(localStorage.getItem('fir_sahayak_token') || '')}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="View / Download Original Document"
                            className="p-1 hover:bg-slate-100 text-slate-600 hover:text-blue-600 rounded"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>

                          {!doc.is_archived && (
                            <>
                              {/* Replace Document */}
                              <button
                                onClick={() => {
                                  setSelectedDocForAction(doc);
                                  setShowReplaceModal(true);
                                }}
                                title="Replace with Corrected Document"
                                className="p-1 hover:bg-slate-100 text-slate-600 hover:text-amber-600 rounded"
                              >
                                <RefreshCw className="w-3.5 h-3.5" />
                              </button>

                              {/* Archive */}
                              <button
                                onClick={() => {
                                  setSelectedDocForAction(doc);
                                  setShowDeleteModal(true);
                                }}
                                title="Archive / Soft-Delete"
                                className="p-1 hover:bg-red-50 text-slate-400 hover:text-red-600 rounded"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </>
                          )}

                          {doc.is_archived && (
                            <button
                              onClick={() => handleRestore(doc)}
                              title="Restore Document"
                              className="p-1 hover:bg-emerald-50 text-emerald-600 hover:text-emerald-800 rounded flex items-center gap-1 text-[11px] font-semibold"
                            >
                              <RotateCcw className="w-3.5 h-3.5" />
                              <span>Restore</span>
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
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-lg w-full overflow-hidden">
            <div className="bg-[#0f5132] text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Upload className="w-5 h-5 text-emerald-300" />
                <h3 className="font-bold text-sm">Upload Knowledge Base Document</h3>
              </div>
              <button onClick={() => setShowUploadModal(false)} className="text-white/80 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUploadSubmit} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Select File (PDF, JPG, PNG, WEBP)</label>
                <input
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,.webp"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      setUploadFile(f);
                      if (!uploadTitle) setUploadTitle(f.name.replace(/\.[^/.]+$/, ''));
                    }
                  }}
                  required
                  className="w-full text-xs text-slate-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-emerald-50 file:text-[#0f5132] hover:file:bg-emerald-100 cursor-pointer"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Official Document Title</label>
                <input
                  type="text"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  placeholder="e.g., Andhra Pradesh Excise Act 1968"
                  required
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Category</label>
                  <select
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0f5132] bg-white text-slate-900 focus:outline-none"
                  >
                    <option value="LEGAL_ACT">Official Laws & Sections</option>
                    <option value="CIRCULAR">Circulars & Orders</option>
                    <option value="SEIZURE_REPORT">Seizure Reports & Formats</option>
                    <option value="INVESTIGATION_GUIDE">Investigation Guides & SOPs</option>
                    <option value="REFERENCE">Reference Materials</option>
                    <option value="HISTORICAL_FIR">Historical FIR Archive</option>
                    <option value="EVIDENCE">Approved Evidence</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Version / Notification Date</label>
                  <input
                    type="date"
                    value={uploadVersionDate}
                    onChange={(e) => setUploadVersionDate(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Issuing Source Department</label>
                <input
                  type="text"
                  value={uploadSource}
                  onChange={(e) => setUploadSource(e.target.value)}
                  placeholder="Andhra Pradesh Prohibition & Excise Department"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="official-check"
                  checked={uploadIsOfficial}
                  onChange={(e) => setUploadIsOfficial(e.target.checked)}
                  className="rounded text-[#0f5132] focus:ring-[#0f5132]"
                />
                <label htmlFor="official-check" className="text-xs text-slate-700 font-medium cursor-pointer">
                  Mark as Verified Departmental Document (Authorizes official citations in AI RAG Assistant)
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploadLoading}
                  className="px-4 py-2 bg-[#0f5132] text-white rounded-lg text-xs font-semibold hover:bg-[#0a3d26] disabled:opacity-50 flex items-center gap-1.5"
                >
                  {uploadLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{uploadLoading ? 'Indexing Document...' : 'Upload & Index'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Replace Document Modal */}
      {showReplaceModal && selectedDocForAction && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-lg w-full overflow-hidden">
            <div className="bg-amber-700 text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <RefreshCw className="w-5 h-5 text-amber-200" />
                <h3 className="font-bold text-sm">Replace Document</h3>
              </div>
              <button onClick={() => setShowReplaceModal(false)} className="text-white/80 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleReplaceSubmit} className="p-5 space-y-4">
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs space-y-1">
                <p className="font-bold text-amber-900">Current Active Document:</p>
                <p className="text-amber-800">{selectedDocForAction.document_title || selectedDocForAction.original_filename}</p>
                <p className="text-[10px] text-amber-700 font-mono">Hash: {selectedDocForAction.file_hash}</p>
                <p className="text-[11px] text-amber-900 pt-1">
                  <strong>Notice:</strong> The existing document will be archived with full provenance and audit logs. All prior RAG query caches will be automatically invalidated.
                </p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Select Replacement Document</label>
                <input
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,.webp"
                  onChange={(e) => setReplaceFile(e.target.files?.[0] || null)}
                  required
                  className="w-full text-xs text-slate-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-amber-50 file:text-amber-800 hover:file:bg-amber-100 cursor-pointer"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Reason for Replacement (Mandatory Audit Requirement)</label>
                <textarea
                  value={replaceReason}
                  onChange={(e) => setReplaceReason(e.target.value)}
                  placeholder="e.g., Previous scan had illegible page 3; corrected official notification uploaded per Superintendent order."
                  required
                  rows={3}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-amber-600 focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowReplaceModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={replaceLoading}
                  className="px-4 py-2 bg-amber-700 text-white rounded-lg text-xs font-semibold hover:bg-amber-800 disabled:opacity-50 flex items-center gap-1.5"
                >
                  {replaceLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{replaceLoading ? 'Replacing & Re-indexing...' : 'Confirm Document Replacement'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Archive / Delete Modal */}
      {showDeleteModal && selectedDocForAction && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="bg-red-700 text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-200" />
                <h3 className="font-bold text-sm">Archive Document Confirmation</h3>
              </div>
              <button onClick={() => setShowDeleteModal(false)} className="text-white/80 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 leading-relaxed">
                <p className="font-bold mb-1">Destructive Archival Notice:</p>
                This action soft-deletes <strong>{selectedDocForAction.document_title || selectedDocForAction.original_filename}</strong>.
                It will be excluded from standard searches and AI FIR RAG Assistant retrieval. Physical file bytes and cryptographic audit history are permanently preserved.
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Archival Reason (Mandatory)</label>
                <input
                  type="text"
                  value={actionReason}
                  onChange={(e) => setActionReason(e.target.value)}
                  placeholder="e.g., Obsoleted by Act Amendment 2026"
                  required
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-red-600 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Type <span className="font-mono text-red-600">ARCHIVE</span> to confirm:
                </label>
                <input
                  type="text"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  placeholder="ARCHIVE"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-red-600 focus:outline-none font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowDeleteModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleArchiveConfirm}
                  disabled={deleteConfirmText !== 'ARCHIVE' || !actionReason.trim()}
                  className="px-4 py-2 bg-red-700 text-white rounded-lg text-xs font-semibold hover:bg-red-800 disabled:opacity-40"
                >
                  Archive Document
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Document Pages & Text Preview Modal */}
      {previewDoc && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-3xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            <div className="bg-[#0f5132] text-white px-5 py-4 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-sm">{previewDoc.document_title || previewDoc.original_filename}</h3>
                <p className="text-[11px] text-emerald-200">{previewDoc.doc_category} • {previewDoc.physical_page_count} Physical Pages</p>
              </div>
              <button onClick={() => setPreviewDoc(null)} className="text-white/80 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 overflow-y-auto space-y-4 flex-1">
              {previewLoading ? (
                <div className="py-12 text-center">
                  <RefreshCw className="w-6 h-6 text-[#0f5132] animate-spin mx-auto mb-2" />
                  <p className="text-xs text-slate-500">Loading extracted pages...</p>
                </div>
              ) : previewPages.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-500">
                  No extracted text found for this document.
                </div>
              ) : (
                previewPages.map((p) => (
                  <div key={p.id} className="border border-slate-200 rounded-lg p-3.5 bg-slate-50 space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-semibold text-slate-700 border-b border-slate-200 pb-1.5">
                      <span>Physical Page {p.physical_page_number}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${p.ocr_applied ? 'bg-purple-100 text-purple-800' : 'bg-emerald-100 text-emerald-800'}`}>
                        {p.ocr_applied ? 'OCR Processed' : 'Digital Text'}
                      </span>
                    </div>
                    <div className="text-xs text-slate-700 whitespace-pre-wrap font-mono leading-relaxed bg-white p-3 rounded border border-slate-100 max-h-48 overflow-y-auto">
                      {p.text_snippet || 'No text extracted on this page.'}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
              <span className="text-xs text-slate-500 font-mono">SHA-256: {previewDoc.file_hash}</span>
              <button
                onClick={() => setPreviewDoc(null)}
                className="px-4 py-1.5 bg-[#0f5132] text-white rounded-lg text-xs font-semibold hover:bg-[#0a3d26]"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default KnowledgeBase;

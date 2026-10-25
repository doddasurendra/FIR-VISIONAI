import React, { useState, useEffect } from 'react';
import { X, ChevronLeft, ChevronRight, FileText, CheckCircle2, AlertTriangle, ExternalLink, RefreshCw, ShieldAlert, ZoomIn, ZoomOut } from 'lucide-react';
import api from '../../api/client';

interface PDFViewerModalProps {
  documentId: string;
  initialPage?: number;
  onClose: () => void;
}

export const PDFViewerModal: React.FC<PDFViewerModalProps> = ({
  documentId,
  initialPage = 1,
  onClose,
}) => {
  const [currentPage, setCurrentPage] = useState<number>(initialPage);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [filename, setFilename] = useState<string>('Document.pdf');
  const [mimeType, setMimeType] = useState<string>('application/pdf');
  const [pagesData, setPagesData] = useState<any[]>([]);
  const [ingestionStatus, setIngestionStatus] = useState<string>('COMPLETED');
  const [loading, setLoading] = useState<boolean>(true);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fileMissing, setFileMissing] = useState<boolean>(false);
  const [imageError, setImageError] = useState<boolean>(false);
  const [zoom, setZoom] = useState<number>(1);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [reuploadFile, setReuploadFile] = useState<File | null>(null);
  const [reuploadState, setReuploadState] = useState<{ busy: boolean; message?: string; error?: string }>({ busy: false });

  const submitReupload = async () => {
    if (!reuploadFile) return;
    setReuploadState({ busy: true });
    try {
      const form = new FormData();
      form.append('file', reuploadFile);
      form.append('reason', 'Original file missing from storage; re-uploaded from the viewer');
      const res = await api.post(`/documents/${documentId}/replace`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const newId = res.data?.new_document_id;
      setReuploadState({
        busy: false,
        message: `File uploaded and processed as a replacement${newId ? ` (new record ${String(newId).slice(0, 8)})` : ''}. This record is now archived; open the new record from the case.`,
      });
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setReuploadState({
        busy: false,
        error: typeof detail === 'string' ? detail : detail?.message || 'Re-upload failed. Please try again.',
      });
    }
  };

  useEffect(() => {
    let activeBlobUrl: string | null = null;
    let isCancelled = false;

    const loadDocumentData = async () => {
      setLoading(true);
      setErrorMessage(null);
      setFileMissing(false);
      setImageError(false);
      try {
        // 1. Fetch metadata and pages info
        const metaRes = await api.get(`/documents/${documentId}/pages`);
        if (isCancelled) return;
        setFilename(metaRes.data.original_filename);
        setTotalPages(metaRes.data.physical_page_count || 1);
        setPagesData(metaRes.data.pages || []);
        if (metaRes.data.ingestion_status) {
          setIngestionStatus(metaRes.data.ingestion_status);
        }

        // 2. Authenticated binary fetch of PDF/Image bytes via Axios interceptor
        const viewRes = await api.get(`/documents/${documentId}/view`, {
          responseType: 'blob',
        });
        if (isCancelled) return;

        const returnedMime: string = String(viewRes.headers['content-type'] || 'application/pdf');
        setMimeType(returnedMime);

        const blob = new Blob([viewRes.data], { type: returnedMime });
        activeBlobUrl = URL.createObjectURL(blob);
        setPdfBlobUrl(activeBlobUrl);
      } catch (err: any) {
        if (isCancelled) return;
        console.error('Failed to load authenticated document:', err);
        const status = err.response?.status;
        // Blob requests return error bodies as Blobs; read the JSON detail out of them
        let detail: any = err.response?.data?.detail;
        if (err.response?.data instanceof Blob) {
          try {
            detail = JSON.parse(await err.response.data.text())?.detail;
          } catch {
            detail = undefined;
          }
        }
        const detailText = typeof detail === 'string' ? detail : detail?.message;
        if (status === 401) {
          setErrorMessage('Authentication session expired. Please log in again to view official records.');
        } else if (status === 403) {
          setErrorMessage('Access denied: You do not have departmental authorization to view evidence records from this jurisdiction.');
        } else if (status === 404 && detail?.code === 'ORIGINAL_FILE_MISSING') {
          setFileMissing(true);
          setErrorMessage(detailText);
        } else if (status === 404) {
          setErrorMessage(detailText || 'This document record was not found.');
        } else if (!err.response) {
          setErrorMessage('The server could not be reached. Check your connection and retry.');
        } else {
          setErrorMessage(detailText || 'Failed to securely load the evidence document record.');
        }
      } finally {
        if (!isCancelled) {
          setLoading(false);
        }
      }
    };

    loadDocumentData();

    return () => {
      isCancelled = true;
      if (activeBlobUrl) {
        URL.revokeObjectURL(activeBlobUrl);
      }
    };
  }, [documentId, reloadKey]);

  const activePageInfo = pagesData.find((p) => p.physical_page_number === currentPage);
  const token = localStorage.getItem('fir_sahayak_token') || localStorage.getItem('token') || '';
  const fallbackDirectUrl = `/api/v1/documents/${documentId}/view?token=${encodeURIComponent(token)}#page=${currentPage}`;
  const isImage = mimeType.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(filename);

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl h-[90vh] flex flex-col overflow-hidden border border-slate-300">
        {/* Header Bar */}
        <div className="bg-slate-900 text-white px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-1.5 bg-blue-600 rounded-md">
              <FileText className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-slate-100">{filename}</h3>
              <p className="text-xs text-slate-400">
                Official Evidence Record | {isImage ? 'Evidence Photograph' : `Physical Pages: ${totalPages}`}
              </p>
            </div>
          </div>

          {/* Page Controls */}
          <div className="flex items-center space-x-3">
            {isImage && pdfBlobUrl && !errorMessage && (
              <div className="flex items-center space-x-1 bg-slate-800 px-2 py-1 rounded-lg border border-slate-700 text-xs">
                <button
                  onClick={() => setZoom((z) => Math.max(0.25, +(z - 0.25).toFixed(2)))}
                  className="p-1 hover:bg-slate-700 rounded disabled:opacity-40"
                  disabled={zoom <= 0.25}
                  title="Zoom out"
                >
                  <ZoomOut className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setZoom(1)}
                  className="font-mono font-medium px-2 hover:bg-slate-700 rounded"
                  title="Fit to window"
                >
                  {Math.round(zoom * 100)}%
                </button>
                <button
                  onClick={() => setZoom((z) => Math.min(4, +(z + 0.25).toFixed(2)))}
                  className="p-1 hover:bg-slate-700 rounded disabled:opacity-40"
                  disabled={zoom >= 4}
                  title="Zoom in"
                >
                  <ZoomIn className="w-4 h-4" />
                </button>
              </div>
            )}
            {!isImage && (
              <div className="flex items-center space-x-1.5 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700 text-xs">
                <button
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="p-1 hover:bg-slate-700 rounded disabled:opacity-40"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="font-mono font-medium px-2">
                  Physical Page {currentPage} / {totalPages}
                </span>
                <button
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className="p-1 hover:bg-slate-700 rounded disabled:opacity-40"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}

            <a
              href={pdfBlobUrl || fallbackDirectUrl}
              target="_blank"
              rel="noreferrer"
              className="p-2 hover:bg-slate-800 rounded-lg text-slate-300 hover:text-white transition-colors"
              title="Open Raw PDF / Image in New Tab"
            >
              <ExternalLink className="w-4 h-4" />
            </a>

            <button
              onClick={onClose}
              className="p-2 hover:bg-red-600/80 rounded-lg text-slate-300 hover:text-white transition-colors ml-2"
              title="Close Viewer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 flex overflow-hidden">
          {/* Main Embedded Viewer */}
          <div className="flex-1 bg-slate-200 border-r border-slate-300 flex items-center justify-center relative p-2">
            {loading ? (
              <div className="flex flex-col items-center justify-center space-y-3 text-slate-600">
                <RefreshCw className="w-8 h-8 animate-spin text-blue-600" />
                <span className="text-sm font-semibold">Loading official authenticated evidence document...</span>
                <span className="text-xs text-slate-400">Verifying departmental credentials and security tokens</span>
              </div>
            ) : errorMessage ? (
              <div className="max-w-md p-6 bg-white rounded-xl border border-red-200 shadow-md text-center space-y-3">
                <div className="w-12 h-12 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto">
                  <ShieldAlert className="w-6 h-6" />
                </div>
                <h4 className="font-bold text-slate-800 text-sm">
                  {fileMissing ? 'Original File Not in Storage' : 'Unable to Display Document'}
                </h4>
                <p className="text-xs text-slate-600 leading-relaxed">{errorMessage}</p>
                {fileMissing ? (
                  <div className="pt-2 space-y-2 text-left">
                    <p className="text-[11px] text-slate-500">
                      If you hold the original file, you can upload it again. The current record is archived and
                      replaced by the new upload (requires permission to manage this document).
                    </p>
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,.webp,.tif,.tiff"
                      onChange={(e) => setReuploadFile(e.target.files?.[0] || null)}
                      className="block w-full text-[11px] text-slate-600"
                    />
                    <button
                      onClick={submitReupload}
                      disabled={!reuploadFile || reuploadState.busy || !!reuploadState.message}
                      className="w-full px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded text-xs font-semibold"
                    >
                      {reuploadState.busy ? 'Uploading…' : 'Re-upload original file'}
                    </button>
                    {reuploadState.message && <p className="text-[11px] text-emerald-700">{reuploadState.message}</p>}
                    {reuploadState.error && <p className="text-[11px] text-red-600">{reuploadState.error}</p>}
                  </div>
                ) : (
                  <button
                    onClick={() => setReloadKey((k) => k + 1)}
                    className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-semibold"
                  >
                    Retry
                  </button>
                )}
              </div>
            ) : isImage && pdfBlobUrl && !imageError ? (
              <div className="w-full h-full overflow-auto p-4 bg-slate-900/5 rounded-lg">
                <img
                  src={pdfBlobUrl}
                  alt={filename}
                  onError={() => setImageError(true)}
                  style={zoom === 1 ? undefined : { width: `${zoom * 100}%`, maxWidth: 'none', maxHeight: 'none' }}
                  className={`mx-auto rounded shadow-lg border border-slate-300 ${zoom === 1 ? 'max-h-full max-w-full object-contain' : ''}`}
                />
              </div>
            ) : isImage && imageError ? (
              <div className="max-w-md p-6 bg-white rounded-xl border border-amber-200 shadow-md text-center space-y-3">
                <div className="w-12 h-12 bg-amber-100 text-amber-600 rounded-full flex items-center justify-center mx-auto">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <h4 className="font-bold text-slate-800 text-sm">Image Rendering Issue</h4>
                <p className="text-xs text-slate-600 leading-relaxed">
                  The evidence image binary could not be rendered directly in this preview.
                </p>
                <div className="pt-2 flex justify-center gap-2">
                  <a
                    href={pdfBlobUrl || fallbackDirectUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-semibold"
                  >
                    Open Raw File
                  </a>
                  <button
                    onClick={() => setImageError(false)}
                    className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-semibold"
                  >
                    Retry
                  </button>
                </div>
              </div>
            ) : pdfBlobUrl ? (
              <iframe
                src={`${pdfBlobUrl}#page=${currentPage}`}
                title="Official PDF Viewer"
                className="w-full h-full border-0 rounded bg-white shadow-inner"
              />
            ) : (
              <div className="text-xs text-slate-500">No document source available.</div>
            )}
          </div>

          {/* Side Inspection Panel */}
          <div className="w-80 bg-slate-50 flex flex-col p-4 overflow-y-auto text-xs space-y-4">
            <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-sm">
              <h4 className="font-bold text-slate-800 mb-2 flex items-center justify-between">
                <span>Page Metadata</span>
                <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded text-[10px] font-bold">
                  {isImage ? 'Image Record' : `Physical Page ${currentPage}`}
                </span>
              </h4>
              <div className="space-y-1.5 text-slate-600">
                <div className="flex justify-between">
                  <span>Physical Page:</span>
                  <span className="font-semibold text-slate-900">
                    {isImage ? 'N/A (Image)' : currentPage}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Printed Page No:</span>
                  <span className="font-semibold text-slate-900">
                    {isImage ? 'N/A' : (activePageInfo?.printed_page_number || currentPage)}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span>OCR Processed:</span>
                  <span className="font-semibold">
                    {activePageInfo?.ocr_applied || isImage ? (
                      <span className="text-amber-600 flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" /> Yes (OCR)
                      </span>
                    ) : (
                      <span className="text-emerald-600 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" /> Native Digital
                      </span>
                    )}
                  </span>
                </div>
              </div>
            </div>

            {/* Extracted Text Snippet */}
            <div className="flex-1 bg-white p-3.5 rounded-lg border border-slate-200 shadow-sm flex flex-col">
              <h4 className="font-bold text-slate-800 mb-2">Extracted Page Evidence</h4>
              <div className="flex-1 bg-slate-100 p-2.5 rounded font-mono text-[11px] text-slate-700 overflow-y-auto leading-relaxed border border-slate-200">
                {loading ? (
                  <p className="italic text-slate-400">Loading extracted page text...</p>
                ) : activePageInfo?.text_snippet ? (
                  <span>{activePageInfo.text_snippet}</span>
                ) : pagesData.length > 0 && pagesData[0]?.text_snippet ? (
                  <span>{pagesData[0].text_snippet}</span>
                ) : ingestionStatus === 'PROCESSING' || ingestionStatus === 'IN_PROGRESS' ? (
                  <p className="italic text-blue-600">Document is currently undergoing OCR extraction and analysis...</p>
                ) : ingestionStatus === 'FAILED' ? (
                  <p className="italic text-red-500">OCR extraction failed for this document record.</p>
                ) : (
                  <div className="text-slate-500 italic">No extracted text available for this evidence record.</div>
                )}
              </div>
              <p className="text-[10px] text-slate-400 mt-2">
                Grounded RAG retrieval chunk source linked to {isImage ? 'source image evidence' : `physical page ${currentPage}`}.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

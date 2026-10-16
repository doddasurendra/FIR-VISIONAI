import React, { useState, useEffect } from 'react';
import { X, ChevronLeft, ChevronRight, FileText, CheckCircle2, AlertTriangle, ExternalLink, RefreshCw, ShieldAlert } from 'lucide-react';
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
  const [loading, setLoading] = useState<boolean>(true);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let activeBlobUrl: string | null = null;
    let isCancelled = false;

    const loadDocumentData = async () => {
      setLoading(true);
      setErrorMessage(null);
      try {
        // 1. Fetch metadata and pages info
        const metaRes = await api.get(`/documents/${documentId}/pages`);
        if (isCancelled) return;
        setFilename(metaRes.data.original_filename);
        setTotalPages(metaRes.data.physical_page_count || 1);
        setPagesData(metaRes.data.pages || []);

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
        if (status === 401) {
          setErrorMessage('Authentication session expired. Please log in again to view official records.');
        } else if (status === 403) {
          setErrorMessage('Access denied: You do not have departmental authorization to view evidence records from this jurisdiction.');
        } else if (status === 404) {
          setErrorMessage('Official evidence document file was not found on the server.');
        } else {
          setErrorMessage(err.response?.data?.detail || 'Failed to securely load the evidence document record.');
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
  }, [documentId]);

  const activePageInfo = pagesData.find((p) => p.physical_page_number === currentPage);
  const token = localStorage.getItem('token') || '';
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
                <h4 className="font-bold text-slate-800 text-sm">Unable to Display Document</h4>
                <p className="text-xs text-slate-600 leading-relaxed">{errorMessage}</p>
              </div>
            ) : isImage && pdfBlobUrl ? (
              <div className="w-full h-full flex items-center justify-center overflow-auto p-4 bg-slate-900/5 rounded-lg">
                <img
                  src={pdfBlobUrl}
                  alt={filename}
                  className="max-h-full max-w-full object-contain rounded shadow-lg border border-slate-300"
                />
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
                {activePageInfo?.text_snippet ? (
                  activePageInfo.text_snippet
                ) : (
                  <p className="italic text-slate-400">Loading extracted page text...</p>
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

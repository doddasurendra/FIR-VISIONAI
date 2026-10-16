import React, { useState, useEffect, useRef } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { useSearchParams } from 'react-router-dom';
import { PDFViewerModal } from '../components/pdf/PDFViewerModal';
import {
  BotMessageSquare,
  Send,
  FileText,
  Shield,
  Layers,
  Sparkles,
  ExternalLink,
  AlertCircle,
  HelpCircle,
  CheckCircle2,
  RefreshCw,
  UploadCloud
} from 'lucide-react';

export const AIFIRAssistance: React.FC = () => {
  const { t, language } = useLanguage();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();

  // Mode A: PDF_ONLY (Mandatory default when asking about an uploaded PDF)
  // Mode B: CROSS_CASE (Visibly labelled cross-case intelligence)
  const [mode, setMode] = useState<'PDF_ONLY' | 'CROSS_CASE'>('PDF_ONLY');
  const [documents, setDocuments] = useState<any[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>('');
  
  const [messages, setMessages] = useState<any[]>([
    {
      id: 'init-1',
      sender: 'ai',
      text: "Namaste Officer. I am FIR VisionAI, your AI case intelligence assistant. In 'Uploaded PDF Only' mode, I ground every answer exclusively in your selected FIR PDF with exact physical page citations. In 'Cross-Case Intelligence' mode, I analyze authorized patterns across cases within your jurisdiction.",
      mode: 'PDF_ONLY',
      citations: []
    }
  ]);
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeViewerModal, setActiveViewerModal] = useState<{ docId: string; page: number } | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadingDoc, setUploadingDoc] = useState(false);

  const handleDirectPdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    // Allow PDF, JPEG, PNG, WEBP — backend does magic-byte validation
    const allowed = /\.(pdf|jpe?g|png|webp)$/i;
    if (!allowed.test(file.name)) {
      alert('Unsupported file type. Please upload a PDF, JPEG, PNG, or WEBP file.');
      return;
    }
    setUploadingDoc(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await api.post('/documents/upload', fd);
      const newDoc = res.data;

      // Refresh documents list
      const docsRes = await api.get('/documents/');
      setDocuments(docsRes.data);
      setSelectedDocId(newDoc.id);

      const isImage = newDoc.is_image || !file.name.toLowerCase().endsWith('.pdf');
      const successText = isImage
        ? `🖼️ Image **${file.name}** uploaded, OCR-processed (Gemini multimodal), and indexed successfully.\n\nYou can now ask questions about this image. Answers will be grounded in the extracted text with image source citations.`
        : `📄 Evidence PDF **${file.name}** uploaded, hashed (SHA-256), and indexed successfully (${newDoc.physical_page_count} physical pages).\n\nYou can now ask questions about this document in Mode A. Every answer will be strictly grounded with clickable physical page citations.`;

      setMessages((prev) => [
        ...prev,
        {
          id: String(Date.now()),
          sender: 'ai',
          text: successText,
          mode: isImage ? 'IMAGE_ONLY' : 'PDF_ONLY',
          citations: []
        }
      ]);
    } catch (err: any) {
      alert('Upload error: ' + (err.response?.data?.detail || err.message));
    } finally {
      setUploadingDoc(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Fetch available documents, respecting docId from URL search params
  useEffect(() => {
    const fetchDocs = async () => {
      try {
        const res = await api.get('/documents/');
        setDocuments(res.data);
        const paramDocId = searchParams.get('docId');
        if (paramDocId && res.data.some((d: any) => d.id === paramDocId)) {
          setSelectedDocId(paramDocId);
        } else if (res.data.length > 0) {
          setSelectedDocId(res.data[0].id);
        }
      } catch (e) {
        console.error('Failed to load documents:', e);
      }
    };
    fetchDocs();
  }, [user]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSelectDocument = (docId: string) => {
    setSelectedDocId(docId);
    const targetDoc = documents.find((d) => d.id === docId);
    const isImg = targetDoc?.mime_type?.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(targetDoc?.original_filename || '');
    
    // Clear previous conversation and citations when changing documents to prevent stale context
    setMessages([
      {
        id: `init-${docId}`,
        sender: 'ai',
        text: isImg
          ? `Selected image evidence **${targetDoc?.original_filename || 'Record'}**. Answers will be grounded exclusively in this image without invented page numbers.`
          : `Selected FIR PDF **${targetDoc?.original_filename || 'Record'}** (${targetDoc?.physical_page_count || 1} physical pages). Grounded exclusively in this document with physical page citations.`,
        mode: isImg ? 'IMAGE_ONLY' : 'PDF_ONLY',
        citations: []
      }
    ]);
  };

  const handleClearChat = () => {
    const isImg = selectedDocObj?.mime_type?.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(selectedDocObj?.original_filename || '');
    setMessages([
      {
        id: `reset-${Date.now()}`,
        sender: 'ai',
        text: mode === 'PDF_ONLY'
          ? (isImg
              ? `Conversation reset for **${selectedDocObj?.original_filename || 'Image'}**.`
              : `Conversation reset for **${selectedDocObj?.original_filename || 'PDF'}**.`)
          : "Conversation reset. You may ask authorized cross-case questions within your jurisdiction.",
        mode: mode === 'PDF_ONLY' ? (isImg ? 'IMAGE_ONLY' : 'PDF_ONLY') : 'CROSS_CASE',
        citations: []
      }
    ]);
  };

  const handleSendMessage = async (customQuery?: string) => {
    const queryToSend = customQuery || queryInput;
    if (!queryToSend.trim()) return;

    if (mode === 'PDF_ONLY' && !selectedDocId) {
      alert('Please select an uploaded FIR document first for grounded RAG.');
      return;
    }

    const isImg = selectedDocObj?.mime_type?.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(selectedDocObj?.original_filename || '');
    const activeMode = mode === 'PDF_ONLY' ? (isImg ? 'IMAGE_ONLY' : 'PDF_ONLY') : 'CROSS_CASE';

    const userMsg = {
      id: String(Date.now()),
      sender: 'user',
      text: queryToSend,
      mode: activeMode
    };
    setMessages((prev) => [...prev, userMsg]);
    if (!customQuery) setQueryInput('');
    setLoading(true);

    try {
      const payload: any = {
        query: queryToSend,
        mode: activeMode,
        language
      };
      if (mode === 'PDF_ONLY') {
        payload.document_id = selectedDocId;
      }

      const res = await api.post('/rag/query', payload);
      const aiMsg = {
        id: String(Date.now() + 1),
        sender: 'ai',
        text: res.data.answer,
        mode: res.data.mode,
        citations: res.data.citations || [],
        documentId: res.data.document_id,
        isAggregate: res.data.is_aggregate_count
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (e: any) {
      const errText = e.response?.data?.detail || 'An error occurred during retrieval.';
      setMessages((prev) => [
        ...prev,
        {
          id: String(Date.now() + 1),
          sender: 'ai',
          text: `⚠️ Error: ${errText}`,
          mode: activeMode,
          citations: []
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const selectedDocObj = documents.find((d) => d.id === selectedDocId);
  const isSelectedDocImage = selectedDocObj?.mime_type?.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(selectedDocObj?.original_filename || '');

  return (
    <div className="h-[calc(100vh-7.5rem)] flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Top Mode Header Banner */}
      <div className="bg-slate-900 text-white p-4 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-blue-600 rounded-lg">
            <BotMessageSquare className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span>AI FIR Assistance</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                Grounded RAG v1.0
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              Departmental Investigative Copilot | Data Scope: <span className="font-semibold text-emerald-400">{user?.role}</span>
            </p>
          </div>
        </div>

        {/* Mode Selector Tabs */}
        <div className="flex items-center bg-slate-800 p-1 rounded-lg border border-slate-700 text-xs">
          <button
            onClick={() => setMode('PDF_ONLY')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold transition-all ${
              mode === 'PDF_ONLY'
                ? 'bg-blue-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Mode A: Uploaded Document Only</span>
          </button>

          <button
            onClick={() => setMode('CROSS_CASE')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold transition-all ${
              mode === 'CROSS_CASE'
                ? 'bg-blue-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Mode B: Cross-Case Intelligence</span>
          </button>
        </div>
      </div>

      {/* Sub-header: Document Picker for Mode A */}
      {mode === 'PDF_ONLY' && (
        <div className="bg-blue-50/70 border-b border-blue-100 px-6 py-2.5 flex flex-wrap items-center justify-between text-xs gap-3">
          <div className="flex items-center space-x-2">
            <span className="font-semibold text-blue-900">
              {isSelectedDocImage ? 'Active Image Evidence:' : 'Active Source PDF:'}
            </span>
            <select
              value={selectedDocId}
              onChange={(e) => handleSelectDocument(e.target.value)}
              className="bg-white border border-blue-200 text-blue-950 font-medium px-3 py-1 rounded-md text-xs focus:ring-2 focus:ring-blue-500"
            >
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.original_filename} ({d.mime_type?.startsWith('image/') ? 'Image Record' : `${d.physical_page_count} Pages`})
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleClearChat}
              className="ml-2 px-2 py-1 bg-white hover:bg-slate-100 border border-slate-300 rounded text-[11px] text-slate-600 font-medium"
              title="Reset conversation and clear citations"
            >
              Clear Chat
            </button>
          </div>

          <div className="flex items-center space-x-3">
            {selectedDocObj && (
              <div className="flex items-center space-x-3 text-blue-800 text-[11px]">
                <span>SHA-256: <code className="font-mono">{selectedDocObj.file_hash?.slice(0, 10)}...</code></span>
                <button
                  onClick={() => setActiveViewerModal({ docId: selectedDocObj.id, page: 1 })}
                  className="underline hover:text-blue-950 font-semibold flex items-center gap-1"
                >
                  <ExternalLink className="w-3 h-3" />
                  <span>{isSelectedDocImage ? 'Open Evidence Viewer' : 'Open PDF Viewer'}</span>
                </button>
              </div>
            )}

            {/* Direct Document Upload Button */}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleDirectPdfUpload}
              accept=".pdf,.jpg,.jpeg,.png,.webp"
              className="hidden"
            />
            <button
              type="button"
              disabled={uploadingDoc}
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-md font-semibold text-xs shadow-sm transition-colors disabled:opacity-50"
              title="Upload new FIR evidence PDF or image for instant grounded RAG"
            >
              <UploadCloud className="w-3.5 h-3.5" />
              <span>{uploadingDoc ? 'Uploading & Indexing...' : 'Upload Document'}</span>
            </button>
          </div>
        </div>
      )}

      {/* Cross-case Scope Notice for Mode B */}
      {mode === 'CROSS_CASE' && (
        <div className="bg-slate-100 border-b border-slate-200 px-6 py-2 flex items-center justify-between text-xs text-slate-700">
          <span className="flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-blue-600" />
            Authorized Cross-Case Intelligence strictly scoped to: <strong className="text-slate-900">{user?.station || user?.district || 'State Headquarters'}</strong>
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleClearChat}
              className="px-2 py-0.5 bg-white hover:bg-slate-200 border border-slate-300 rounded text-[11px] text-slate-600 font-medium"
            >
              Clear Chat
            </button>
            <span className="text-[11px] text-slate-500 font-medium">SQL Parametric Aggregates Enabled</span>
          </div>
        </div>
      )}

      {/* Chat Messages Stream */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50/50">
        {messages.map((m) => {
          const isUser = m.sender === 'user';
          return (
            <div
              key={m.id}
              className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
            >
              <div
                className={`max-w-2xl rounded-2xl p-4 shadow-sm text-xs leading-relaxed ${
                  isUser
                    ? 'bg-blue-600 text-white rounded-br-none'
                    : 'bg-white text-slate-800 border border-slate-200 rounded-bl-none'
                }`}
              >
                <div className="whitespace-pre-wrap font-sans">{m.text}</div>

                {/* Validated Citations Footer (Clickable!) */}
                {!isUser && m.citations && m.citations.length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-slate-100 flex flex-wrap gap-1.5 items-center">
                    <span className="text-[11px] font-bold text-slate-500 mr-1">
                      Validated Citations:
                    </span>
                    {m.citations.map((c: any, cIdx: number) => (
                      <button
                        key={cIdx}
                        onClick={() => {
                          setActiveViewerModal({
                            docId: c.document_id || selectedDocId,
                            page: c.physical_page_number || 1
                          });
                        }}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 transition-colors shadow-2xs"
                        title={c.physical_page_number ? "Click to jump to physical page in evidence viewer" : "Click to inspect evidence image"}
                      >
                        <FileText className="w-3 h-3 text-blue-600" />
                        <span>{c.source_label}</span>
                        <ExternalLink className="w-2.5 h-2.5 ml-0.5 opacity-60" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex items-center space-x-2 text-xs text-slate-500 italic p-3 bg-white rounded-xl border border-slate-200 w-fit">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-600" />
            <span>Retrieving authorized evidence chunks and synthesizing grounded answer...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Query Chips */}
      <div className="px-6 py-2 bg-white border-t border-slate-100 flex items-center gap-2 overflow-x-auto text-[11px]">
        <span className="text-slate-400 font-medium whitespace-nowrap">Suggested:</span>
        {mode === 'PDF_ONLY' ? (
          isSelectedDocImage ? (
            <>
              <button
                onClick={() => handleSendMessage('Summarize visible evidence in this image.')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "Summarize visible evidence"
              </button>
              <button
                onClick={() => handleSendMessage('What persons or names are visible in this document?')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "What persons or names are visible?"
              </button>
              <button
                onClick={() => handleSendMessage('What items or quantities are recorded?')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "What items or quantities are recorded?"
              </button>
              <button
                onClick={() => handleSendMessage('What is the accused previous criminal history?')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "Criminal history? (Tests missing info)"
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => handleSendMessage('Summarize this FIR concisely.')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "Summarize this FIR"
              </button>
              <button
                onClick={() => handleSendMessage('Who are the accused or persons mentioned in this document?')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "Who are the accused / persons?"
              </button>
              <button
                onClick={() => handleSendMessage('What contraband or items were seized in this case?')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "What items were seized?"
              </button>
              <button
                onClick={() => handleSendMessage('Where and when did the occurrence take place?')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "Where and when did it occur?"
              </button>
              <button
                onClick={() => handleSendMessage('What is the accused person previous criminal history?')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
              >
                "Criminal history? (Tests missing info)"
              </button>
            </>
          )
        ) : (
          <>
            <button
              onClick={() => handleSendMessage('How many cases were registered in this district this year?')}
              className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
            >
              "How many cases registered in this district?"
            </button>
            <button
              onClick={() => handleSendMessage('Show cases involving Auto AP21TY4567')}
              className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
            >
              "Cases involving Auto AP21TY4567"
            </button>
            <button
              onClick={() => handleSendMessage('Which entities appear in multiple cases?')}
              className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap transition-colors"
            >
              "Entities appearing in multiple cases"
            </button>
          </>
        )}
      </div>

      {/* Input Form */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSendMessage();
        }}
        className="p-4 bg-white border-t border-slate-200 flex items-center space-x-3"
      >
        <input
          type="text"
          value={queryInput}
          onChange={(e) => setQueryInput(e.target.value)}
          placeholder={
            mode === 'PDF_ONLY'
              ? 'Ask anything about the selected FIR PDF (Answer will cite physical page)...'
              : 'Ask a cross-case investigative question within your jurisdiction...'
          }
          className="flex-1 text-xs border border-slate-300 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-2xs"
        />
        <button
          type="submit"
          disabled={loading || !queryInput.trim()}
          className="px-5 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 disabled:opacity-50 transition-colors"
        >
          <Send className="w-4 h-4" />
          <span>Send</span>
        </button>
      </form>

      {/* Physical PDF Viewer Modal (Triggered by clicking citation) */}
      {activeViewerModal && (
        <PDFViewerModal
          documentId={activeViewerModal.docId}
          initialPage={activeViewerModal.page}
          onClose={() => setActiveViewerModal(null)}
        />
      )}
    </div>
  );
};

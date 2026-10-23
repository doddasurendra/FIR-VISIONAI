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
  BookOpen,
  Sparkles,
  ExternalLink,
  AlertCircle,
  HelpCircle,
  CheckCircle2,
  RefreshCw,
  UploadCloud,
  Languages,
  Scale
} from 'lucide-react';

export const AIFIRAssistance: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();

  // Mode A: PDF_ONLY (Selected FIR Only)
  // Mode B: KNOWLEDGE_BASE_ONLY (Official Knowledge Base)
  // Mode C: FIR_PLUS_LEGAL (FIR + Legal Corpus)
  // Mode D: CROSS_CASE (Cross-Case Intelligence)
  const [mode, setMode] = useState<'PDF_ONLY' | 'KNOWLEDGE_BASE_ONLY' | 'FIR_PLUS_LEGAL' | 'CROSS_CASE'>('PDF_ONLY');
  const [documents, setDocuments] = useState<any[]>([]);
  const [historicalFirs, setHistoricalFirs] = useState<any[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>('');

  // Chat-specific language selection ('en' | 'te' | 'hi')
  const [chatLanguage, setChatLanguage] = useState<'en' | 'te' | 'hi'>('en');
  const [hasSelectedLanguage, setHasSelectedLanguage] = useState<boolean>(false);

  const [messages, setMessages] = useState<any[]>([
    {
      id: 'init-1',
      sender: 'ai',
      text: "Namaste Officer. I am FIR VisionAI, your AI case intelligence assistant.\n\n• **Mode A (Selected FIR Only):** Grounds every answer exclusively in your selected FIR document with exact physical page citations.\n• **Mode B (Knowledge Base Only):** Answers exclusively from authorized departmental legal acts, circulars, and reference guides for your jurisdiction.\n• **Mode C (FIR + Legal Corpus):** Synthesizes facts from your selected FIR with verified statutory sections from the Indian Legal Corpus (BNS, AP Excise, NDPS, Constitution).\n• **Mode D (Cross-Case Intelligence):** Analyzes authorized multi-case patterns across your jurisdiction.",
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

  const handleSelectLanguage = (lang: 'en' | 'te' | 'hi') => {
    setChatLanguage(lang);
    setHasSelectedLanguage(true);
    const confirmationTexts = {
      en: "Language set to **English**. All subsequent answers will be synthesized in English.",
      te: "సమాధానాల భాష **తెలుగు**గా ఎంపిక చేయబడింది. తదుపరి సమాధానాలన్నీ తెలుగులోనే అందించబడతాయి.",
      hi: "उत्तरों की भाषा **हिन्दी** चुनी गई है। आगे के सभी उत्तर हिन्दी में प्रस्तुत किए जाएंगे।"
    };
    setMessages((prev) => [
      ...prev,
      {
        id: `lang-confirm-${Date.now()}`,
        sender: 'ai',
        text: confirmationTexts[lang],
        mode: mode,
        citations: []
      }
    ]);
  };

  const handleDirectPdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
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
      const rawDocs = Array.isArray(docsRes.data) ? docsRes.data : (docsRes.data?.documents || []);
      setDocuments(rawDocs);
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
        const [docsRes, histRes] = await Promise.all([
          api.get('/documents/'),
          api.get('/documents/historical-firs').catch(() => ({ data: { records: [] } }))
        ]);
        const docsList = Array.isArray(docsRes.data) ? docsRes.data : (docsRes.data?.documents || []);
        const histList = histRes.data?.records || [];
        setDocuments(docsList);
        setHistoricalFirs(histList);

        const paramDocId = searchParams.get('docId');
        if (paramDocId && (docsList.some((d: any) => d.id === paramDocId) || histList.some((h: any) => h.document_id === paramDocId || h.id === paramDocId))) {
          setSelectedDocId(paramDocId);
        } else if (histList.length > 0) {
          setSelectedDocId(histList[0].document_id || histList[0].id);
        } else if (docsList.length > 0) {
          setSelectedDocId(docsList[0].id);
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
    const targetDoc = documents.find((d) => d.id === docId) || historicalFirs.find((d) => d.document_id === docId || d.id === docId);
    const isImg = targetDoc?.mime_type?.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(targetDoc?.original_filename || '');
    const docLabel = targetDoc?.display_label || targetDoc?.original_filename || 'Record';

    // Clear previous conversation and citations when changing documents to prevent stale context
    setMessages([
      {
        id: `init-${docId}`,
        sender: 'ai',
        text: isImg
          ? `Selected image evidence **${docLabel}**. Answers will be grounded exclusively in this image without invented page numbers.`
          : `Selected FIR record **${docLabel}** (${targetDoc?.physical_page_count || 1} physical pages). Grounded exclusively in this document with physical page citations.`,
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
          : mode === 'KNOWLEDGE_BASE_ONLY'
          ? 'Conversation reset. You may now ask questions across authorized departmental Knowledge Base acts, circulars, and reference materials.'
          : mode === 'FIR_PLUS_LEGAL'
          ? `Conversation reset for FIR + Legal Corpus mode on **${selectedDocObj?.original_filename || 'Selected FIR'}**. Both case facts and applicable statutes will be cited.`
          : "Conversation reset. You may ask authorized cross-case questions within your jurisdiction.",
        mode: mode === 'KNOWLEDGE_BASE_ONLY' ? 'KNOWLEDGE_BASE_ONLY' : (mode === 'FIR_PLUS_LEGAL' ? 'FIR_PLUS_LEGAL' : (mode === 'PDF_ONLY' ? (isImg ? 'IMAGE_ONLY' : 'PDF_ONLY') : 'CROSS_CASE')),
        citations: []
      }
    ]);
  };

  const handleSendMessage = async (customQuery?: string) => {
    const queryToSend = customQuery || queryInput;
    if (!queryToSend.trim()) return;

    if ((mode === 'PDF_ONLY' || mode === 'FIR_PLUS_LEGAL') && !selectedDocId) {
      alert('Please select an uploaded FIR document first.');
      return;
    }

    const isImg = selectedDocObj?.mime_type?.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(selectedDocObj?.original_filename || '');
    const activeMode = mode === 'KNOWLEDGE_BASE_ONLY'
      ? 'KNOWLEDGE_BASE_ONLY'
      : (mode === 'FIR_PLUS_LEGAL' ? 'FIR_PLUS_LEGAL' : (mode === 'PDF_ONLY' ? (isImg ? 'IMAGE_ONLY' : 'PDF_ONLY') : 'CROSS_CASE'));

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
        language: chatLanguage
      };
      if (mode === 'PDF_ONLY' || mode === 'FIR_PLUS_LEGAL') {
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
      const errDetail = e.response?.data?.detail || e.message;
      let errText = `⚠️ Error: ${errDetail}`;
      if (chatLanguage === 'te') {
        errText = `⚠️ లోపం: ${errDetail || 'సమాచారాన్ని పొందడంలో సమస్య ఏర్పడింది.'}`;
      } else if (chatLanguage === 'hi') {
        errText = `⚠️ त्रुटि: ${errDetail || 'जानकारी प्राप्त करने में समस्या उत्पन्न हुई।'}`;
      }
      setMessages((prev) => [
        ...prev,
        {
          id: String(Date.now() + 1),
          sender: 'ai',
          text: errText,
          mode: activeMode,
          citations: []
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const selectedDocObj =
    documents.find((d) => d.id === selectedDocId) ||
    historicalFirs.find((d) => d.document_id === selectedDocId || d.id === selectedDocId);
  const isSelectedDocImage =
    selectedDocObj?.is_image ||
    selectedDocObj?.mime_type?.startsWith('image/') ||
    /\.(jpe?g|png|webp)$/i.test(selectedDocObj?.original_filename || '');

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

        {/* Right Header Controls: Mode Selector & Chat Language Switcher */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Persistent Chat Language Switcher */}
          <div className="flex items-center space-x-1 bg-slate-800 p-1 rounded-lg border border-slate-700 text-xs">
            <span className="text-slate-400 px-1 text-[11px] font-medium flex items-center gap-1">
              <Languages className="w-3.5 h-3.5 text-amber-300" />
              <span>Language:</span>
            </span>
            <button
              type="button"
              onClick={() => handleSelectLanguage('en')}
              className={`px-2 py-0.5 rounded text-[11px] font-bold transition-all ${
                chatLanguage === 'en' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-300 hover:text-white'
              }`}
            >
              English
            </button>
            <button
              type="button"
              onClick={() => handleSelectLanguage('te')}
              className={`px-2 py-0.5 rounded text-[11px] font-bold transition-all ${
                chatLanguage === 'te' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-300 hover:text-white'
              }`}
            >
              తెలుగు
            </button>
            <button
              type="button"
              onClick={() => handleSelectLanguage('hi')}
              className={`px-2 py-0.5 rounded text-[11px] font-bold transition-all ${
                chatLanguage === 'hi' ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-300 hover:text-white'
              }`}
            >
              हिन्दी
            </button>
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
              <span>Mode A: Selected FIR Only</span>
            </button>

            <button
              onClick={() => setMode('KNOWLEDGE_BASE_ONLY')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold transition-all ${
                mode === 'KNOWLEDGE_BASE_ONLY'
                  ? 'bg-emerald-700 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>Mode B: Knowledge Base Only</span>
            </button>

            <button
              onClick={() => setMode('FIR_PLUS_LEGAL')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold transition-all ${
                mode === 'FIR_PLUS_LEGAL'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Scale className="w-3.5 h-3.5" />
              <span>Mode C: FIR + Legal Corpus</span>
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
              <span>Mode D: Cross-Case</span>
            </button>
          </div>
        </div>
      </div>

      {/* Sub-header: Mode B Knowledge Base Info */}
      {mode === 'KNOWLEDGE_BASE_ONLY' && (
        <div className="bg-emerald-50/80 border-b border-emerald-200 px-6 py-2.5 flex flex-wrap items-center justify-between text-xs gap-3">
          <div className="flex items-center space-x-2">
            <BookOpen className="w-4 h-4 text-emerald-700" />
            <span className="font-semibold text-emerald-950">
              Active Source: Official Departmental Knowledge Base (AP Acts, Circulars, SOPs & Reference Materials)
            </span>
          </div>
          <span className="text-[11px] font-semibold text-emerald-800 bg-white border border-emerald-300 px-2.5 py-0.5 rounded shadow-xs">
            Jurisdiction: {user?.district || 'Statewide Legal Corpus'}
          </span>
        </div>
      )}

      {/* Sub-header: Mode C FIR + Legal Corpus Info & Picker */}
      {mode === 'FIR_PLUS_LEGAL' && (
        <div className="bg-indigo-50/80 border-b border-indigo-200 px-6 py-2.5 flex flex-wrap items-center justify-between text-xs gap-3">
          <div className="flex items-center space-x-2">
            <Scale className="w-4 h-4 text-indigo-700" />
            <span className="font-semibold text-indigo-950">
              Active Sources: Selected FIR Document + Official Indian Legal Corpus (BNS 2023, AP Excise, NDPS, Constitution)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              className="bg-white border border-indigo-300 rounded px-2.5 py-1 text-xs text-indigo-950 font-medium focus:outline-none focus:ring-1 focus:ring-indigo-500 max-w-md truncate"
            >
              <option value="">-- Choose FIR Case Document --</option>
              {historicalFirs.length > 0 && (
                <optgroup label="Historical FIR Records">
                  {historicalFirs.map((hf) => (
                    <option key={hf.document_id || hf.id} value={hf.document_id || hf.id}>
                      {hf.display_label}
                    </option>
                  ))}
                </optgroup>
              )}
              {documents.filter((d) => d.doc_category === 'FIR' || !d.doc_category || d.case_id).length > 0 && (
                <optgroup label="Uploaded Case Evidence">
                  {documents
                    .filter((d) => d.doc_category === 'FIR' || !d.doc_category || d.case_id)
                    .map((doc) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.original_filename} ({doc.mime_type?.startsWith('image/') ? 'Image Record' : `${doc.physical_page_count || 1} pages`})
                      </option>
                    ))}
                </optgroup>
              )}
            </select>
          </div>
        </div>
      )}

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
              className="bg-white border border-blue-200 text-blue-950 font-medium px-3 py-1 rounded-md text-xs focus:ring-2 focus:ring-blue-500 max-w-md truncate"
            >
              {historicalFirs.length > 0 && (
                <optgroup label="Historical FIR Records">
                  {historicalFirs.map((hf) => (
                    <option key={hf.document_id || hf.id} value={hf.document_id || hf.id}>
                      {hf.display_label}
                    </option>
                  ))}
                </optgroup>
              )}
              {documents.filter((d) => d.doc_category === 'FIR' || !d.doc_category || d.case_id).length > 0 && (
                <optgroup label="Uploaded Case Evidence">
                  {documents
                    .filter((d) => d.doc_category === 'FIR' || !d.doc_category || d.case_id)
                    .map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.original_filename} ({d.mime_type?.startsWith('image/') ? 'Image Record' : `${d.physical_page_count || 1} Pages`})
                      </option>
                    ))}
                </optgroup>
              )}
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
        {/* Interactive Language Selector Card — Always visible before first user question */}
        {!hasSelectedLanguage && (
          <div className="bg-gradient-to-r from-blue-50 via-indigo-50 to-emerald-50 border border-blue-200 rounded-2xl p-4 shadow-xs space-y-2.5 max-w-2xl animate-in fade-in duration-200">
            <div className="flex items-center space-x-2">
              <Languages className="w-4 h-4 text-blue-700" />
              <h3 className="text-xs font-bold text-blue-950 uppercase tracking-wide">
                Language Selection / భాష ఎంపిక / भाषा चयन
              </h3>
            </div>
            <p className="text-xs font-medium text-slate-800">
              Which language would you like the answers in?
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                onClick={() => handleSelectLanguage('en')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                  chatLanguage === 'en'
                    ? 'bg-blue-600 text-white border-blue-700 shadow-xs'
                    : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
                }`}
              >
                English
              </button>
              <button
                type="button"
                onClick={() => handleSelectLanguage('te')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                  chatLanguage === 'te'
                    ? 'bg-blue-600 text-white border-blue-700 shadow-xs'
                    : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
                }`}
              >
                తెలుగు (Telugu)
              </button>
              <button
                type="button"
                onClick={() => handleSelectLanguage('hi')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                  chatLanguage === 'hi'
                    ? 'bg-blue-600 text-white border-blue-700 shadow-xs'
                    : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
                }`}
              >
                हिन्दी (Hindi)
              </button>
            </div>
          </div>
        )}

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
            <span>
              {chatLanguage === 'te'
                ? 'పత్ర ఆధారాలను విశ్లేషించి సమాధానం తయారుచేస్తోంది...'
                : chatLanguage === 'hi'
                ? 'साक्ष्य विश्लेषण कर उत्तर तैयार किया जा रहा है...'
                : 'Retrieving authorized evidence chunks and synthesizing grounded answer...'}
            </span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Query Chips */}
      <div className="px-6 py-2 bg-white border-t border-slate-100 flex items-center gap-2 overflow-x-auto text-[11px]">
        <span className="text-slate-400 font-medium whitespace-nowrap">Suggested:</span>
        {mode === 'PDF_ONLY' ? (
          isSelectedDocImage ? (
            chatLanguage === 'te' ? (
              <>
                <button onClick={() => handleSendMessage('ఈ చిత్రంలోని సాక్ష్యాలను సంక్షిప్తంగా వివరించండి.')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"సాక్ష్యాల సారాంశం"</button>
                <button onClick={() => handleSendMessage('ఈ పత్రంలో ఏ వ్యక్తులు లేదా పేర్లు ఉన్నాయి?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"వ్యక్తుల పేర్లు"</button>
                <button onClick={() => handleSendMessage('నిందితుడి గత నేర చరిత్ర ఏమిటి?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"గత నేర చరిత్ర?"</button>
              </>
            ) : chatLanguage === 'hi' ? (
              <>
                <button onClick={() => handleSendMessage('इस छवि में दिखाई देने वाले साक्ष्यों का संक्षिप्त सारांश दें।')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"साक्ष्य सारांश"</button>
                <button onClick={() => handleSendMessage('इस दस्तावेज़ में कौन से व्यक्ति दर्ज हैं?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"व्यक्ति / नाम"</button>
                <button onClick={() => handleSendMessage('अभियुक्त का पिछला आपराधिक इतिहास क्या है?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"पिछला इतिहास?"</button>
              </>
            ) : (
              <>
                <button onClick={() => handleSendMessage('Summarize visible evidence in this image.')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"Summarize visible evidence"</button>
                <button onClick={() => handleSendMessage('What persons or names are visible in this document?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"What persons or names are visible?"</button>
                <button onClick={() => handleSendMessage('What is the accused previous criminal history?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"Criminal history? (Tests missing info)"</button>
              </>
            )
          ) : (
            chatLanguage === 'te' ? (
              <>
                <button onClick={() => handleSendMessage('ఈ FIR పత్రాన్ని సంక్షిప్తంగా వివరించండి.')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"FIR సారాంశం"</button>
                <button onClick={() => handleSendMessage('ఈ పత్రంలో పేర్కొన్న నిందితులు లేదా వ్యక్తులు ఎవరు?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"నిందితుల వివరాలు"</button>
                <button onClick={() => handleSendMessage('ఈ కేసులో స్వాధీనం చేసుకున్న నిషేధిత వస్తువులు ఏమిటి?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"స్వాధీనం చేసుకున్న వస్తువులు"</button>
                <button onClick={() => handleSendMessage('నిందితుడి మునుపటి క్రిమినల్ హిస్టరీ ఏమిటి?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"గత నేర చరిత్ర? (అనుపలబ్ధ సమాచారం)"</button>
              </>
            ) : chatLanguage === 'hi' ? (
              <>
                <button onClick={() => handleSendMessage('इस FIR का संक्षिप्त सारांश प्रस्तुत करें।')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"FIR का सारांश"</button>
                <button onClick={() => handleSendMessage('इस दस्तावेज़ में किन अभियुक्तों के नाम दर्ज हैं?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"अभियुक्तों के नाम"</button>
                <button onClick={() => handleSendMessage('इस मामले में क्या प्रतिबंधित सामग्री ज़ब्त की गई?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"ज़ब्त सामग्री"</button>
                <button onClick={() => handleSendMessage('अभियुक्त का पिछला आपराधिक इतिहास क्या है?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"आपराधिक इतिहास? (अनुपलब्ध जानकारी)"</button>
              </>
            ) : (
              <>
                <button onClick={() => handleSendMessage('Summarize this FIR concisely.')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"Summarize this FIR"</button>
                <button onClick={() => handleSendMessage('Who are the accused or persons mentioned in this document?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"Who are the accused / persons?"</button>
                <button onClick={() => handleSendMessage('What contraband or items were seized in this case?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"What items were seized?"</button>
                <button onClick={() => handleSendMessage('What is the accused person previous criminal history?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"Criminal history? (Tests missing info)"</button>
              </>
            )
          )
        ) : (
          chatLanguage === 'te' ? (
            <>
              <button onClick={() => handleSendMessage('ఈ సంవత్సరం ఈ జిల్లాలో ఎన్ని కేసులు నమోదయ్యాయి?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"జిల్లాలో నమోదైన మొత్తం కేసులు?"</button>
              <button onClick={() => handleSendMessage('ఆటో AP21TY4567 సంబంధిత కేసులు చూపించండి')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"ఆటో AP21TY4567 కేసులు"</button>
            </>
          ) : chatLanguage === 'hi' ? (
            <>
              <button onClick={() => handleSendMessage('इस वर्ष इस जिले में कितने मामले दर्ज किए गए?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"जिले में कुल दर्ज मामले?"</button>
              <button onClick={() => handleSendMessage('ऑटो AP21TY4567 से संबंधित मामले दिखाएं')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"ऑटो AP21TY4567 मामले"</button>
            </>
          ) : (
            <>
              <button onClick={() => handleSendMessage('How many cases were registered in this district this year?')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"How many cases registered in this district?"</button>
              <button onClick={() => handleSendMessage('Show cases involving Auto AP21TY4567')} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap">"Cases involving Auto AP21TY4567"</button>
            </>
          )
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
            chatLanguage === 'te'
              ? mode === 'PDF_ONLY'
                ? 'ఎంచుకున్న FIR PDF గురించి ఏదైనా అడగండి (పేజీ నంబర్ సూచించబడుతుంది)...'
                : 'అధికారిక పరిధిలోని కేసుల గురించి విచారణ ప్రశ్న అడగండి...'
              : chatLanguage === 'hi'
              ? mode === 'PDF_ONLY'
                ? 'चयनित FIR PDF के बारे में कोई प्रश्न पूछें (पृष्ठ संदर्भ सहित)...'
                : 'अधिकार क्षेत्र के मामलों के बारे में प्रश्न पूछें...'
              : mode === 'PDF_ONLY'
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

export default AIFIRAssistance;

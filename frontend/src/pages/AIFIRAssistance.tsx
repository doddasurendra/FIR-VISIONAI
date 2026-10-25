import React, { useState, useEffect, useRef } from 'react';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useSearchParams } from 'react-router-dom';
import { PDFViewerModal } from '../components/pdf/PDFViewerModal';
import {
  BotMessageSquare, Send, FileText, Shield, Layers, BookOpen, ExternalLink, RefreshCw,
  UploadCloud, Languages, Scale, FolderOpen, ShieldCheck, Search, Info, ChevronDown, ChevronUp,
} from 'lucide-react';

type Scope = 'CURRENT_FIR' | 'CASE' | 'FIR_AND_LAW' | 'KNOWLEDGE_BASE' | 'ALL_AUTHORIZED';
type Lang = 'en' | 'te' | 'hi';

interface Citation {
  source_number?: number;
  document_id?: string;
  document_name?: string;
  physical_page_number?: number | null;
  section_ref?: string | null;
  section_title?: string | null;
  category?: string | null;
  source_type?: string;
  legal_status?: string | null;
  official_source_url?: string | null;
  is_image?: boolean;
  evidence_excerpt?: string;
  source_label: string;
  case_id?: string | null;
  fir_number?: string;
}

interface ChatMessage {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  scope: Scope;
  citations?: Citation[];
  notFound?: boolean;
  suggestedScope?: Scope | null;
  question?: string;
  answerMethod?: string;
  legalMode?: boolean;
  isError?: boolean;
}

const SCOPES: { key: Scope; label: string; icon: React.FC<{ className?: string }>; active: string; needsDoc: boolean }[] = [
  { key: 'CURRENT_FIR', label: 'Current FIR', icon: FileText, active: 'bg-blue-600', needsDoc: true },
  { key: 'CASE', label: 'Case + evidence', icon: FolderOpen, active: 'bg-sky-700', needsDoc: true },
  { key: 'FIR_AND_LAW', label: 'FIR + Law', icon: Scale, active: 'bg-indigo-600', needsDoc: true },
  { key: 'KNOWLEDGE_BASE', label: 'Knowledge Base', icon: BookOpen, active: 'bg-emerald-700', needsDoc: false },
  { key: 'ALL_AUTHORIZED', label: 'All authorised', icon: Layers, active: 'bg-slate-600', needsDoc: false },
];

const SCOPE_DESCRIPTIONS: Record<Scope, string> = {
  CURRENT_FIR: 'Answers only from the selected FIR document, with page citations.',
  CASE: 'Answers from every searchable document of the selected FIR’s case that you may access.',
  FIR_AND_LAW: 'Answers from the selected FIR and the legal corpus, keeping what the FIR states separate from what the law states.',
  KNOWLEDGE_BASE: 'Answers from Knowledge Base documents you may access (laws, circulars, guides, references, approved evidence).',
  ALL_AUTHORIZED: 'Answers from every searchable document within your jurisdiction.',
};

const SCOPE_LABEL: Record<Scope, string> = Object.fromEntries(SCOPES.map((s) => [s.key, s.label])) as Record<Scope, string>;

const SUGGESTIONS: Record<'fir' | 'law' | 'kb' | 'all', Record<Lang, string[]>> = {
  fir: {
    en: ['What incident is described in this FIR?', 'What is the date and place of the incident?', 'What items were seized and in what quantity?', 'Which officers or witnesses are mentioned?', 'What is the accused person’s previous criminal history?'],
    te: ['ఈ FIRలో వివరించిన సంఘటన ఏమిటి?', 'సంఘటన జరిగిన తేదీ మరియు స్థలం ఏమిటి?', 'ఏ వస్తువులు ఎంత పరిమాణంలో స్వాధీనం చేసుకున్నారు?'],
    hi: ['इस FIR में किस घटना का वर्णन है?', 'घटना की तारीख और स्थान क्या है?', 'कौन सी वस्तुएं कितनी मात्रा में ज़ब्त की गईं?'],
  },
  law: {
    en: ['Which legal provisions are mentioned in this FIR, and what do they say?', 'Which official provisions may be relevant to the recorded seizure?'],
    te: ['ఈ FIRలో పేర్కొన్న చట్ట నిబంధనలు ఏమిటి, అవి ఏమి చెబుతున్నాయి?'],
    hi: ['इस FIR में किन कानूनी प्रावधानों का उल्लेख है और वे क्या कहते हैं?'],
  },
  kb: {
    en: ['What is the punishment for theft under the Bharatiya Nyaya Sanhita?', 'What does Article 21 of the Constitution say?', 'What certificate is required for electronic records to be admissible?', 'Within what time must an arrested person be produced before a Magistrate?'],
    te: ['భారతీయ న్యాయ సంహిత ప్రకారం దొంగతనానికి శిక్ష ఏమిటి?', 'రాజ్యాంగంలోని ఆర్టికల్ 21 ఏమి చెబుతుంది?'],
    hi: ['भारतीय न्याय संहिता के तहत चोरी की सज़ा क्या है?', 'संविधान का अनुच्छेद 21 क्या कहता है?'],
  },
  all: {
    en: ['How many cases are registered in my jurisdiction?', 'Which records mention seized vehicles?'],
    te: ['నా అధికార పరిధిలో ఎన్ని కేసులు నమోదయ్యాయి?'],
    hi: ['मेरे अधिकार क्षेत्र में कितने मामले दर्ज हैं?'],
  },
};

const SOURCE_BADGE: Record<string, string> = {
  OFFICIAL: 'bg-emerald-50 text-emerald-800 border-emerald-300',
  SECONDARY: 'bg-sky-50 text-sky-800 border-sky-300',
  SYNTHETIC: 'bg-fuchsia-50 text-fuchsia-800 border-fuchsia-300',
  UNVERIFIED: 'bg-slate-50 text-slate-600 border-slate-300',
  CASE_RECORD: 'bg-blue-50 text-blue-800 border-blue-300',
};

const UI_TEXT: Record<Lang, { thinking: string; widen: (s: string) => string; quoted: string; legal: string; placeholder: string }> = {
  en: {
    thinking: 'Searching authorised documents and preparing a cited answer…',
    widen: (s) => `Search ${s} instead`,
    quoted: 'AI summary unavailable: matching passages are quoted directly.',
    legal: 'Decision support only. Verify against the official text before using any provision.',
    placeholder: 'Ask a question about the selected sources…',
  },
  te: {
    thinking: 'అధీకృత పత్రాలను శోధించి ఆధారాలతో సమాధానం సిద్ధం చేస్తోంది…',
    widen: (s) => `${s} పరిధిలో శోధించండి`,
    quoted: 'AI సారాంశం అందుబాటులో లేదు: సరిపోలిన భాగాలు యథాతథంగా ఇవ్వబడ్డాయి.',
    legal: 'ఇది నిర్ణయ సహాయం మాత్రమే. ఏ నిబంధననైనా ఉపయోగించే ముందు అధికారిక పాఠంతో సరిచూడండి.',
    placeholder: 'ఎంచుకున్న మూలాల గురించి ప్రశ్న అడగండి…',
  },
  hi: {
    thinking: 'अधिकृत दस्तावेज़ों में खोज कर संदर्भ सहित उत्तर तैयार किया जा रहा है…',
    widen: (s) => `${s} में खोजें`,
    quoted: 'AI सारांश उपलब्ध नहीं है: मेल खाने वाले अंश सीधे उद्धृत हैं।',
    legal: 'केवल निर्णय सहायता। किसी भी प्रावधान का उपयोग करने से पहले आधिकारिक पाठ से मिलान करें।',
    placeholder: 'चयनित स्रोतों के बारे में प्रश्न पूछें…',
  },
};

function isImageDoc(d: any): boolean {
  return Boolean(d?.is_image || d?.mime_type?.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(d?.original_filename || ''));
}

const CitationCard: React.FC<{ c: Citation; onOpen: (c: Citation) => void }> = ({ c, onOpen }) => {
  const [open, setOpen] = useState(false);
  const badge = SOURCE_BADGE[c.source_type || 'UNVERIFIED'] || SOURCE_BADGE.UNVERIFIED;
  return (
    <li className="border border-slate-200 rounded-lg bg-slate-50/60">
      <div className="flex items-start gap-2 px-2.5 py-2">
        {c.source_number !== undefined && (
          <span className="text-[10px] font-bold text-blue-700 bg-blue-50 border border-blue-200 rounded px-1.5 py-0.5 flex-shrink-0">S{c.source_number}</span>
        )}
        <div className="min-w-0 flex-1">
          <button onClick={() => onOpen(c)} className="text-[11px] font-semibold text-slate-800 hover:text-blue-700 hover:underline text-left">
            {c.document_name || c.source_label}
          </button>
          <div className="flex items-center gap-1.5 flex-wrap mt-0.5 text-[10px] text-slate-600">
            {c.section_ref && <span className="font-semibold text-indigo-700">{c.section_ref}</span>}
            <span>{c.is_image ? 'Image evidence' : c.physical_page_number ? `Page ${c.physical_page_number}` : ''}</span>
            {c.source_type && <span className={`px-1 rounded border ${badge}`}>{c.source_type === 'OFFICIAL' ? 'Official source' : c.source_type.replace(/_/g, ' ').toLowerCase()}</span>}
            {c.legal_status && <span className="text-slate-500">{c.legal_status.replace(/_/g, ' ').toLowerCase()}</span>}
            {c.fir_number && <span>FIR {c.fir_number}</span>}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {c.evidence_excerpt && (
            <button onClick={() => setOpen(!open)} className="text-slate-500 hover:text-slate-800 p-0.5" title={open ? 'Hide excerpt' : 'Show supporting excerpt'}>
              {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          )}
          {c.official_source_url && (
            <a href={c.official_source_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 p-0.5" title="Official source">
              <ShieldCheck className="w-3.5 h-3.5" />
            </a>
          )}
          {c.document_id && (
            <button onClick={() => onOpen(c)} className="text-blue-600 p-0.5" title={c.is_image ? 'Open image' : `Open page ${c.physical_page_number || 1}`}>
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
      {open && c.evidence_excerpt && (
        <blockquote className="mx-2.5 mb-2 px-2.5 py-1.5 border-l-2 border-blue-300 bg-white text-[11px] text-slate-700 leading-relaxed">“{c.evidence_excerpt}”</blockquote>
      )}
    </li>
  );
};

export const AIFIRAssistance: React.FC = () => {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();

  const [scope, setScope] = useState<Scope>('CURRENT_FIR');
  const [kbCategory, setKbCategory] = useState<string>('ALL');
  const [documents, setDocuments] = useState<any[]>([]);
  const [historicalFirs, setHistoricalFirs] = useState<any[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>('');
  const [chatLanguage, setChatLanguage] = useState<Lang>('en');
  const [hasSelectedLanguage, setHasSelectedLanguage] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'init-1',
      sender: 'ai',
      scope: 'CURRENT_FIR',
      text: 'Namaste Officer. I answer only from FIR VisionAI documents you are authorised to see, and every answer names its source document and page.\n\nChoose where to search with the tabs above: the current FIR, its whole case, the FIR together with the law, the Knowledge Base, or all records in your jurisdiction. If the selected sources do not contain the answer, I will say so instead of guessing.',
      citations: [],
    },
  ]);
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeViewerModal, setActiveViewerModal] = useState<{ docId: string; page: number } | null>(null);
  const [uploadingDoc, setUploadingDoc] = useState(false);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const ui = UI_TEXT[chatLanguage];

  const addMessage = (m: Omit<ChatMessage, 'id'>) =>
    setMessages((prev) => [...prev, { ...m, id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}` }]);

  const loadDocuments = async (preferId?: string) => {
    try {
      const [docsRes, histRes] = await Promise.all([
        api.get('/documents/', { params: { limit: 200 } }),
        api.get('/documents/historical-firs').catch(() => ({ data: { records: [] } })),
      ]);
      const docsList = Array.isArray(docsRes.data) ? docsRes.data : docsRes.data?.documents || [];
      const histList = histRes.data?.records || [];
      setDocuments(docsList);
      setHistoricalFirs(histList);
      const wanted = preferId || searchParams.get('docId');
      if (wanted && (docsList.some((d: any) => d.id === wanted) || histList.some((h: any) => (h.document_id || h.id) === wanted))) {
        setSelectedDocId(wanted);
      } else if (!selectedDocId) {
        if (histList.length > 0) setSelectedDocId(histList[0].document_id || histList[0].id);
        else if (docsList.length > 0) setSelectedDocId(docsList[0].id);
      }
    } catch (e) {
      setNotice('Could not load your documents. Refresh the page or sign in again.');
    }
  };

  useEffect(() => { loadDocuments(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [user]);
  // Scroll only the message list (scrollIntoView would also scroll the whole page)
  useEffect(() => {
    const el = messagesContainerRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const firDocuments = documents.filter((d) => d.doc_category === 'FIR' || d.doc_category === 'EVIDENCE' || !d.doc_category || d.case_id);
  const selectedDocObj =
    documents.find((d) => d.id === selectedDocId) ||
    historicalFirs.find((d) => (d.document_id || d.id) === selectedDocId);
  const selectedCaseId: string | null = selectedDocObj?.case_id || null;
  const scopeMeta = SCOPES.find((s) => s.key === scope)!;

  const handleSelectLanguage = (lang: Lang) => {
    setChatLanguage(lang);
    setHasSelectedLanguage(true);
    const confirmation: Record<Lang, string> = {
      en: 'Answers will be written in **English**.',
      te: 'సమాధానాలు **తెలుగు**లో ఇవ్వబడతాయి.',
      hi: 'उत्तर **हिन्दी** में दिए जाएंगे।',
    };
    addMessage({ sender: 'ai', text: confirmation[lang], scope });
  };

  const handleSelectDocument = (docId: string) => {
    setSelectedDocId(docId);
    const d = documents.find((x) => x.id === docId) || historicalFirs.find((x) => (x.document_id || x.id) === docId);
    const label = d?.display_label || d?.document_title || d?.original_filename || 'Record';
    setMessages([{
      id: `init-${docId}`,
      sender: 'ai',
      scope,
      text: isImageDoc(d)
        ? `Selected image evidence **${label}**. Answers cite the image itself; images have no page numbers.`
        : `Selected **${label}** (${d?.physical_page_count || 1} pages). Answers cite the exact page.`,
      citations: [],
    }]);
  };

  const handleClearChat = () => {
    setMessages([{ id: `reset-${Date.now()}`, sender: 'ai', scope, text: `Conversation cleared. Searching: ${SCOPE_LABEL[scope]}. ${SCOPE_DESCRIPTIONS[scope]}`, citations: [] }]);
  };

  // Upload a new FIR document; processing runs in the background, so poll until it finishes
  const handleDirectUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!/\.(pdf|jpe?g|png|webp)$/i.test(file.name)) {
      setNotice('Unsupported file type. Upload a PDF, JPEG, PNG or WEBP file.');
      return;
    }
    setUploadingDoc(true);
    setNotice(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await api.post('/documents/upload', fd);
      const { job_id: jobId, id: docId, status } = res.data;
      addMessage({ sender: 'ai', scope, text: `**${file.name}** uploaded. Extracting text and indexing…` });
      let finalStatus = status;
      if (status !== 'COMPLETED' && jobId) {
        for (let i = 0; i < 90; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          const js = await api.get(`/documents/jobs/${jobId}/status`).catch(() => null);
          const stage = js?.data?.stage;
          if (stage === 'COMPLETED' || stage === 'FAILED') { finalStatus = stage; break; }
        }
      }
      await loadDocuments(docId);
      setSelectedDocId(docId);
      const detail = await api.get(`/documents/${docId}/detail`, { params: { page_size: 1 } }).catch(() => null);
      const idx = detail?.data?.index_status;
      if (finalStatus === 'FAILED' || detail?.data?.status === 'FAILED') {
        addMessage({ sender: 'ai', scope, isError: true, text: `Processing of **${file.name}** failed: ${detail?.data?.error_message || 'unknown error'}. Open the Knowledge Base to retry.` });
      } else if (idx === 'NEEDS_REVIEW') {
        addMessage({ sender: 'ai', scope, isError: true, text: `No readable text could be extracted from **${file.name}** (OCR unavailable or failed), so it cannot be searched yet. Retry from the Knowledge Base once OCR is available.` });
      } else if (finalStatus === 'COMPLETED') {
        addMessage({ sender: 'ai', scope, text: `**${file.name}** is ready: ${detail?.data?.pages_with_text ?? '?'} page(s) with text, ${detail?.data?.chunk_count ?? '?'} searchable passages. Ask your questions below.` });
      } else {
        addMessage({ sender: 'ai', scope, text: `**${file.name}** is still processing. Its status is shown in the Knowledge Base; try your question again shortly.` });
      }
    } catch (err: any) {
      setNotice(`Upload failed: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setUploadingDoc(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const ask = async (question: string, askScope: Scope = scope) => {
    if (!question.trim()) return;
    const meta = SCOPES.find((s) => s.key === askScope)!;
    if (meta.needsDoc && !selectedDocId) {
      setNotice('Select an FIR document first.');
      return;
    }
    setNotice(null);
    addMessage({ sender: 'user', text: question, scope: askScope });
    setLoading(true);
    try {
      const payload: Record<string, any> = { query: question, scope: askScope, language: chatLanguage };
      if (meta.needsDoc) payload.document_id = selectedDocId;
      if (askScope === 'CASE' && selectedCaseId) payload.case_id = selectedCaseId;
      if (askScope === 'KNOWLEDGE_BASE' && kbCategory !== 'ALL') payload.categories = [kbCategory];
      const res = await api.post('/rag/query', payload);
      const d = res.data;
      addMessage({
        sender: 'ai',
        scope: askScope,
        text: d.answer,
        citations: d.citations || [],
        notFound: Boolean(d.not_found),
        suggestedScope: d.can_expand_scope ? d.suggested_scope : null,
        question,
        answerMethod: d.answer_method,
        legalMode: Boolean(d.legal_mode),
      });
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      addMessage({ sender: 'ai', scope: askScope, isError: true, text: `⚠️ ${typeof detail === 'string' ? detail : e.message}` });
    } finally {
      setLoading(false);
    }
  };

  const widenScope = (m: ChatMessage) => {
    if (!m.suggestedScope || !m.question) return;
    setScope(m.suggestedScope);
    ask(m.question, m.suggestedScope);
  };

  const openCitation = (c: Citation) => {
    const docId = c.document_id || selectedDocId;
    if (docId) setActiveViewerModal({ docId, page: c.is_image ? 1 : c.physical_page_number || 1 });
  };

  const suggestionSet = scope === 'KNOWLEDGE_BASE' ? 'kb' : scope === 'ALL_AUTHORIZED' ? 'all' : scope === 'FIR_AND_LAW' ? 'law' : 'fir';
  const suggestions = SUGGESTIONS[suggestionSet][chatLanguage];

  return (
    <div className="h-[calc(100vh-7.5rem)] flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="bg-slate-900 text-white p-4 border-b border-slate-800 flex flex-col xl:flex-row xl:items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-blue-600 rounded-lg"><BotMessageSquare className="w-5 h-5 text-white" /></div>
          <div>
            <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span>AI FIR Assistance</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">Cited answers only</span>
            </h2>
            <p className="text-xs text-slate-400">
              Your access: <span className="font-semibold text-emerald-400">{user?.role === 'STATE' ? 'Statewide' : user?.role === 'DISTRICT' ? `${user?.district} district` : `${user?.station || ''}`}</span>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center space-x-1 bg-slate-800 p-1 rounded-lg border border-slate-700 text-xs">
            <span className="text-slate-400 px-1 text-[11px] font-medium flex items-center gap-1"><Languages className="w-3.5 h-3.5 text-amber-300" /><span>Language:</span></span>
            {(['en', 'te', 'hi'] as Lang[]).map((l) => (
              <button key={l} type="button" onClick={() => handleSelectLanguage(l)}
                className={`px-2 py-0.5 rounded text-[11px] font-bold transition-all ${chatLanguage === l ? 'bg-blue-600 text-white shadow-xs' : 'text-slate-300 hover:text-white'}`}>
                {l === 'en' ? 'English' : l === 'te' ? 'తెలుగు' : 'हिन्दी'}
              </button>
            ))}
          </div>
          <div className="flex items-center flex-wrap bg-slate-800 p-1 rounded-lg border border-slate-700 text-xs" role="tablist" aria-label="Search scope">
            {SCOPES.map((s) => {
              const Icon = s.icon;
              return (
                <button key={s.key} role="tab" aria-selected={scope === s.key} onClick={() => setScope(s.key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold transition-all ${scope === s.key ? `${s.active} text-white shadow` : 'text-slate-400 hover:text-slate-200'}`}>
                  <Icon className="w-3.5 h-3.5" /><span>{s.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Scope bar */}
      <div className="bg-slate-50 border-b border-slate-200 px-6 py-2.5 flex flex-wrap items-center justify-between text-xs gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Shield className="w-4 h-4 text-blue-700 flex-shrink-0" />
          <span className="text-slate-700">{SCOPE_DESCRIPTIONS[scope]}</span>
        </div>
        <div className="flex items-center flex-wrap gap-2">
          {scopeMeta.needsDoc && (
            <>
              <select value={selectedDocId} onChange={(e) => handleSelectDocument(e.target.value)} aria-label="Selected FIR document"
                className="bg-white border border-blue-200 text-blue-950 font-medium px-3 py-1 rounded-md text-xs focus:ring-2 focus:ring-blue-500 max-w-md truncate">
                <option value="">— Choose an FIR document —</option>
                {historicalFirs.length > 0 && (
                  <optgroup label="FIR records">
                    {historicalFirs.map((hf) => <option key={hf.document_id || hf.id} value={hf.document_id || hf.id}>{hf.display_label}</option>)}
                  </optgroup>
                )}
                {firDocuments.length > 0 && (
                  <optgroup label="Uploaded case documents">
                    {firDocuments.map((d) => (
                      <option key={d.id} value={d.id}>{d.document_title || d.original_filename} ({isImageDoc(d) ? 'image' : `${d.physical_page_count || 1} pages`})</option>
                    ))}
                  </optgroup>
                )}
              </select>
              {scope === 'CASE' && selectedDocObj && (
                <span className="text-[11px] text-slate-600">
                  {selectedCaseId ? <>Case {selectedDocObj.fir_number ? `FIR ${selectedDocObj.fir_number}` : 'linked'}</> : 'Not linked to a case: this document only'}
                </span>
              )}
              {selectedDocObj && (
                <button onClick={() => setActiveViewerModal({ docId: selectedDocObj.document_id || selectedDocObj.id, page: 1 })} className="text-blue-800 underline hover:text-blue-950 font-semibold flex items-center gap-1 text-[11px]">
                  <ExternalLink className="w-3 h-3" /><span>Open document</span>
                </button>
              )}
              <input type="file" ref={fileInputRef} onChange={handleDirectUpload} accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden" />
              <button type="button" disabled={uploadingDoc} onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center gap-1.5 px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded-md font-semibold text-xs shadow-sm disabled:opacity-50">
                {uploadingDoc ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <UploadCloud className="w-3.5 h-3.5" />}
                <span>{uploadingDoc ? 'Processing…' : 'Upload FIR'}</span>
              </button>
            </>
          )}
          {scope === 'KNOWLEDGE_BASE' && (
            <div className="flex items-center gap-1.5 bg-white px-2.5 py-1 rounded border border-emerald-300">
              <span className="text-slate-600 font-semibold text-[11px]">Category:</span>
              <select value={kbCategory} onChange={(e) => setKbCategory(e.target.value)} aria-label="Knowledge Base category" className="bg-transparent text-xs text-emerald-950 font-bold focus:outline-none cursor-pointer">
                <option value="ALL">All Knowledge Base documents</option>
                <option value="LEGAL_ACT">Official Laws & Sections</option>
                <option value="CIRCULAR">Circulars & Orders</option>
                <option value="SEIZURE_REPORT">Seizure Reports</option>
                <option value="INVESTIGATION_GUIDE">Investigation Guides & SOPs</option>
                <option value="REFERENCE">Reference Materials</option>
                <option value="HISTORICAL_FIR">Historical FIR Records</option>
                <option value="EVIDENCE">Approved Evidence</option>
              </select>
            </div>
          )}
          <button type="button" onClick={handleClearChat} className="px-2 py-1 bg-white hover:bg-slate-100 border border-slate-300 rounded text-[11px] text-slate-600 font-medium">Clear chat</button>
        </div>
      </div>

      {notice && (
        <div className="px-6 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-900 flex items-center justify-between">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="text-amber-700 font-semibold">Dismiss</button>
        </div>
      )}

      {/* Messages */}
      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50/50">
        {!hasSelectedLanguage && (
          <div className="bg-gradient-to-r from-blue-50 via-indigo-50 to-emerald-50 border border-blue-200 rounded-2xl p-4 shadow-xs space-y-2.5 max-w-2xl">
            <div className="flex items-center space-x-2">
              <Languages className="w-4 h-4 text-blue-700" />
              <h3 className="text-xs font-bold text-blue-950 uppercase tracking-wide">Language Selection / భాష ఎంపిక / भाषा चयन</h3>
            </div>
            <p className="text-xs font-medium text-slate-800">Which language would you like the answers in?</p>
            <div className="flex flex-wrap gap-2 pt-1">
              {(['en', 'te', 'hi'] as Lang[]).map((l) => (
                <button key={l} type="button" onClick={() => handleSelectLanguage(l)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${chatLanguage === l ? 'bg-blue-600 text-white border-blue-700 shadow-xs' : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'}`}>
                  {l === 'en' ? 'English' : l === 'te' ? 'తెలుగు (Telugu)' : 'हिन्दी (Hindi)'}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => {
          const isUser = m.sender === 'user';
          return (
            <div key={m.id} className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
              {isUser && <span className="text-[10px] text-slate-400 mb-0.5">{SCOPE_LABEL[m.scope]}</span>}
              <div className={`max-w-2xl rounded-2xl p-4 shadow-sm text-xs leading-relaxed ${
                isUser ? 'bg-blue-600 text-white rounded-br-none'
                  : m.isError ? 'bg-amber-50 text-amber-900 border border-amber-200 rounded-bl-none'
                  : m.notFound ? 'bg-white text-slate-800 border border-slate-300 border-dashed rounded-bl-none'
                  : 'bg-white text-slate-800 border border-slate-200 rounded-bl-none'
              }`}>
                <div className="whitespace-pre-wrap font-sans">{m.text}</div>

                {!isUser && (m.answerMethod === 'EXTRACTIVE_QUOTES' || m.legalMode) && (
                  <div className="mt-2 space-y-1">
                    {m.answerMethod === 'EXTRACTIVE_QUOTES' && <p className="text-[10px] text-slate-500 flex items-center gap-1"><Info className="w-3 h-3" />{ui.quoted}</p>}
                    {m.legalMode && <p className="text-[10px] text-indigo-700 flex items-center gap-1"><Scale className="w-3 h-3" />{ui.legal}</p>}
                  </div>
                )}

                {!isUser && m.notFound && m.suggestedScope && (
                  <button onClick={() => widenScope(m)} disabled={loading}
                    className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-200 rounded-md text-[11px] font-semibold disabled:opacity-50">
                    <Search className="w-3.5 h-3.5" />{ui.widen(SCOPE_LABEL[m.suggestedScope])}
                  </button>
                )}

                {!isUser && m.citations && m.citations.length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-slate-100">
                    <p className="text-[11px] font-bold text-slate-500 mb-1.5">Sources ({m.citations.length})</p>
                    <ul className="space-y-1.5">
                      {m.citations.map((c, i) => <CitationCard key={`${c.document_id}-${c.source_number ?? i}`} c={c} onOpen={openCitation} />)}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex items-center space-x-2 text-xs text-slate-500 italic p-3 bg-white rounded-xl border border-slate-200 w-fit">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-600" /><span>{ui.thinking}</span>
          </div>
        )}
      </div>

      {/* Suggestions */}
      <div className="px-6 py-2 bg-white border-t border-slate-100 flex items-center gap-2 overflow-x-auto text-[11px]">
        <span className="text-slate-400 font-medium whitespace-nowrap">Try:</span>
        {suggestions.map((q) => (
          <button key={q} onClick={() => ask(q)} disabled={loading}
            className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full whitespace-nowrap disabled:opacity-50">
            {q}
          </button>
        ))}
      </div>

      {/* Input */}
      <form onSubmit={(e) => { e.preventDefault(); const q = queryInput; setQueryInput(''); ask(q); }} className="p-4 bg-white border-t border-slate-200 flex items-center space-x-3">
        <input
          id="ai-fir-question"
          type="text"
          value={queryInput}
          onChange={(e) => setQueryInput(e.target.value)}
          placeholder={`${ui.placeholder} (${SCOPE_LABEL[scope]})`}
          className="flex-1 text-xs border border-slate-300 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-2xs"
        />
        <button type="submit" disabled={loading || !queryInput.trim()}
          className="px-5 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center gap-1.5 disabled:opacity-50 transition-colors">
          <Send className="w-4 h-4" /><span>Send</span>
        </button>
      </form>

      {activeViewerModal && (
        <PDFViewerModal documentId={activeViewerModal.docId} initialPage={activeViewerModal.page} onClose={() => setActiveViewerModal(null)} />
      )}
    </div>
  );
};

export default AIFIRAssistance;

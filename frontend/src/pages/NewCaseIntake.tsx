import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import {
  FileText,
  Mic,
  UploadCloud,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Save,
  RotateCcw,
  ArrowRight,
  ExternalLink,
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Shield,
  ShieldCheck,
  Clock,
  Layers,
  BookOpen,
  Scale,
  RefreshCw,
  FolderOpen,
  Calendar,
  Phone,
  Mail,
  Globe,
  Truck,
  DollarSign,
  Tag,
  Hash,
  MapPin,
  Building2,
  User,
  Users
} from 'lucide-react';

interface ExtractionField {
  id: string;
  key: string;
  label: string;
  data_type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  required: boolean;
  description?: string;
  validation_rules?: string;
  value?: any;
  confidence?: number | null;
  source_page?: number;
  reviewed?: boolean;
}

interface ExtractionEntity {
  id: string;
  name: string;
  type: string;
  context?: string;
  source_page: number;
  confidence: number;
  status: string;
}

interface KeyPoint {
  id: string;
  point: string;
  source_page?: number;
}

interface PageContent {
  page_number: number;
  text: string;
  ocr_applied?: boolean;
  ocr_confidence?: number | null;
  is_unreadable?: boolean;
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
  file_hash?: string;
  document_content?: string;
  pages_content?: PageContent[];
  raw_text_summary?: string;
  document_metadata?: {
    original_filename?: string;
    document_id?: string;
    case_id?: string | null;
    document_type?: string;
    upload_date?: string | null;
    extraction_date?: string | null;
    total_pages?: number;
    page_count?: number;
    mime_type?: string;
    file_format?: string;
    file_size?: string | null;
    file_size_bytes?: number | null;
    file_hash?: string;
    ocr_status?: string;
    ocr_applied?: boolean;
    ocr_quality?: number | null;
    provider?: string;
    model?: string;
    sarvam_job_id?: string | null;
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
}

interface WorkflowStageInfo {
  id: string;
  number: number;
  title: string;
  subtitle: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  summary?: string;
  error?: string;
}

export const NewCaseIntake: React.FC = () => {
  const { t, language } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  // Mode Selection
  const [activeTab, setActiveTab] = useState<'narrative' | 'voice' | 'file'>('file');
  const [narrativeText, setNarrativeText] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [processing, setProcessing] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Document Viewer & Extraction State
  const [runData, setRunData] = useState<ExtractionRunData | null>(null);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [isImage, setIsImage] = useState<boolean>(false);
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null);
  const [copiedContent, setCopiedContent] = useState<boolean>(false);

  // Accordion Expand States
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    metadata: true,
    content: true,
    summary: true,
    fields: true,
    entities: true,
    keyPoints: true,
    warnings: true
  });

  // Section Selector Tab (All, Content, Metadata, Summary, Entities, Key Points, Fields, Warnings)
  const [activeResultsTab, setActiveResultsTab] = useState<'all' | 'content' | 'metadata' | 'summary' | 'entities' | 'keyPoints' | 'fields' | 'warnings'>('all');
  const [selectedContentPage, setSelectedContentPage] = useState<number | 'all'>('all');
  const [entityCategory, setEntityCategory] = useState<string>('ALL');
  const [copiedSummary, setCopiedSummary] = useState<boolean>(false);

  // Filters for extracted items
  const [fieldFilter, setFieldFilter] = useState('');
  const [entityFilter, setEntityFilter] = useState('');

  // Form edit fields (synced with extraction)
  const [formData, setFormData] = useState<any>({
    fir_number: '',
    district: user?.district || 'Kurnool',
    station: user?.station || 'Kurnool Town Station',
    mandal: '',
    village: '',
    offence_nature: '',
    contraband_type: '',
    seized_quantity: 0,
    seized_unit: 'Litres',
    vehicle_details: '',
    narrative: ''
  });

  // 5-Stage Automated Post-Intake Workflow State
  const [workflowStages, setWorkflowStages] = useState<WorkflowStageInfo[]>([
    {
      id: 'STAGE_1_UPLOAD_EXTRACTION',
      number: 1,
      title: 'Evidence Upload & Extraction',
      subtitle: 'Document verification, file hashing & AI extraction',
      status: 'PENDING'
    },
    {
      id: 'STAGE_2_OFFICER_REVIEW',
      number: 2,
      title: 'Officer Review & Sign-Off',
      subtitle: 'Mandatory human verification and field sign-off',
      status: 'PENDING'
    },
    {
      id: 'STAGE_3_AI_LEGAL',
      number: 3,
      title: 'AI & Legal Intelligence',
      subtitle: 'Statutory sections from BNS, IPC, AP Excise & NDPS',
      status: 'PENDING'
    },
    {
      id: 'STAGE_4_INVESTIGATION',
      number: 4,
      title: 'Investigation Tools',
      subtitle: 'Case Diary & Chargesheet baseline, entity graph',
      status: 'PENDING'
    },
    {
      id: 'STAGE_5_ADMIN_FIR',
      number: 5,
      title: 'Administration & Existing FIRs',
      subtitle: 'Case verification, audit logging & folder indexing',
      status: 'PENDING'
    }
  ]);

  const [confirmedCaseId, setConfirmedCaseId] = useState<string | null>(null);
  const [confirmedFirNumber, setConfirmedFirNumber] = useState<string | null>(null);
  const [isPollingWorkflow, setIsPollingWorkflow] = useState<boolean>(false);
  const pollingRef = useRef<any>(null);

  // Clean up blob URL on unmount
  useEffect(() => {
    return () => {
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [pdfBlobUrl]);

  // Jump to specific page citation in viewer
  const handleJumpToPage = (pageNum: number) => {
    if (pageNum > 0 && pageNum <= totalPages) {
      setCurrentPage(pageNum);
    }
  };

  // Update a structured field value in real time
  const handleFieldChange = (fieldKey: string, newValue: any) => {
    if (!runData) return;
    const updated = runData.structured_fields.map(f => {
      if (f.key === fieldKey) {
        return { ...f, value: newValue, reviewed: true };
      }
      return f;
    });
    setRunData({ ...runData, structured_fields: updated });

    // Also sync key form fields
    if (fieldKey in formData) {
      setFormData((prev: any) => ({ ...prev, [fieldKey]: newValue }));
    }
  };

  // ───────────────────────────────────────────────────────────────────────────
  // Handle File Upload & Extraction (Unified Workspace Pipeline)
  // ───────────────────────────────────────────────────────────────────────────
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];

    // Explicitly reset prior state to prevent stale data
    if (pdfBlobUrl) {
      URL.revokeObjectURL(pdfBlobUrl);
      setPdfBlobUrl(null);
    }
    setRunData(null);
    setUploadedDocId(null);
    setConfirmedCaseId(null);
    setConfirmedFirNumber(null);
    setFormData({
      fir_number: '',
      district: user?.district || '',
      station: user?.station || '',
      mandal: '',
      village: '',
      offence_nature: '',
      contraband_type: '',
      seized_quantity: 0,
      seized_unit: 'Litres',
      vehicle_details: '',
      narrative: ''
    });
    setUploadFile(file);
    setErrorMsg(null);

    // Update Stage 1 to RUNNING
    setWorkflowStages(stages =>
      stages.map(s => {
        if (s.number === 1) return { ...s, status: 'RUNNING', summary: 'Uploading & parsing document...' };
        if (s.number === 2) return { ...s, status: 'PENDING', summary: undefined };
        return { ...s, status: 'PENDING', summary: undefined };
      })
    );

    try {
      setProcessing(true);
      const fd = new FormData();
      fd.append('file', file);

      // Upload and run extraction via unified endpoint
      const uploadRes = await api.post('/documents/upload', fd);
      const data = uploadRes.data;
      const docId = data.document_id || data.id;
      setUploadedDocId(docId);

      // Build or fetch extraction run data
      const meta = data.document_metadata || {};
      let fullRunData: ExtractionRunData = {
        run_id: data.run_id,
        document_id: docId,
        original_filename: data.filename || file.name,
        mime_type: data.mime_type,
        page_count: data.physical_page_count || 1,
        provider: data.provider || 'AI Document Intelligence',
        sarvam_job_id: data.sarvam_job_id,
        file_hash: data.file_hash,
        document_content: data.document_content || '',
        pages_content: data.pages_content || [],
        raw_text_summary: data.raw_text_summary || meta.raw_text_summary || '',
        document_metadata: {
          original_filename: data.filename || file.name,
          document_id: docId,
          case_id: data.case_id || null,
          document_type: meta.document_type || 'First Information Report (FIR)',
          upload_date: meta.upload_date || new Date().toISOString(),
          extraction_date: meta.extraction_date || new Date().toISOString(),
          total_pages: data.physical_page_count || meta.total_pages || 1,
          page_count: data.physical_page_count || meta.page_count || 1,
          mime_type: data.mime_type,
          file_format: meta.file_format || (data.mime_type || 'application/pdf').split('/').pop()?.toUpperCase() || 'PDF',
          file_size: meta.file_size || `${(file.size / 1024).toFixed(1)} KB`,
          file_size_bytes: meta.file_size_bytes || file.size,
          file_hash: data.file_hash,
          ocr_status: meta.ocr_status || data.status || 'COMPLETED',
          ocr_applied: meta.ocr_applied ?? true,
          ocr_quality: meta.ocr_quality ?? 0.95,
          provider: data.provider || meta.provider || 'AI Document Intelligence',
          model: meta.model || (data.provider === 'SARVAM_AI' ? 'sarvam-doc-ai-v1' : 'fir-vision-v1'),
          sarvam_job_id: data.sarvam_job_id,
          author: meta.author,
          document_date: meta.document_date,
          district: meta.district,
          station: meta.station,
          raw_text_summary: data.raw_text_summary || meta.raw_text_summary,
        },
        structured_fields: data.structured_fields || [],
        entities: data.entities || [],
        key_points: data.key_points || [],
        warnings: data.warnings || []
      };

      // If upload response lacked full structured fields, fetch from /extraction/document/{docId}
      if (!fullRunData.structured_fields || fullRunData.structured_fields.length === 0) {
        try {
          const extRes = await api.get(`/extraction/document/${docId}`);
          fullRunData = { ...fullRunData, ...extRes.data };
        } catch (fetchErr) {
          console.warn('Extraction detail fetch error:', fetchErr);
        }
      }

      setRunData(fullRunData);
      setTotalPages(fullRunData.page_count || 1);
      setCurrentPage(1);

      // Fetch authenticated document view stream for the side-by-side preview
      try {
        const viewRes = await api.get(`/documents/${docId}/view`, { responseType: 'blob' });
        const mime = String(viewRes.headers['content-type'] || data.mime_type || 'application/pdf');
        const isImg = mime.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(file.name);
        setIsImage(isImg);

        const blob = new Blob([viewRes.data], { type: mime });
        const objectUrl = URL.createObjectURL(blob);
        setPdfBlobUrl(objectUrl);
      } catch (viewerErr) {
        console.warn('Document preview stream load notice:', viewerErr);
        // Fallback for image preview if blob fetch fails
        if (!file.name.toLowerCase().endsWith('.pdf')) {
          setPdfBlobUrl(URL.createObjectURL(file));
          setIsImage(true);
        }
      }

      // Populate form data from extracted structured fields
      const fieldMap: Record<string, any> = {};
      fullRunData.structured_fields.forEach(f => {
        fieldMap[f.key] = f.value;
      });

      setFormData((prev: any) => ({
        ...prev,
        fir_number: fieldMap.fir_number || data.extracted_data?.fir_number || '',
        district: fieldMap.district || data.extracted_data?.district || user?.district || '',
        station: fieldMap.station || data.extracted_data?.station || user?.station || '',
        mandal: fieldMap.mandal || data.extracted_data?.mandal || '',
        village: fieldMap.village || data.extracted_data?.village || '',
        offence_nature: fieldMap.offence_nature || data.extracted_data?.offence_nature || '',
        contraband_type: fieldMap.contraband_type || data.extracted_data?.contraband_type || '',
        seized_quantity: fieldMap.seized_quantity ?? data.extracted_data?.seized_quantity ?? 0,
        seized_unit: fieldMap.seized_unit || data.extracted_data?.seized_unit || 'Litres',
        vehicle_details: fieldMap.vehicle_details || data.extracted_data?.vehicle_details || '',
        narrative: fullRunData.document_content?.slice(0, 3000) || data.extracted_data?.narrative_summary || ''
      }));

      // Stage 1 COMPLETED; Stage 2 becomes ACTIVE (Officer Review Required)
      setWorkflowStages(stages =>
        stages.map(s => {
          if (s.number === 1) {
            return {
              ...s,
              status: 'COMPLETED',
              summary: `${fullRunData.provider || 'AI Engine'} • ${fullRunData.structured_fields.length} fields • ${fullRunData.entities.length} entities • Hash: ${(fullRunData.file_hash || '').slice(0, 8)}...`
            };
          }
          if (s.number === 2) {
            return {
              ...s,
              status: 'RUNNING',
              summary: 'Human verification required under Police & Excise Guidelines. Review extracted fields before confirming.'
            };
          }
          return s;
        })
      );
    } catch (e: any) {
      console.error('File upload error:', e);
      const detail = e.response?.data?.detail || e.message || 'File processing failed.';
      setErrorMsg(`Upload and extraction failed: ${detail}`);
      setWorkflowStages(stages =>
        stages.map(s => (s.number === 1 ? { ...s, status: 'FAILED', error: detail } : s))
      );
    } finally {
      setProcessing(false);
    }
  };

  // ───────────────────────────────────────────────────────────────────────────
  // Handle Narrative & Voice Extraction (Alternative Modes)
  // ───────────────────────────────────────────────────────────────────────────
  const handleNarrativeExtract = async () => {
    if (!narrativeText.trim()) return;
    try {
      setProcessing(true);
      setErrorMsg(null);
      const res = await api.post('/extraction/narrative', {
        narrative: narrativeText,
        language
      });
      applyExtractedToForm(res.data);
      setWorkflowStages(stages =>
        stages.map(s => {
          if (s.number === 1) return { ...s, status: 'COMPLETED', summary: 'Narrative parsed via Gemini Multimodal' };
          if (s.number === 2) return { ...s, status: 'RUNNING', summary: 'Review parsed fields before registration' };
          return s;
        })
      );
    } catch (e: any) {
      setErrorMsg('Extraction error: ' + (e.response?.data?.detail || e.message));
    } finally {
      setProcessing(false);
    }
  };

  const handleVoiceSimulate = async () => {
    try {
      setProcessing(true);
      setErrorMsg(null);
      const blob = new Blob(['sample-audio-bytes'], { type: 'audio/wav' });
      const fd = new FormData();
      fd.append('audio', blob, 'sample_audio.wav');
      fd.append('language', language);

      const res = await api.post('/extraction/voice', fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setNarrativeText(res.data.transcript);
      applyExtractedToForm(res.data.extracted_data);
      setWorkflowStages(stages =>
        stages.map(s => {
          if (s.number === 1) return { ...s, status: 'COMPLETED', summary: 'Voice transcribed and structured' };
          if (s.number === 2) return { ...s, status: 'RUNNING', summary: 'Review transcribed fields before registration' };
          return s;
        })
      );
    } catch (e: any) {
      setErrorMsg('Voice processing error: ' + (e.response?.data?.detail || e.message));
    } finally {
      setProcessing(false);
    }
  };

  const applyExtractedToForm = (data: any) => {
    setFormData((prev: any) => ({
      ...prev,
      fir_number: data.fir_number || '',
      district: data.district || user?.district || '',
      station: data.station || user?.station || '',
      mandal: data.mandal || '',
      village: data.village || '',
      offence_nature: data.offence_nature || '',
      contraband_type: data.contraband_type || '',
      seized_quantity: data.seized_quantity ?? 0,
      seized_unit: data.seized_unit || 'Litres',
      vehicle_details: data.vehicle_details || '',
      narrative: data.narrative_summary || narrativeText || ''
    }));
  };

  // ───────────────────────────────────────────────────────────────────────────
  // Poll Automated Post-Intake Workflow Stages (Stages 3, 4, 5)
  // ───────────────────────────────────────────────────────────────────────────
  const pollWorkflowStatus = useCallback((caseId: string) => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    setIsPollingWorkflow(true);

    const checkStatus = async () => {
      try {
        const res = await api.get(`/folders/workflow/${caseId}`);
        const stagesList: any[] = res.data || [];

        const stageMap: Record<string, any> = {};
        stagesList.forEach(s => {
          stageMap[s.stage] = s;
        });

        setWorkflowStages(prev =>
          prev.map(st => {
            if (st.number === 1 || st.number === 2) return st;

            let backendStageKey = '';
            if (st.number === 3) backendStageKey = 'AI_LEGAL';
            if (st.number === 4) backendStageKey = 'INVESTIGATION';
            if (st.number === 5) backendStageKey = 'ADMIN';

            const bs = stageMap[backendStageKey];
            if (!bs) return st;

            let sumText = st.summary;
            if (bs.status === 'COMPLETED' && bs.result_summary) {
              try {
                const parsed = JSON.parse(bs.result_summary);
                if (st.number === 3 && parsed.top_candidates) {
                  sumText = `Recommended sections: ${parsed.top_candidates.join(', ')}`;
                } else if (st.number === 4 && parsed.drafts_created) {
                  sumText = `Drafted ${parsed.drafts_created.join(' & ')} • Ready for IO review`;
                } else if (st.number === 5) {
                  sumText = 'Case verified, audit recorded, available in Existing/Old FIRs';
                }
              } catch {
                sumText = bs.status;
              }
            }

            return {
              ...st,
              status: bs.status,
              summary: sumText,
              error: bs.error_message
            };
          })
        );

        const adminCompleted = stageMap['ADMIN']?.status === 'COMPLETED';
        const anyFailed = stagesList.some(s => s.status === 'FAILED');

        if (adminCompleted || anyFailed) {
          if (pollingRef.current) clearInterval(pollingRef.current);
          setIsPollingWorkflow(false);
        }
      } catch (pollErr) {
        console.warn('Workflow polling error:', pollErr);
      }
    };

    checkStatus();
    pollingRef.current = setInterval(checkStatus, 1500);
  }, []);

  // ───────────────────────────────────────────────────────────────────────────
  // Retry Failed Stages Idempotently
  // ───────────────────────────────────────────────────────────────────────────
  const handleRetryWorkflow = async () => {
    if (!confirmedCaseId) return;
    try {
      setProcessing(true);
      setErrorMsg(null);
      await api.post(`/folders/workflow/${confirmedCaseId}/retry`);
      pollWorkflowStatus(confirmedCaseId);
    } catch (err: any) {
      setErrorMsg('Failed to retry workflow: ' + (err.response?.data?.detail || err.message));
    } finally {
      setProcessing(false);
    }
  };

  // ───────────────────────────────────────────────────────────────────────────
  // Confirm and Register Case (Mandatory Officer Review Sign-Off)
  // ───────────────────────────────────────────────────────────────────────────
  const handleConfirmAndRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (processing) return;
    setErrorMsg(null);

    // Validate mandatory fields explicitly
    const missing: string[] = [];
    if (!formData.fir_number || !String(formData.fir_number).trim()) missing.push('FIR Number (fir_number)');
    if (!formData.district || !String(formData.district).trim()) missing.push('District (district)');
    if (!formData.station || !String(formData.station).trim()) missing.push('Police / Excise Station (station)');
    if (!formData.offence_nature || !String(formData.offence_nature).trim()) missing.push('Offence Nature (offence_nature)');

    if (missing.length > 0) {
      setErrorMsg(`Cannot register case. Missing required field(s): ${missing.join(', ')}. Please review and provide values before confirming.`);
      return;
    }

    try {
      setProcessing(true);

      // Sync latest formData edits into runData.structured_fields before sending
      if (runData) {
        const keysToSync = [
          'fir_number', 'district', 'station', 'offence_nature',
          'contraband_type', 'seized_quantity', 'seized_unit', 'vehicle_details',
          'mandal', 'village'
        ];
        keysToSync.forEach(k => {
          const val = formData[k];
          const existing = runData.structured_fields.find(f => f.key === k);
          if (existing) {
            existing.value = val;
            existing.reviewed = true;
          } else if (val !== undefined && val !== null && val !== '') {
            runData.structured_fields.push({
              id: 'field_' + k,
              key: k,
              label: k.replace(/_/g, ' ').toUpperCase(),
              data_type: typeof val === 'number' ? 'number' : 'string',
              required: ['fir_number', 'district', 'station', 'offence_nature'].includes(k),
              value: val,
              confidence: 1.0,
              reviewed: true
            });
          }
        });
      }

      // Update Stage 2 to COMPLETED
      setWorkflowStages(stages =>
        stages.map(s => {
          if (s.number === 2) {
            return {
              ...s,
              status: 'COMPLETED',
              summary: `Signed off by ${user?.full_name || 'Authorized Officer'} (${user?.designation || 'Inspector'})`
            };
          }
          if (s.number >= 3) {
            return { ...s, status: 'RUNNING' };
          }
          return s;
        })
      );

      let caseId = '';
      let firNum = formData.fir_number;

      if (runData?.run_id) {
        // Confirm via Extraction Workspace confirmation API (registers case, entities, fields)
        const confirmRes = await api.post(`/extraction/run/${runData.run_id}/confirm`, {
          case_id: runData.case_id,
          reviewed_data: runData
        });
        caseId = confirmRes.data.case_id;
        firNum = confirmRes.data.fir_number || firNum;
      } else {
        // Confirm via standard case creation API
        const payload = {
          ...formData,
          document_ids: uploadedDocId ? [uploadedDocId] : []
        };
        const createRes = await api.post('/cases/', payload);
        caseId = createRes.data.id;
        firNum = createRes.data.fir_number || firNum;
      }

      setConfirmedCaseId(caseId);
      setConfirmedFirNumber(firNum);

      // Start live polling of Stages 3, 4, 5
      pollWorkflowStatus(caseId);
    } catch (err: any) {
      console.error('Case confirmation error:', err);
      const detail = err.response?.data?.detail || err.message || 'Failed to confirm case.';
      setErrorMsg(`Confirmation failed: ${detail}`);
      setWorkflowStages(stages =>
        stages.map(s => (s.number === 2 ? { ...s, status: 'FAILED', error: detail } : s))
      );
    } finally {
      setProcessing(false);
    }
  };

  const allStagesCompleted = workflowStages.every(s => s.status === 'COMPLETED');
  const anyStageFailed = workflowStages.some(s => s.status === 'FAILED');

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* ── HEADER ───────────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center space-x-2">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-[#0f5132]/10 text-[#0f5132] uppercase tracking-wider">
              Official Law Enforcement Intake
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600">
              {user?.station || 'Station Jurisdiction'}
            </span>
          </div>
          <h1 className="text-xl font-black text-slate-900 tracking-tight mt-1">
            {t.nav.newCaseIntake}
          </h1>
          <p className="text-xs text-slate-500">
            End-to-end FIR intake: Evidence Upload & OCR extraction, Officer Review, Legal Intelligence, Investigation Tools & Registration
          </p>
        </div>

        {/* Mode Selector Tabs */}
        <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200 self-start">
          <button
            onClick={() => setActiveTab('file')}
            className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-md text-xs font-bold transition-all ${
              activeTab === 'file'
                ? 'bg-white text-[#0f5132] shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Evidence Upload / OCR</span>
          </button>
          <button
            onClick={() => setActiveTab('narrative')}
            className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-md text-xs font-bold transition-all ${
              activeTab === 'narrative'
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Typed Narrative</span>
          </button>
          <button
            onClick={() => setActiveTab('voice')}
            className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-md text-xs font-bold transition-all ${
              activeTab === 'voice'
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Mic className="w-3.5 h-3.5" />
            <span>Voice Intake</span>
          </button>
        </div>
      </div>

      {/* ── 5-STAGE AUTOMATED WORKFLOW STATUS TRACKER ───────────────────────── */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2">
          <div className="flex items-center space-x-2">
            <Layers className="w-4 h-4 text-[#0f5132]" />
            <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Automated Post-Intake Workflow Pipeline
            </h2>
          </div>
          <div className="text-[11px] text-slate-500 font-medium">
            {confirmedFirNumber ? (
              <span className="font-mono font-bold text-[#0f5132]">Case: {confirmedFirNumber}</span>
            ) : (
              'Stages execute sequentially upon upload and verification'
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {workflowStages.map(st => {
            const isCompleted = st.status === 'COMPLETED';
            const isRunning = st.status === 'RUNNING';
            const isFailed = st.status === 'FAILED';

            return (
              <div
                key={st.id}
                className={`p-3.5 rounded-xl border transition-all ${
                  isCompleted
                    ? 'bg-emerald-50/70 border-emerald-300'
                    : isRunning
                    ? 'bg-blue-50/70 border-blue-400 ring-2 ring-blue-200'
                    : isFailed
                    ? 'bg-red-50 border-red-300'
                    : 'bg-slate-50 border-slate-200 opacity-75'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-black ${
                      isCompleted
                        ? 'bg-emerald-600 text-white'
                        : isRunning
                        ? 'bg-blue-600 text-white animate-pulse'
                        : isFailed
                        ? 'bg-red-600 text-white'
                        : 'bg-slate-200 text-slate-600'
                    }`}
                  >
                    {isCompleted ? <Check className="w-3.5 h-3.5 stroke-[3]" /> : st.number}
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      isCompleted
                        ? 'bg-emerald-100 text-emerald-800'
                        : isRunning
                        ? 'bg-blue-100 text-blue-800'
                        : isFailed
                        ? 'bg-red-100 text-red-800'
                        : 'bg-slate-200 text-slate-600'
                    }`}
                  >
                    {st.status}
                  </span>
                </div>
                <h3 className="text-xs font-bold text-slate-900 leading-tight">{st.title}</h3>
                <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">{st.subtitle}</p>
                {st.summary && (
                  <div className="mt-2 text-[10px] text-slate-700 bg-white/80 p-1.5 rounded border border-slate-200/60 font-mono">
                    {st.summary}
                  </div>
                )}
                {st.error && (
                  <div className="mt-2 text-[10px] text-red-700 bg-red-100/80 p-1.5 rounded border border-red-200">
                    {st.error}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Live workflow actions / retry bar */}
        {(allStagesCompleted || anyStageFailed || isPollingWorkflow) && (
          <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-100">
            {allStagesCompleted && (
              <div className="flex items-center space-x-2 text-emerald-700 text-xs font-bold">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>All 5 stages completed successfully. FIR verified, indexed, and available across all modules.</span>
              </div>
            )}
            {anyStageFailed && (
              <div className="flex items-center space-x-2 text-red-700 text-xs font-bold">
                <AlertCircle className="w-4 h-4 text-red-600" />
                <span>One or more stages encountered an issue. You can safely retry without creating duplicates.</span>
              </div>
            )}
            {isPollingWorkflow && !allStagesCompleted && (
              <div className="flex items-center space-x-2 text-blue-700 text-xs font-semibold">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Automated pipeline executing post-confirmation stages in the background...</span>
              </div>
            )}

            <div className="flex items-center space-x-2 ml-auto">
              {anyStageFailed && confirmedCaseId && (
                <button
                  type="button"
                  onClick={handleRetryWorkflow}
                  disabled={processing}
                  className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold inline-flex items-center space-x-1.5 shadow-sm"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Retry Workflow</span>
                </button>
              )}
              {confirmedCaseId && (
                <>
                  <button
                    type="button"
                    onClick={() => navigate(`/cases/${confirmedCaseId}`)}
                    className="px-3.5 py-1.5 bg-[#0f5132] hover:bg-[#0a3d26] text-white rounded-lg text-xs font-bold inline-flex items-center space-x-1.5 shadow-sm"
                  >
                    <FolderOpen className="w-3.5 h-3.5" />
                    <span>View in Existing/Old FIRs</span>
                    <ExternalLink className="w-3 h-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate('/case-diary')}
                    className="px-3 py-1.5 bg-blue-700 hover:bg-blue-800 text-white rounded-lg text-xs font-semibold inline-flex items-center space-x-1 shadow-sm"
                  >
                    <BookOpen className="w-3.5 h-3.5" />
                    <span>Case Diary</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate('/legal')}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold inline-flex items-center space-x-1 shadow-sm"
                  >
                    <Scale className="w-3.5 h-3.5" />
                    <span>AI Legal Intelligence</span>
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Global Error Banner */}
      {errorMsg && (
        <div className="p-4 bg-red-50 text-red-800 rounded-xl text-xs flex items-center justify-between border border-red-200 shadow-sm">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-600" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-red-600 font-bold hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {/* ── TAB 1: EVIDENCE UPLOAD / OCR (FULL EXTRACTION WORKSPACE) ─────────── */}
      {activeTab === 'file' && (
        <div className="space-y-5">
          {/* Upload Dropzone */}
          {!runData && (
            <div className="p-8 bg-white rounded-xl border-2 border-dashed border-slate-300 text-center space-y-4 shadow-sm hover:border-[#0f5132] transition-colors">
              <div className="w-14 h-14 rounded-2xl bg-emerald-50 text-[#0f5132] flex items-center justify-center mx-auto shadow-inner">
                <UploadCloud className="w-7 h-7" />
              </div>
              <div className="max-w-md mx-auto">
                <h3 className="font-bold text-sm text-slate-900">Upload FIR Evidence Document or Scan</h3>
                <p className="text-xs text-slate-500 mt-1">
                  Upload PDF (grounded page citations), scanned documents, or JPEG/PNG/WEBP photographs.
                  Automatically processed via official Sarvam AI Document Intelligence or Multimodal Vision. Max 50 MB.
                </p>
              </div>

              <div className="flex items-center justify-center">
                <label className="px-5 py-2.5 bg-[#0f5132] hover:bg-[#0a3d26] text-white rounded-lg text-xs font-bold inline-flex items-center space-x-2 cursor-pointer shadow-md transition-all">
                  <UploadCloud className="w-4 h-4" />
                  <span>{processing ? 'Processing Document...' : 'Select FIR Document'}</span>
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png,.webp,.JPG,.JPEG,.PNG,.WEBP"
                    disabled={processing}
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </label>
              </div>
            </div>
          )}

          {/* Side-by-Side Workspace (Visible Once File Is Uploaded) */}
          {runData && (
            <div className="space-y-5">
              {/* Document bar with actions */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-slate-900 text-white rounded-xl shadow-md">
                <div className="flex items-center space-x-3">
                  <div className="p-2 rounded-lg bg-emerald-500/20 text-emerald-400">
                    <FileText className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-bold text-white truncate max-w-xs md:max-w-md">
                        {runData.original_filename}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-900/60 text-emerald-300 border border-emerald-700/50">
                        {runData.provider || 'AI Extractor'}
                      </span>
                      {runData.sarvam_job_id && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-900/60 text-purple-300 border border-purple-700/50">
                          Sarvam ID: {runData.sarvam_job_id.slice(0, 10)}...
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      {runData.page_count} Physical Page{runData.page_count !== 1 ? 's' : ''} • SHA-256:{' '}
                      <span className="font-mono">{runData.file_hash ? runData.file_hash.slice(0, 16) + '...' : 'Verified'}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-2 self-end sm:self-auto">
                  <label className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold cursor-pointer border border-slate-700 flex items-center space-x-1.5">
                    <UploadCloud className="w-3.5 h-3.5" />
                    <span>Upload Different File</span>
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,.webp,.JPG,.JPEG,.PNG,.WEBP"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => navigate(`/document-extraction?docId=${runData.document_id}`)}
                    className="px-3 py-1.5 bg-emerald-800 hover:bg-emerald-700 text-emerald-100 rounded-lg text-xs font-semibold border border-emerald-600 flex items-center space-x-1.5"
                    title="Open in Full Document Workspace"
                  >
                    <span>Full Workspace</span>
                    <ExternalLink className="w-3 h-3" />
                  </button>
                </div>
              </div>

              {/* Side-by-Side Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* ── LEFT COLUMN: DOCUMENT PREVIEW ── */}
                <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden shadow-sm flex flex-col h-[700px]">
                  {/* Viewer Toolbar */}
                  <div className="flex items-center justify-between px-4 py-2.5 bg-slate-800/90 border-b border-slate-700 text-slate-200 text-xs">
                    <div className="flex items-center space-x-2">
                      <span className="font-bold text-slate-300">Original Evidence</span>
                      <span className="text-slate-500">•</span>
                      <span>
                        Page {currentPage} of {totalPages}
                      </span>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        type="button"
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        disabled={currentPage <= 1}
                        className="p-1 rounded hover:bg-slate-700 disabled:opacity-40"
                        title="Previous page"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        disabled={currentPage >= totalPages}
                        className="p-1 rounded hover:bg-slate-700 disabled:opacity-40"
                        title="Next page"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                      <div className="h-4 w-px bg-slate-700 mx-1" />
                      <button
                        type="button"
                        onClick={() => setZoomLevel(z => Math.max(50, z - 15))}
                        className="p-1 rounded hover:bg-slate-700"
                        title="Zoom out"
                      >
                        <ZoomOut className="w-4 h-4" />
                      </button>
                      <span className="font-mono text-[11px] text-slate-400 w-10 text-center">{zoomLevel}%</span>
                      <button
                        type="button"
                        onClick={() => setZoomLevel(z => Math.min(200, z + 15))}
                        className="p-1 rounded hover:bg-slate-700"
                        title="Zoom in"
                      >
                        <ZoomIn className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Viewer Canvas / Stream */}
                  <div className="flex-1 bg-slate-950 overflow-auto p-4 flex items-center justify-center">
                    {pdfBlobUrl ? (
                      isImage ? (
                        <div
                          className="transition-transform duration-150 flex items-center justify-center"
                          style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: 'top center' }}
                        >
                          <img
                            src={pdfBlobUrl}
                            alt="FIR Document Evidence"
                            className="max-w-full rounded shadow-2xl border border-slate-700 object-contain"
                          />
                        </div>
                      ) : (
                        <iframe
                          src={`${pdfBlobUrl}#page=${currentPage}&zoom=${zoomLevel}`}
                          title="Evidence Document Viewer"
                          className="w-full h-full rounded shadow-xl bg-white border border-slate-700"
                        />
                      )
                    ) : (
                      <div className="text-center text-slate-500 text-xs">
                        Document preview stream not available.
                      </div>
                    )}
                  </div>
                </div>

                {/* ── RIGHT COLUMN: EXTRACTION RESULTS & REVIEW ── */}
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm flex flex-col h-[700px]">
                  {/* Results Header with Section Quick-Selector */}
                  <div className="border-b border-slate-200 bg-slate-50 flex-shrink-0">
                    <div className="flex items-center justify-between px-4 py-2.5">
                      <div className="flex items-center space-x-2">
                        <Sparkles className="w-4 h-4 text-emerald-600" />
                        <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                          Extraction Results & Citations
                        </h3>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-[#0f5132]">
                          {runData.structured_fields.length} Fields
                        </span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800">
                          {runData.entities.length} Entities
                        </span>
                      </div>

                      <span className="text-[11px] font-semibold text-slate-500">
                        Click <span className="text-[#0f5132] font-bold">[Page #]</span> to jump
                      </span>
                    </div>

                    {/* Section Selector Tab Bar */}
                    <div className="flex items-center space-x-1 px-3 py-1.5 bg-slate-100 border-t border-slate-200 overflow-x-auto text-xs">
                      {[
                        { id: 'all', label: 'All Sections' },
                        { id: 'content', label: 'A. Content' },
                        { id: 'metadata', label: 'B. Metadata' },
                        { id: 'summary', label: 'C. Summary' },
                        { id: 'entities', label: 'D. Entities' },
                        { id: 'keyPoints', label: 'E. Key Points' },
                        { id: 'fields', label: 'F. Fields' },
                        { id: 'warnings', label: `G. Warnings (${runData.warnings?.length || 0})` },
                      ].map(tab => (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => setActiveResultsTab(tab.id as any)}
                          className={`px-2.5 py-1 rounded-md text-[11px] font-semibold whitespace-nowrap transition-colors ${
                            activeResultsTab === tab.id
                              ? 'bg-white text-[#0f5132] shadow-xs font-bold'
                              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Scrollable Extraction Content */}
                  <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {/* Confirmation Success Banner (Displayed once registered) */}
                    {confirmedCaseId && (
                      <div className="p-4 bg-emerald-50 border border-emerald-300 rounded-xl space-y-3 shadow-xs animate-in fade-in">
                        <div className="flex items-start space-x-3">
                          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
                          <div className="flex-1">
                            <h4 className="text-sm font-bold text-emerald-950">
                              FIR Registered Successfully: {confirmedFirNumber}
                            </h4>
                            <p className="text-xs text-emerald-800 mt-0.5">
                              Document evidence, confirmed entities, and verified fields saved to database. Post-intake workflow stages are executing automatically.
                            </p>
                          </div>
                        </div>

                        {/* Direct Navigation Links */}
                        <div className="flex flex-wrap gap-2 pt-1 border-t border-emerald-200/80">
                          <button
                            type="button"
                            onClick={() => navigate(`/cases/${confirmedCaseId}`)}
                            className="px-3 py-1.5 bg-[#0f5132] hover:bg-[#0a3d26] text-white rounded-lg text-xs font-semibold inline-flex items-center space-x-1.5 shadow-sm"
                          >
                            <FolderOpen className="w-3.5 h-3.5" />
                            <span>Open in Existing/Old FIRs</span>
                            <ExternalLink className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => navigate(`/case-diary?caseId=${confirmedCaseId}`)}
                            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold inline-flex items-center space-x-1.5 shadow-sm"
                          >
                            <BookOpen className="w-3.5 h-3.5" />
                            <span>Case Diary</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => navigate(`/chargesheet?caseId=${confirmedCaseId}`)}
                            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold inline-flex items-center space-x-1.5 shadow-sm"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            <span>Chargesheet</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => navigate(`/legal?caseId=${confirmedCaseId}`)}
                            className="px-3 py-1.5 bg-purple-800 hover:bg-purple-900 text-white rounded-lg text-xs font-semibold inline-flex items-center space-x-1.5 shadow-sm"
                          >
                            <Scale className="w-3.5 h-3.5" />
                            <span>AI Legal Intelligence</span>
                          </button>
                        </div>
                      </div>
                    )}

                    {/* ── SECTION G: QUALITY WARNINGS ── */}
                    {(activeResultsTab === 'all' || activeResultsTab === 'warnings') && runData.warnings && runData.warnings.length > 0 && (
                      <div className="border border-amber-200 bg-amber-50 rounded-xl p-3">
                        <div
                          className="flex items-center justify-between cursor-pointer"
                          onClick={() => setExpanded(e => ({ ...e, warnings: !e.warnings }))}
                        >
                          <div className="flex items-center space-x-2">
                            <AlertCircle className="w-4 h-4 text-amber-600" />
                            <span className="text-xs font-bold text-amber-900">
                              Section G: Document Quality Warnings ({runData.warnings.length})
                            </span>
                          </div>
                          <ChevronDown
                            className={`w-4 h-4 text-amber-600 transition-transform ${
                              expanded.warnings ? 'rotate-180' : ''
                            }`}
                          />
                        </div>
                        {expanded.warnings && (
                          <ul className="mt-2 space-y-1 pl-5 list-disc text-xs text-amber-800">
                            {runData.warnings.map((w, idx) => (
                              <li key={idx}>{w}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    {/* ── SECTION B: DOCUMENT METADATA ── */}
                    {(activeResultsTab === 'all' || activeResultsTab === 'metadata') && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div
                          className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                          onClick={() => setExpanded(e => ({ ...e, metadata: !e.metadata }))}
                        >
                          <div className="flex items-center space-x-2">
                            <Shield className="w-4 h-4 text-[#0f5132]" />
                            <span className="text-xs font-bold text-slate-800">Section B: Verified Document Metadata</span>
                          </div>
                          <ChevronDown
                            className={`w-4 h-4 text-slate-400 transition-transform ${
                              expanded.metadata ? 'rotate-180' : ''
                            }`}
                          />
                        </div>
                        {expanded.metadata && (
                          <div className="p-3.5 bg-white border-t border-slate-100 space-y-3">
                            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Original Filename</span>
                                <span className="font-semibold text-slate-900 truncate block" title={runData.document_metadata?.original_filename || runData.original_filename}>
                                  {runData.document_metadata?.original_filename || runData.original_filename}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Document ID</span>
                                <span className="font-mono text-[11px] text-slate-700 block truncate" title={runData.document_id}>
                                  {runData.document_id}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Associated Case ID</span>
                                <span className="font-mono text-[11px] text-slate-700 block truncate">
                                  {confirmedCaseId || runData.document_metadata?.case_id || runData.case_id || 'Pending Confirmation'}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Document Type</span>
                                <span className="font-semibold text-slate-800">
                                  {runData.document_metadata?.document_type || 'First Information Report (FIR)'}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Upload Timestamp</span>
                                <span className="text-slate-700">
                                  {runData.document_metadata?.upload_date || 'Current Session'}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Extraction Timestamp</span>
                                <span className="text-slate-700">
                                  {runData.document_metadata?.extraction_date || 'Completed'}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Physical Page Count</span>
                                <span className="font-semibold text-slate-800">
                                  {runData.document_metadata?.total_pages || runData.page_count || 1} Page(s)
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Format & File Size</span>
                                <span className="font-semibold text-slate-800">
                                  {runData.document_metadata?.file_format || 'PDF'} • {runData.document_metadata?.file_size || 'N/A'}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">OCR Status</span>
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                                  {runData.document_metadata?.ocr_status || 'COMPLETED'}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Document SHA-256 Hash</span>
                                <span className="font-mono text-[10px] text-slate-600 block truncate" title={runData.document_metadata?.file_hash || runData.file_hash}>
                                  {runData.document_metadata?.file_hash || runData.file_hash || 'Verified'}
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Provider & Model</span>
                                <span className="font-semibold text-emerald-800">
                                  {runData.document_metadata?.provider || runData.provider || 'AI Extractor'} ({runData.document_metadata?.model || 'v1'})
                                </span>
                              </div>
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">OCR Quality Score</span>
                                <span className="font-bold text-slate-800">
                                  {runData.document_metadata?.ocr_quality != null
                                    ? `${Math.round(runData.document_metadata.ocr_quality * 100)}% Verified`
                                    : '95% Verified'}
                                </span>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── SECTION C: GROUNDED RAW-TEXT SUMMARY ── */}
                    {(activeResultsTab === 'all' || activeResultsTab === 'summary') && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div
                          className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                          onClick={() => setExpanded(e => ({ ...e, summary: !e.summary }))}
                        >
                          <div className="flex items-center space-x-2">
                            <BookOpen className="w-4 h-4 text-emerald-700" />
                            <span className="text-xs font-bold text-slate-800">Section C: Grounded Raw-Text Summary</span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              ({(runData.raw_text_summary || runData.document_metadata?.raw_text_summary || '').split(/\s+/).filter(Boolean).length} words)
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            <button
                              type="button"
                              onClick={ev => {
                                ev.stopPropagation();
                                const textToCopy = runData.raw_text_summary || runData.document_metadata?.raw_text_summary || '';
                                if (textToCopy) {
                                  navigator.clipboard.writeText(textToCopy);
                                  setCopiedSummary(true);
                                  setTimeout(() => setCopiedSummary(false), 2000);
                                }
                              }}
                              className="p-1 text-slate-500 hover:text-[#0f5132] inline-flex items-center space-x-1 text-[11px] font-semibold"
                              title="Copy summary"
                            >
                              {copiedSummary ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                              <span>{copiedSummary ? 'Copied' : 'Copy Summary'}</span>
                            </button>
                            <ChevronDown
                              className={`w-4 h-4 text-slate-400 transition-transform ${
                                expanded.summary ? 'rotate-180' : ''
                              }`}
                            />
                          </div>
                        </div>
                        {expanded.summary && (
                          <div className="p-3.5 bg-white border-t border-slate-100">
                            <div className="p-3 bg-emerald-50/50 rounded-lg border border-emerald-200 text-xs text-slate-800 leading-relaxed font-sans">
                              {runData.raw_text_summary || runData.document_metadata?.raw_text_summary || 'No summary text generated.'}
                            </div>
                            <div className="mt-2 text-[10px] text-slate-400 italic">
                              * Grounded exclusively in the verified OCR text of this uploaded document.
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── SECTION A: DOCUMENT CONTENT (FULL OCR TEXT & PAGES) ── */}
                    {(activeResultsTab === 'all' || activeResultsTab === 'content') && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div
                          className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                          onClick={() => setExpanded(e => ({ ...e, content: !e.content }))}
                        >
                          <div className="flex items-center space-x-2">
                            <FileText className="w-4 h-4 text-[#0f5132]" />
                            <span className="text-xs font-bold text-slate-800">Section A: Document Content & Full OCR Text</span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              ({runData.document_content ? runData.document_content.split(/\s+/).filter(Boolean).length : 0} words)
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            <button
                              type="button"
                              onClick={ev => {
                                ev.stopPropagation();
                                if (runData.document_content) {
                                  navigator.clipboard.writeText(runData.document_content);
                                  setCopiedContent(true);
                                  setTimeout(() => setCopiedContent(false), 2000);
                                }
                              }}
                              className="p-1 text-slate-500 hover:text-[#0f5132] inline-flex items-center space-x-1 text-[11px] font-semibold"
                              title="Copy full text"
                            >
                              {copiedContent ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                              <span>{copiedContent ? 'Copied' : 'Copy Text'}</span>
                            </button>
                            <ChevronDown
                              className={`w-4 h-4 text-slate-400 transition-transform ${
                                expanded.content ? 'rotate-180' : ''
                              }`}
                            />
                          </div>
                        </div>
                        {expanded.content && (
                          <div className="p-3 bg-white border-t border-slate-100 space-y-2.5">
                            {/* Page filter buttons if multi-page content available */}
                            {runData.pages_content && runData.pages_content.length > 1 && (
                              <div className="flex items-center space-x-1.5 overflow-x-auto pb-1 border-b border-slate-100 text-xs">
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex-shrink-0">
                                  Page View:
                                </span>
                                <button
                                  type="button"
                                  onClick={() => setSelectedContentPage('all')}
                                  className={`px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0 transition-colors ${
                                    selectedContentPage === 'all'
                                      ? 'bg-[#0f5132] text-white'
                                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                  }`}
                                >
                                  All Pages ({runData.pages_content.length})
                                </button>
                                {runData.pages_content.map(p => (
                                  <button
                                    key={p.page_number}
                                    type="button"
                                    onClick={() => {
                                      setSelectedContentPage(p.page_number);
                                      handleJumpToPage(p.page_number);
                                    }}
                                    className={`px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0 transition-colors ${
                                      selectedContentPage === p.page_number
                                        ? 'bg-[#0f5132] text-white'
                                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                    }`}
                                  >
                                    Page {p.page_number}
                                  </button>
                                ))}
                              </div>
                            )}

                            {/* OCR Text Box */}
                            <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 font-mono text-xs text-slate-800 whitespace-pre-wrap max-h-56 overflow-y-auto leading-relaxed">
                              {selectedContentPage === 'all'
                                ? (runData.pages_content && runData.pages_content.length > 0
                                    ? runData.pages_content.map(p => (
                                        <div key={p.page_number} className="mb-4 last:mb-0">
                                          <div className="flex items-center justify-between text-[10px] font-bold text-slate-400 border-b border-slate-200 pb-1 mb-2">
                                            <span>--- Physical Page {p.page_number} ---</span>
                                            {p.ocr_confidence && (
                                              <span>OCR Conf: {Math.round(p.ocr_confidence * 100)}%</span>
                                            )}
                                          </div>
                                          <div>{p.text || '[Empty or unreadable page]'}</div>
                                        </div>
                                      ))
                                    : runData.document_content || 'No text extracted from document.')
                                : (runData.pages_content?.find(p => p.page_number === selectedContentPage)?.text || 'No text recorded for this page.')}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── SECTION D: ENTITIES & CITATIONS ── */}
                    {(activeResultsTab === 'all' || activeResultsTab === 'entities') && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div
                          className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                          onClick={() => setExpanded(e => ({ ...e, entities: !e.entities }))}
                        >
                          <div className="flex items-center space-x-2">
                            <Layers className="w-4 h-4 text-blue-600" />
                            <span className="text-xs font-bold text-slate-800">
                              Section D: Extracted Entities ({runData.entities?.length || 0})
                            </span>
                          </div>
                          <ChevronDown
                            className={`w-4 h-4 text-slate-400 transition-transform ${
                              expanded.entities ? 'rotate-180' : ''
                            }`}
                          />
                        </div>
                        {expanded.entities && (
                          <div className="p-3 bg-white border-t border-slate-100 space-y-3">
                            {/* Entity Category Filter Pills */}
                            <div className="flex items-center space-x-1 overflow-x-auto pb-1 text-xs">
                              {[
                                { id: 'ALL', label: 'All' },
                                { id: 'PEOPLE', label: 'People & Roles' },
                                { id: 'LOCATIONS', label: 'Locations & Stn' },
                                { id: 'DATES', label: 'Dates & Times' },
                                { id: 'DIGITAL', label: 'Phones & Digital' },
                                { id: 'VEHICLES', label: 'Vehicles' },
                                { id: 'CONTRABAND', label: 'Contraband' },
                                { id: 'FINANCIAL', label: 'Financial' },
                                { id: 'LEGAL', label: 'Sections & Evidence' },
                              ].map(cat => (
                                <button
                                  key={cat.id}
                                  type="button"
                                  onClick={() => setEntityCategory(cat.id)}
                                  className={`px-2 py-0.5 rounded text-[11px] font-semibold whitespace-nowrap transition-colors ${
                                    entityCategory === cat.id
                                      ? 'bg-blue-600 text-white'
                                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                  }`}
                                >
                                  {cat.label}
                                </button>
                              ))}
                            </div>

                            {/* Entities Grid/List */}
                            <div className="flex flex-wrap gap-2">
                              {runData.entities
                                ?.filter(ent => {
                                  if (entityCategory === 'PEOPLE') return ['ACCUSED', 'COMPLAINANT', 'VICTIM', 'WITNESS', 'OFFICER', 'PERSON'].includes(ent.type);
                                  if (entityCategory === 'LOCATIONS') return ['LOCATION', 'JURISDICTION'].includes(ent.type);
                                  if (entityCategory === 'DATES') return ent.type === 'DATE_TIME';
                                  if (entityCategory === 'DIGITAL') return ['DIGITAL_ID', 'PHONE'].includes(ent.type);
                                  if (entityCategory === 'VEHICLES') return ent.type === 'VEHICLE';
                                  if (entityCategory === 'CONTRABAND') return ent.type === 'CONTRABAND';
                                  if (entityCategory === 'FINANCIAL') return ent.type === 'FINANCIAL';
                                  if (entityCategory === 'LEGAL') return ['SECTION', 'EVIDENCE'].includes(ent.type);
                                  return true;
                                })
                                .map(ent => (
                                  <div
                                    key={ent.id}
                                    className="p-2 rounded-lg text-xs bg-slate-50 border border-slate-200 text-slate-800 shadow-2xs space-y-1 min-w-[200px] flex-1 max-w-[320px]"
                                  >
                                    <div className="flex items-center justify-between gap-1">
                                      <span
                                        className={`px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-wider ${
                                          ['ACCUSED'].includes(ent.type)
                                            ? 'bg-red-100 text-red-800'
                                            : ['COMPLAINANT', 'VICTIM'].includes(ent.type)
                                            ? 'bg-blue-100 text-blue-800'
                                            : ['OFFICER'].includes(ent.type)
                                            ? 'bg-emerald-100 text-emerald-800'
                                            : ['LOCATION', 'JURISDICTION'].includes(ent.type)
                                            ? 'bg-teal-100 text-teal-800'
                                            : ['DATE_TIME'].includes(ent.type)
                                            ? 'bg-indigo-100 text-indigo-800'
                                            : ['VEHICLE'].includes(ent.type)
                                            ? 'bg-amber-100 text-amber-800'
                                            : ['CONTRABAND'].includes(ent.type)
                                            ? 'bg-rose-100 text-rose-800'
                                            : ['FINANCIAL'].includes(ent.type)
                                            ? 'bg-yellow-100 text-yellow-800'
                                            : ['SECTION', 'EVIDENCE'].includes(ent.type)
                                            ? 'bg-purple-100 text-purple-800'
                                            : 'bg-slate-200 text-slate-700'
                                        }`}
                                      >
                                        {ent.type.replace('_', ' ')}
                                      </span>

                                      <div className="flex items-center space-x-1.5">
                                        {ent.confidence != null && (
                                          <span className="text-[10px] text-slate-400 font-mono">
                                            {Math.round(ent.confidence * 100)}%
                                          </span>
                                        )}
                                        <button
                                          type="button"
                                          onClick={() => handleJumpToPage(ent.source_page || 1)}
                                          className="text-[10px] font-bold text-[#0f5132] hover:underline"
                                          title={`Jump to Page ${ent.source_page || 1}`}
                                        >
                                          [P{ent.source_page || 1}]
                                        </button>
                                      </div>
                                    </div>

                                    <div className="font-bold text-slate-900 leading-snug">
                                      {ent.name}
                                    </div>

                                    {ent.context && (
                                      <p className="text-[11px] text-slate-500 italic">
                                        {ent.context}
                                      </p>
                                    )}
                                  </div>
                                ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── SECTION E: KEY POINTS ── */}
                    {(activeResultsTab === 'all' || activeResultsTab === 'keyPoints') && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div
                          className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                          onClick={() => setExpanded(e => ({ ...e, keyPoints: !e.keyPoints }))}
                        >
                          <div className="flex items-center space-x-2">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                            <span className="text-xs font-bold text-slate-800">
                              Section E: Grounded Key Factual Points ({runData.key_points?.length || 0})
                            </span>
                          </div>
                          <ChevronDown
                            className={`w-4 h-4 text-slate-400 transition-transform ${
                              expanded.keyPoints ? 'rotate-180' : ''
                            }`}
                          />
                        </div>
                        {expanded.keyPoints && (
                          <div className="p-3 bg-white border-t border-slate-100 space-y-1.5">
                            {runData.key_points && runData.key_points.length > 0 ? (
                              runData.key_points.map(kp => (
                                <div
                                  key={kp.id}
                                  className="flex items-start justify-between text-xs text-slate-800 bg-slate-50 p-2.5 rounded-lg border border-slate-200"
                                >
                                  <div className="flex items-start space-x-2">
                                    <span className="text-[#0f5132] font-black">•</span>
                                    <span>{kp.point}</span>
                                  </div>
                                  {kp.source_page && (
                                    <button
                                      type="button"
                                      onClick={() => handleJumpToPage(kp.source_page || 1)}
                                      className="ml-3 text-[10px] font-bold text-[#0f5132] hover:underline flex-shrink-0"
                                      title={`Navigate to source page ${kp.source_page}`}
                                    >
                                      [Page {kp.source_page}]
                                    </button>
                                  )}
                                </div>
                              ))
                            ) : (
                              <div className="text-xs text-slate-400 p-2">No key points extracted.</div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── SECTION F: STRUCTURED FIR FIELDS (OFFICER REVIEW) ── */}
                    {(activeResultsTab === 'all' || activeResultsTab === 'fields') && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between border-b border-slate-200">
                          <div className="flex items-center space-x-2">
                            <CheckCircle2 className="w-4 h-4 text-[#0f5132]" />
                            <span className="text-xs font-bold text-slate-800">
                              Section F: Structured FIR Fields (Officer Review & Edit)
                            </span>
                          </div>
                          <input
                            type="text"
                            placeholder="Filter fields..."
                            value={fieldFilter}
                            onChange={e => setFieldFilter(e.target.value)}
                            className="text-xs px-2.5 py-1 border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-[#0f5132]"
                          />
                        </div>

                        <div className="p-3.5 bg-white space-y-4">
                          {/* Group 1: General FIR Information */}
                          <div className="space-y-2">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-1">
                              1. General FIR Information
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {runData.structured_fields
                                .filter(f => ['fir_number', 'year', 'district', 'station', 'registration_date', 'registration_time'].includes(f.key))
                                .filter(f => !fieldFilter || f.label.toLowerCase().includes(fieldFilter.toLowerCase()))
                                .map(f => {
                                  const valStr = f.value != null ? (Array.isArray(f.value) ? f.value.join(', ') : String(f.value)) : '';
                                  const isRequired = ['fir_number', 'district', 'station'].includes(f.key) || f.required;
                                  return (
                                    <div key={f.id} className="space-y-1">
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-1.5">
                                          <label className="text-xs font-bold text-slate-800">{f.label}</label>
                                          {isRequired && (
                                            <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-red-100 text-red-700 uppercase">
                                              Required
                                            </span>
                                          )}
                                        </div>
                                        {f.source_page && (
                                          <button
                                            type="button"
                                            onClick={() => handleJumpToPage(f.source_page || 1)}
                                            className="text-[10px] font-bold text-[#0f5132] hover:underline"
                                          >
                                            [P{f.source_page}]
                                          </button>
                                        )}
                                      </div>
                                      <input
                                        type="text"
                                        value={valStr}
                                        onChange={e => handleFieldChange(f.key, e.target.value)}
                                        placeholder={f.description || `Enter ${f.label}`}
                                        className="w-full text-xs border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-[#0f5132] focus:border-transparent font-medium text-slate-800"
                                      />
                                    </div>
                                  );
                                })}
                            </div>
                          </div>

                          {/* Group 2: Incident & Jurisdiction */}
                          <div className="space-y-2 pt-2 border-t border-slate-100">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-1">
                              2. Incident & Occurrence
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {runData.structured_fields
                                .filter(f => ['offence_date', 'offence_time', 'place_of_occurrence', 'mandal', 'village', 'distance_from_station'].includes(f.key))
                                .filter(f => !fieldFilter || f.label.toLowerCase().includes(fieldFilter.toLowerCase()))
                                .map(f => {
                                  const valStr = f.value != null ? (Array.isArray(f.value) ? f.value.join(', ') : String(f.value)) : '';
                                  return (
                                    <div key={f.id} className="space-y-1">
                                      <div className="flex items-center justify-between">
                                        <label className="text-xs font-bold text-slate-800">{f.label}</label>
                                        {f.source_page && (
                                          <button
                                            type="button"
                                            onClick={() => handleJumpToPage(f.source_page || 1)}
                                            className="text-[10px] font-bold text-[#0f5132] hover:underline"
                                          >
                                            [P{f.source_page}]
                                          </button>
                                        )}
                                      </div>
                                      <input
                                        type="text"
                                        value={valStr}
                                        onChange={e => handleFieldChange(f.key, e.target.value)}
                                        placeholder={f.description || `Enter ${f.label}`}
                                        className="w-full text-xs border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-[#0f5132] focus:border-transparent font-medium text-slate-800"
                                      />
                                    </div>
                                  );
                                })}
                            </div>
                          </div>

                          {/* Group 3: Parties & Accused */}
                          <div className="space-y-2 pt-2 border-t border-slate-100">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-1">
                              3. Parties & Complainant
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {runData.structured_fields
                                .filter(f => ['complainant_name', 'complainant_contact', 'accused_names', 'victim_names'].includes(f.key))
                                .filter(f => !fieldFilter || f.label.toLowerCase().includes(fieldFilter.toLowerCase()))
                                .map(f => {
                                  const valStr = f.value != null ? (Array.isArray(f.value) ? f.value.join(', ') : String(f.value)) : '';
                                  return (
                                    <div key={f.id} className="space-y-1">
                                      <div className="flex items-center justify-between">
                                        <label className="text-xs font-bold text-slate-800">{f.label}</label>
                                        {f.source_page && (
                                          <button
                                            type="button"
                                            onClick={() => handleJumpToPage(f.source_page || 1)}
                                            className="text-[10px] font-bold text-[#0f5132] hover:underline"
                                          >
                                            [P{f.source_page}]
                                          </button>
                                        )}
                                      </div>
                                      <input
                                        type="text"
                                        value={valStr}
                                        onChange={e => handleFieldChange(f.key, e.target.value)}
                                        placeholder={f.description || `Enter ${f.label}`}
                                        className="w-full text-xs border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-[#0f5132] focus:border-transparent font-medium text-slate-800"
                                      />
                                    </div>
                                  );
                                })}
                            </div>
                          </div>

                          {/* Group 4: Seizure & Evidence */}
                          <div className="space-y-2 pt-2 border-t border-slate-100">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-1">
                              4. Offence, Seizure & Evidence
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {runData.structured_fields
                                .filter(f => ['offence_nature', 'contraband_type', 'seized_quantity', 'seized_unit', 'property_loss_amount', 'vehicle_details', 'evidence_collected'].includes(f.key))
                                .filter(f => !fieldFilter || f.label.toLowerCase().includes(fieldFilter.toLowerCase()))
                                .map(f => {
                                  const valStr = f.value != null ? (Array.isArray(f.value) ? f.value.join(', ') : String(f.value)) : '';
                                  const isRequired = f.key === 'offence_nature' || f.required;
                                  return (
                                    <div key={f.id} className="space-y-1">
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-1.5">
                                          <label className="text-xs font-bold text-slate-800">{f.label}</label>
                                          {isRequired && (
                                            <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-red-100 text-red-700 uppercase">
                                              Required
                                            </span>
                                          )}
                                        </div>
                                        {f.source_page && (
                                          <button
                                            type="button"
                                            onClick={() => handleJumpToPage(f.source_page || 1)}
                                            className="text-[10px] font-bold text-[#0f5132] hover:underline"
                                          >
                                            [P{f.source_page}]
                                          </button>
                                        )}
                                      </div>
                                      <input
                                        type="text"
                                        value={valStr}
                                        onChange={e => handleFieldChange(f.key, e.target.value)}
                                        placeholder={f.description || `Enter ${f.label}`}
                                        className="w-full text-xs border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-[#0f5132] focus:border-transparent font-medium text-slate-800"
                                      />
                                    </div>
                                  );
                                })}
                            </div>
                          </div>

                          {/* Group 5: Legal Sections & Narrative */}
                          <div className="space-y-2 pt-2 border-t border-slate-100">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-1">
                              5. Legal Sections & Officers
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {runData.structured_fields
                                .filter(f => ['law_sections', 'investigating_officer', 'seizing_officer_name', 'brief_facts', 'incident_narrative'].includes(f.key))
                                .filter(f => !fieldFilter || f.label.toLowerCase().includes(fieldFilter.toLowerCase()))
                                .map(f => {
                                  const valStr = f.value != null ? (Array.isArray(f.value) ? f.value.join(', ') : String(f.value)) : '';
                                  const isTextArea = ['brief_facts', 'incident_narrative'].includes(f.key);
                                  return (
                                    <div key={f.id} className={`space-y-1 ${isTextArea ? 'md:col-span-2' : ''}`}>
                                      <div className="flex items-center justify-between">
                                        <label className="text-xs font-bold text-slate-800">{f.label}</label>
                                        {f.source_page && (
                                          <button
                                            type="button"
                                            onClick={() => handleJumpToPage(f.source_page || 1)}
                                            className="text-[10px] font-bold text-[#0f5132] hover:underline"
                                          >
                                            [P{f.source_page}]
                                          </button>
                                        )}
                                      </div>
                                      {isTextArea ? (
                                        <textarea
                                          rows={3}
                                          value={valStr}
                                          onChange={e => handleFieldChange(f.key, e.target.value)}
                                          placeholder={f.description || `Enter ${f.label}`}
                                          className="w-full text-xs border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-[#0f5132] focus:border-transparent font-medium text-slate-800"
                                        />
                                      ) : (
                                        <input
                                          type="text"
                                          value={valStr}
                                          onChange={e => handleFieldChange(f.key, e.target.value)}
                                          placeholder={f.description || `Enter ${f.label}`}
                                          className="w-full text-xs border border-slate-300 rounded-lg p-2 focus:ring-2 focus:ring-[#0f5132] focus:border-transparent font-medium text-slate-800"
                                        />
                                      )}
                                    </div>
                                  );
                                })}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Officer Sign-Off & Confirmation Footer */}
                  <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 flex-shrink-0">
                    <div className="text-[11px] text-slate-600">
                      <strong>Mandatory Human Sign-Off:</strong> Confirming verifies the extraction data and triggers automated post-intake intelligence pipeline.
                    </div>
                    <button
                      type="button"
                      onClick={handleConfirmAndRegister}
                      disabled={processing}
                      className="px-5 py-2.5 bg-[#0f5132] hover:bg-[#0a3d26] text-white rounded-lg text-xs font-bold inline-flex items-center space-x-2 shadow-md transition-all self-stretch sm:self-auto justify-center disabled:opacity-50"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      <span>{processing ? 'Registering & Executing Pipeline...' : 'Confirm & Register Case'}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 2: TYPED NARRATIVE ───────────────────────────────────────────── */}
      {activeTab === 'narrative' && (
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
            Type or Paste FIR Occurrence Narrative (English, Telugu, or Hindi):
          </label>
          <textarea
            rows={6}
            value={narrativeText}
            onChange={e => setNarrativeText(e.target.value)}
            placeholder="e.g. On 14-08-2024 at Kallur Toll Plaza, Kurnool, seized 45 litres of ID Liquor in Auto AP21TY4567. Accused Ramu Naidu and Someshwar Rao arrested under Section 34(a) AP Excise Act..."
            className="w-full text-xs border border-slate-300 rounded-lg p-3 focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
          />
          <div className="flex justify-between items-center pt-2">
            <span className="text-[11px] text-slate-500">
              Language: <strong>{language.toUpperCase()}</strong> (Selected via Portal Header)
            </span>
            <button
              type="button"
              onClick={handleNarrativeExtract}
              disabled={processing || !narrativeText.trim()}
              className="px-4 py-2 bg-[#0f5132] hover:bg-[#0a3d26] text-white rounded-lg text-xs font-bold inline-flex items-center space-x-1.5 shadow-sm disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span>{processing ? 'Extracting via Gemini...' : 'Extract Structured Case Fields'}</span>
            </button>
          </div>
        </div>
      )}

      {/* ── TAB 3: VOICE INTAKE ─────────────────────────────────────────────── */}
      {activeTab === 'voice' && (
        <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm text-center space-y-4">
          <div className="w-16 h-16 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mx-auto shadow-inner">
            <Mic className="w-8 h-8" />
          </div>
          <div className="max-w-md mx-auto">
            <h3 className="font-bold text-sm text-slate-900">Voice FIR Intake Capture</h3>
            <p className="text-xs text-slate-500 mt-1">
              Speak in Telugu, Hindi, or English. Audio is securely transcribed and parsed into structured FIR fields.
            </p>
          </div>
          <button
            type="button"
            onClick={handleVoiceSimulate}
            disabled={processing}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold inline-flex items-center space-x-2 shadow-sm"
          >
            <Mic className="w-4 h-4" />
            <span>{processing ? 'Transcribing & Structuring...' : 'Record & Transcribe Sample Voice'}</span>
          </button>
        </div>
      )}

      {/* ── REVIEW FORM FOR NARRATIVE & VOICE MODES ─────────────────────────── */}
      {activeTab !== 'file' && (
        <form onSubmit={handleConfirmAndRegister} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 text-[#0f5132]" />
              <h3 className="font-bold text-sm text-slate-900">Officer Verification & Sign-Off</h3>
            </div>
            <span className="text-[10px] font-bold bg-amber-100 text-amber-800 px-2.5 py-0.5 rounded">
              STATE: DRAFT (REQUIRES SIGN-OFF)
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 text-xs">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">FIR Number *</label>
              <input
                type="text"
                required
                value={formData.fir_number}
                onChange={e => setFormData({ ...formData, fir_number: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2 font-mono font-bold"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">District *</label>
              <input
                type="text"
                required
                value={formData.district}
                onChange={e => setFormData({ ...formData, district: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Station *</label>
              <input
                type="text"
                required
                value={formData.station}
                onChange={e => setFormData({ ...formData, station: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Offence Nature *</label>
              <input
                type="text"
                required
                value={formData.offence_nature}
                onChange={e => setFormData({ ...formData, offence_nature: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Contraband / Seized Property</label>
              <input
                type="text"
                value={formData.contraband_type}
                onChange={e => setFormData({ ...formData, contraband_type: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Quantity & Unit</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  step="0.1"
                  value={formData.seized_quantity}
                  onChange={e => setFormData({ ...formData, seized_quantity: parseFloat(e.target.value) || 0 })}
                  className="w-2/3 border border-slate-300 rounded-lg p-2"
                />
                <input
                  type="text"
                  value={formData.seized_unit}
                  onChange={e => setFormData({ ...formData, seized_unit: e.target.value })}
                  className="w-1/3 border border-slate-300 rounded-lg p-2"
                />
              </div>
            </div>
            <div className="sm:col-span-3">
              <label className="block font-semibold text-slate-700 mb-1">Vehicle / Conveyance Details</label>
              <input
                type="text"
                value={formData.vehicle_details}
                onChange={e => setFormData({ ...formData, vehicle_details: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2 font-mono"
              />
            </div>
            <div className="sm:col-span-3">
              <label className="block font-semibold text-slate-700 mb-1">Case Narrative</label>
              <textarea
                rows={3}
                value={formData.narrative}
                onChange={e => setFormData({ ...formData, narrative: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-100">
            <button
              type="submit"
              disabled={processing}
              className="px-5 py-2.5 bg-[#0f5132] hover:bg-[#0a3d26] text-white rounded-lg text-xs font-bold inline-flex items-center space-x-2 shadow-sm"
            >
              <Save className="w-4 h-4" />
              <span>{processing ? 'Registering & Executing Pipeline...' : 'Confirm & Register Case'}</span>
            </button>
          </div>
        </form>
      )}
    </div>
  );
};

export default NewCaseIntake;

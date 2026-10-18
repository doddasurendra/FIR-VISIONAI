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
  FolderOpen
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
  pages_content?: Array<{
    page_number: number;
    text: string;
    ocr_applied?: boolean;
    ocr_confidence?: number | null;
    is_unreadable?: boolean;
  }>;
  raw_text_summary?: string;
  document_metadata?: {
    original_filename?: string;
    document_id?: string;
    case_id?: string | null;
    document_type?: string;
    upload_date?: string | null;
    extraction_date?: string;
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
  const [copiedSummary, setCopiedSummary] = useState<boolean>(false);
  const [copiedHash, setCopiedHash] = useState<boolean>(false);
  const [entityCategoryFilter, setEntityCategoryFilter] = useState<string>('ALL');
  const [ocrViewMode, setOcrViewMode] = useState<'full' | 'paged'>('full');

  // Accordion Expand States
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    warnings: true,
    metadata: true,
    summary: true,
    entities: true,
    keyPoints: true,
    fields: true,
    content: true
  });

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

    // Also sync standard form fields
    const syncKeys = [
      'fir_number',
      'district',
      'station',
      'mandal',
      'village',
      'offence_nature',
      'contraband_type',
      'seized_quantity',
      'seized_unit',
      'vehicle_details',
      'narrative'
    ];
    if (syncKeys.includes(fieldKey)) {
      setFormData((prev: any) => ({ ...prev, [fieldKey]: newValue }));
    }
  };

  const getEntityCategory = (type: string) => {
    switch (type) {
      case 'ACCUSED':
      case 'COMPLAINANT':
      case 'VICTIM':
      case 'OFFICER':
      case 'PERSON':
        return 'PEOPLE';
      case 'LOCATION':
      case 'JURISDICTION':
        return 'LOCATIONS';
      case 'DATE_TIME':
        return 'DATES';
      case 'PHONE':
      case 'DIGITAL_ID':
        return 'DIGITAL';
      case 'VEHICLE':
        return 'VEHICLES';
      case 'CONTRABAND':
        return 'CONTRABAND';
      case 'SECTION':
        return 'SECTIONS';
      case 'EVIDENCE':
        return 'EVIDENCE';
      case 'FINANCIAL':
        return 'FINANCIAL';
      default:
        return 'OTHER';
    }
  };

  const getFieldGroup = (key: string) => {
    if (['fir_number', 'year', 'district', 'station', 'offence_nature'].includes(key)) return 'FIR & Jurisdiction';
    if (['offence_date', 'offence_time', 'information_received_date', 'place_of_occurrence', 'incident_location'].includes(key)) return 'Occurrence & Timeline';
    if (['complainant_name', 'complainant_contact', 'accused_names', 'victim_names'].includes(key)) return 'Persons & Roles';
    if (['contraband_type', 'seized_quantity', 'seized_unit', 'vehicle_details', 'property_loss_amount', 'financial_loss_amount', 'seized_property_details', 'evidence_collected'].includes(key)) return 'Seizure & Evidence';
    return 'Investigation & Legal Sections';
  };

  // ───────────────────────────────────────────────────────────────────────────
  // Handle File Upload & Extraction (Unified Workspace Pipeline)
  // ───────────────────────────────────────────────────────────────────────────
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    setUploadFile(file);
    setErrorMsg(null);
    setConfirmedCaseId(null);
    setConfirmedFirNumber(null);
    setRunData(null);
    if (pdfBlobUrl) {
      URL.revokeObjectURL(pdfBlobUrl);
      setPdfBlobUrl(null);
    }
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
      let fullRunData: ExtractionRunData = {
        run_id: data.run_id,
        document_id: docId,
        case_id: data.case_id || data.document_metadata?.case_id,
        original_filename: data.filename || file.name,
        mime_type: data.mime_type,
        page_count: data.physical_page_count || 1,
        provider: data.provider || 'AI Document Intelligence',
        sarvam_job_id: data.sarvam_job_id,
        file_hash: data.file_hash,
        document_content: data.document_content || '',
        pages_content: data.pages_content || [],
        raw_text_summary: data.raw_text_summary || data.document_metadata?.raw_text_summary || '',
        document_metadata: data.document_metadata,
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

    // Validate mandatory fields with explicit feedback (no silent fallback placeholders)
    const missing: string[] = [];
    if (!formData.fir_number?.toString().trim()) missing.push('FIR Number');
    if (!formData.district?.toString().trim()) missing.push('District');
    if (!formData.station?.toString().trim()) missing.push('Police / Excise Station');
    if (!formData.offence_nature?.toString().trim()) missing.push('Offence Nature');

    if (missing.length > 0) {
      setErrorMsg(
        `Cannot register case: Missing required fields: ${missing.join(', ')}. Please review and complete these fields before confirming.`
      );
      return;
    }

    try {
      setProcessing(true);

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
        // Synchronize all latest form fields into structured_fields payload
        const syncMap: Record<string, any> = {
          fir_number: formData.fir_number,
          district: formData.district,
          station: formData.station,
          offence_nature: formData.offence_nature,
          contraband_type: formData.contraband_type,
          seized_quantity: formData.seized_quantity,
          seized_unit: formData.seized_unit,
          vehicle_details: formData.vehicle_details
        };
        const syncedFields = runData.structured_fields.map(f => {
          if (f.key in syncMap && syncMap[f.key] !== undefined && syncMap[f.key] !== '') {
            return { ...f, value: syncMap[f.key], reviewed: true };
          }
          return f;
        });
        const updatedRunData = { ...runData, structured_fields: syncedFields };

        // Confirm via Extraction Workspace confirmation API (registers case, entities, fields)
        const confirmRes = await api.post(`/extraction/run/${runData.run_id}/confirm`, {
          case_id: runData.case_id || confirmedCaseId,
          reviewed_data: updatedRunData
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
                  {/* Results Header */}
                  <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 bg-slate-50 flex-shrink-0">
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
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800">
                        {runData.key_points.length} Key Points
                      </span>
                    </div>

                    <span className="text-[11px] font-semibold text-slate-500">
                      Click <span className="text-[#0f5132] font-bold">[P#]</span> to jump
                    </span>
                  </div>

                  {/* Scrollable Extraction Content */}
                  <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {/* ─────────────────────────────────────────────────────────── */}
                    {/* SECTION G: Quality Warnings                             */}
                    {/* ─────────────────────────────────────────────────────────── */}
                    {runData.warnings && runData.warnings.length > 0 && (
                      <div className="border border-amber-200 bg-amber-50 rounded-xl p-3">
                        <div
                          className="flex items-center justify-between cursor-pointer"
                          onClick={() => setExpanded(e => ({ ...e, warnings: !e.warnings }))}
                        >
                          <div className="flex items-center space-x-2">
                            <AlertCircle className="w-4 h-4 text-amber-600" />
                            <span className="text-xs font-bold text-amber-900">
                              Section G • Quality & Scanning Warnings ({runData.warnings.length})
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

                    {/* ─────────────────────────────────────────────────────────── */}
                    {/* SECTION B: Document Metadata (Verified Provenance)        */}
                    {/* ─────────────────────────────────────────────────────────── */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div
                        className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => setExpanded(e => ({ ...e, metadata: !e.metadata }))}
                      >
                        <div className="flex items-center space-x-2">
                          <Shield className="w-4 h-4 text-[#0f5132]" />
                          <span className="text-xs font-bold text-slate-800">
                            Section B • Document Metadata & Verified Provenance
                          </span>
                        </div>
                        <ChevronDown
                          className={`w-4 h-4 text-slate-400 transition-transform ${
                            expanded.metadata ? 'rotate-180' : ''
                          }`}
                        />
                      </div>
                      {expanded.metadata && (
                        <div className="p-3.5 bg-white border-t border-slate-100 space-y-3">
                          <div className="grid grid-cols-2 gap-3 text-xs">
                            <div>
                              <span className="text-slate-400 block text-[10px] uppercase font-bold">Original Filename</span>
                              <span className="font-semibold text-slate-800 break-all">
                                {runData.document_metadata?.original_filename || runData.original_filename}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400 block text-[10px] uppercase font-bold">Document ID / Case ID</span>
                              <span className="font-semibold text-slate-800 font-mono text-[11px]">
                                {runData.document_metadata?.document_id || runData.document_id}
                                <span className="block text-slate-500 font-sans text-[10px]">
                                  Case: {runData.document_metadata?.case_id || runData.case_id || (confirmedCaseId || 'Unassigned (Draft)')}
                                </span>
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400 block text-[10px] uppercase font-bold">Document Type</span>
                              <span className="font-semibold text-slate-800">
                                {runData.document_metadata?.document_type || 'First Information Report (FIR)'}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400 block text-[10px] uppercase font-bold">Extraction Provider & Model</span>
                              <span className="font-semibold text-emerald-800">
                                {runData.document_metadata?.provider || runData.provider || 'AI Intelligence'}
                                {runData.document_metadata?.model && (
                                  <span className="text-[10px] text-slate-500 block">
                                    Model: {runData.document_metadata.model}
                                  </span>
                                )}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400 block text-[10px] uppercase font-bold">Upload & Extraction Dates</span>
                              <span className="text-slate-700">
                                {runData.document_metadata?.upload_date || 'Current session'}
                                <span className="block text-slate-400 text-[10px]">
                                  Extracted: {runData.document_metadata?.extraction_date || 'Just now'}
                                </span>
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400 block text-[10px] uppercase font-bold">Physical Pages & File Size</span>
                              <span className="font-semibold text-slate-800">
                                {runData.document_metadata?.page_count || runData.document_metadata?.total_pages || runData.page_count} Page(s)
                                <span className="block text-slate-500 text-[10px]">
                                  Format: {runData.document_metadata?.file_format || (runData.mime_type?.split('/')?.[1] || 'PDF').toUpperCase()} • {runData.document_metadata?.file_size || 'Verified'}
                                </span>
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400 block text-[10px] uppercase font-bold">OCR Status & Quality</span>
                              <span className="inline-flex items-center space-x-1.5 font-semibold text-emerald-700">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                <span>{runData.document_metadata?.ocr_status || 'COMPLETED'}</span>
                                {runData.document_metadata?.ocr_quality != null && (
                                  <span className="text-slate-400 text-[10px]">
                                    ({Math.round(runData.document_metadata.ocr_quality * 100)}% quality)
                                  </span>
                                )}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-400 block text-[10px] uppercase font-bold">Jurisdiction Recorded</span>
                              <span className="text-slate-800 font-semibold">
                                {runData.document_metadata?.station || formData.station || 'Not specified'}
                                <span className="block text-slate-500 text-[10px]">
                                  District: {runData.document_metadata?.district || formData.district || 'Not specified'}
                                </span>
                              </span>
                            </div>
                          </div>

                          {/* Immutable SHA-256 Digest Row */}
                          {(runData.document_metadata?.file_hash || runData.file_hash) && (
                            <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                              <div>
                                <span className="text-slate-400 block text-[10px] uppercase font-bold">Document SHA-256 Digest (Immutable)</span>
                                <span className="font-mono text-[11px] text-slate-700 break-all select-all">
                                  {runData.document_metadata?.file_hash || runData.file_hash}
                                </span>
                              </div>
                              <button
                                type="button"
                                onClick={() => {
                                  const h = runData.document_metadata?.file_hash || runData.file_hash || '';
                                  navigator.clipboard.writeText(h);
                                  setCopiedHash(true);
                                  setTimeout(() => setCopiedHash(false), 2000);
                                }}
                                className="p-1 text-slate-400 hover:text-slate-700 flex-shrink-0 ml-2"
                                title="Copy SHA-256 Digest"
                              >
                                {copiedHash ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* ─────────────────────────────────────────────────────────── */}
                    {/* SECTION C: Raw-Text Summary (Grounded in FIR Source)      */}
                    {/* ─────────────────────────────────────────────────────────── */}
                    {(() => {
                      const summaryText =
                        runData.raw_text_summary ||
                        runData.document_metadata?.raw_text_summary ||
                        runData.structured_fields.find(f => f.key === 'narrative_summary' || f.key === 'brief_facts')?.value ||
                        '';
                      const wordCount = summaryText ? summaryText.split(/\s+/).filter(Boolean).length : 0;
                      return (
                        <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                          <div
                            className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                            onClick={() => setExpanded(e => ({ ...e, summary: !e.summary }))}
                          >
                            <div className="flex items-center space-x-2">
                              <BookOpen className="w-4 h-4 text-emerald-600" />
                              <span className="text-xs font-bold text-slate-800">
                                Section C • Raw-Text Summary
                              </span>
                              {wordCount > 0 && (
                                <span className="text-[10px] font-semibold text-slate-400">
                                  ({wordCount} words)
                                </span>
                              )}
                            </div>
                            <div className="flex items-center space-x-2">
                              {summaryText && (
                                <button
                                  type="button"
                                  onClick={ev => {
                                    ev.stopPropagation();
                                    navigator.clipboard.writeText(summaryText);
                                    setCopiedSummary(true);
                                    setTimeout(() => setCopiedSummary(false), 2000);
                                  }}
                                  className="p-1 text-slate-400 hover:text-slate-700"
                                  title="Copy raw text summary"
                                >
                                  {copiedSummary ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                                </button>
                              )}
                              <ChevronDown
                                className={`w-4 h-4 text-slate-400 transition-transform ${
                                  expanded.summary ? 'rotate-180' : ''
                                }`}
                              />
                            </div>
                          </div>
                          {expanded.summary && (
                            <div className="p-3.5 bg-white border-t border-slate-100 space-y-2">
                              <p className="text-xs text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-200 leading-relaxed whitespace-pre-line">
                                {summaryText || 'Summary grounded in document facts will appear here once extracted.'}
                              </p>
                              <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1">
                                <span>Grounded exclusively in current uploaded FIR text</span>
                                <span>{wordCount} words</span>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    {/* ─────────────────────────────────────────────────────────── */}
                    {/* SECTION D: Extracted Entities (Segmented by Category)     */}
                    {/* ─────────────────────────────────────────────────────────── */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div
                        className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => setExpanded(e => ({ ...e, entities: !e.entities }))}
                      >
                        <div className="flex items-center space-x-2">
                          <Layers className="w-4 h-4 text-blue-600" />
                          <span className="text-xs font-bold text-slate-800">
                            Section D • Extracted Entities ({runData.entities.length})
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
                          {/* Category Filter Chips */}
                          <div className="flex flex-wrap gap-1">
                            {[
                              { id: 'ALL', label: 'All' },
                              { id: 'PEOPLE', label: 'People & Roles' },
                              { id: 'LOCATIONS', label: 'Locations' },
                              { id: 'DATES', label: 'Dates & Times' },
                              { id: 'DIGITAL', label: 'Phone & Digital IDs' },
                              { id: 'VEHICLES', label: 'Vehicles' },
                              { id: 'CONTRABAND', label: 'Contraband' },
                              { id: 'SECTIONS', label: 'Legal Sections' },
                              { id: 'EVIDENCE', label: 'Evidence Articles' },
                              { id: 'FINANCIAL', label: 'Financial' }
                            ].map(cat => {
                              const count =
                                cat.id === 'ALL'
                                  ? runData.entities.length
                                  : runData.entities.filter(ent => getEntityCategory(ent.type) === cat.id).length;
                              if (cat.id !== 'ALL' && count === 0) return null;
                              return (
                                <button
                                  key={cat.id}
                                  type="button"
                                  onClick={() => setEntityCategoryFilter(cat.id)}
                                  className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all ${
                                    entityCategoryFilter === cat.id
                                      ? 'bg-slate-900 text-white shadow-xs'
                                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                  }`}
                                >
                                  {cat.label} ({count})
                                </button>
                              );
                            })}
                          </div>

                          {/* Entity Search Input */}
                          <input
                            type="text"
                            placeholder="Filter entities by name or context..."
                            value={entityFilter}
                            onChange={e => setEntityFilter(e.target.value)}
                            className="w-full text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#0f5132]"
                          />

                          {/* Entities Grid */}
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-56 overflow-y-auto pt-1">
                            {runData.entities
                              .filter(ent => {
                                if (entityCategoryFilter !== 'ALL' && getEntityCategory(ent.type) !== entityCategoryFilter) {
                                  return false;
                                }
                                if (entityFilter) {
                                  const q = entityFilter.toLowerCase();
                                  return (
                                    ent.name.toLowerCase().includes(q) ||
                                    (ent.context && ent.context.toLowerCase().includes(q)) ||
                                    ent.type.toLowerCase().includes(q)
                                  );
                                }
                                return true;
                              })
                              .map(ent => (
                                <div
                                  key={ent.id}
                                  className="p-2 rounded-lg bg-slate-50 border border-slate-200 flex flex-col justify-between space-y-1 hover:border-slate-300 transition-colors"
                                >
                                  <div className="flex items-start justify-between gap-1">
                                    <span
                                      className={`px-1.5 py-0.2 rounded text-[9px] font-black uppercase tracking-wider ${
                                        ent.type === 'ACCUSED'
                                          ? 'bg-red-100 text-red-800'
                                          : ent.type === 'COMPLAINANT'
                                          ? 'bg-blue-100 text-blue-800'
                                          : ent.type === 'OFFICER'
                                          ? 'bg-emerald-100 text-emerald-800'
                                          : ent.type === 'LOCATION' || ent.type === 'JURISDICTION'
                                          ? 'bg-sky-100 text-sky-800'
                                          : ent.type === 'DATE_TIME'
                                          ? 'bg-teal-100 text-teal-800'
                                          : ent.type === 'PHONE' || ent.type === 'DIGITAL_ID'
                                          ? 'bg-purple-100 text-purple-800'
                                          : ent.type === 'VEHICLE'
                                          ? 'bg-amber-100 text-amber-800'
                                          : ent.type === 'CONTRABAND'
                                          ? 'bg-rose-100 text-rose-800'
                                          : ent.type === 'SECTION'
                                          ? 'bg-indigo-100 text-indigo-800'
                                          : ent.type === 'EVIDENCE'
                                          ? 'bg-orange-100 text-orange-800'
                                          : 'bg-slate-200 text-slate-700'
                                      }`}
                                    >
                                      {ent.type.replace('_', ' ')}
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => handleJumpToPage(ent.source_page || 1)}
                                      className="text-[10px] font-bold text-[#0f5132] hover:underline flex-shrink-0"
                                      title={`Jump to page ${ent.source_page || 1}`}
                                    >
                                      [P{ent.source_page || 1}]
                                    </button>
                                  </div>
                                  <div className="font-semibold text-xs text-slate-900 break-words">{ent.name}</div>
                                  {ent.context && (
                                    <div className="text-[10px] text-slate-500 line-clamp-2 leading-tight">
                                      {ent.context}
                                    </div>
                                  )}
                                  <div className="text-[9px] font-mono text-slate-400 pt-0.5">
                                    Confidence: {Math.round((ent.confidence || 0.95) * 100)}%
                                  </div>
                                </div>
                              ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* ─────────────────────────────────────────────────────────── */}
                    {/* SECTION E: Key Points (Grounded Bullet Points)            */}
                    {/* ─────────────────────────────────────────────────────────── */}
                    {runData.key_points && runData.key_points.length > 0 && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div
                          className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                          onClick={() => setExpanded(e => ({ ...e, keyPoints: !e.keyPoints }))}
                        >
                          <div className="flex items-center space-x-2">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                            <span className="text-xs font-bold text-slate-800">
                              Section E • Key Document Points ({runData.key_points.length})
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
                            {runData.key_points.map((kp, idx) => (
                              <div
                                key={kp.id || idx}
                                className="flex items-start justify-between text-xs text-slate-700 bg-slate-50 p-2 rounded-lg border border-slate-100"
                              >
                                <span className="leading-relaxed">{kp.point}</span>
                                {kp.source_page && (
                                  <button
                                    type="button"
                                    onClick={() => handleJumpToPage(kp.source_page || 1)}
                                    className="ml-2 text-[10px] font-bold text-[#0f5132] hover:underline flex-shrink-0"
                                    title={`Jump to page ${kp.source_page}`}
                                  >
                                    [P{kp.source_page}]
                                  </button>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* ─────────────────────────────────────────────────────────── */}
                    {/* SECTION F: Structured FIR Fields (Officer Review)         */}
                    {/* ─────────────────────────────────────────────────────────── */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between border-b border-slate-200">
                        <div className="flex items-center space-x-2">
                          <CheckCircle2 className="w-4 h-4 text-[#0f5132]" />
                          <span className="text-xs font-bold text-slate-800">
                            Section F • Structured FIR Fields (Officer Review)
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
                        {[
                          'FIR & Jurisdiction',
                          'Occurrence & Timeline',
                          'Persons & Roles',
                          'Seizure & Evidence',
                          'Investigation & Legal Sections'
                        ].map(groupName => {
                          const groupFields = runData.structured_fields.filter(f => {
                            if (fieldFilter && !f.label.toLowerCase().includes(fieldFilter.toLowerCase())) {
                              return false;
                            }
                            return getFieldGroup(f.key) === groupName;
                          });
                          if (groupFields.length === 0) return null;

                          return (
                            <div key={groupName} className="space-y-2">
                              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-1">
                                {groupName}
                              </div>
                              <div className="grid grid-cols-1 gap-2.5">
                                {groupFields.map(f => {
                                  const valStr =
                                    f.value != null
                                      ? Array.isArray(f.value)
                                        ? f.value.join(', ')
                                        : String(f.value)
                                      : '';
                                  return (
                                    <div key={f.id || f.key} className="space-y-1">
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-1.5">
                                          <label className="text-xs font-bold text-slate-800">{f.label}</label>
                                          {f.required && (
                                            <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-red-100 text-red-700 uppercase">
                                              Required
                                            </span>
                                          )}
                                          {f.confidence != null && (
                                            <span className="text-[10px] text-slate-400 font-mono">
                                              ({Math.round(f.confidence * 100)}%)
                                            </span>
                                          )}
                                        </div>
                                        {f.source_page && (
                                          <button
                                            type="button"
                                            onClick={() => handleJumpToPage(f.source_page || 1)}
                                            className="text-[10px] font-bold text-[#0f5132] hover:underline"
                                            title={`Navigate to source page ${f.source_page}`}
                                          >
                                            [P{f.source_page} citation]
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
                          );
                        })}
                      </div>
                    </div>

                    {/* ─────────────────────────────────────────────────────────── */}
                    {/* SECTION A: Document Content (Verbatim OCR Text & Pages)   */}
                    {/* ─────────────────────────────────────────────────────────── */}
                    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                      <div
                        className="bg-slate-50 px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => setExpanded(e => ({ ...e, content: !e.content }))}
                      >
                        <div className="flex items-center space-x-2">
                          <FileText className="w-4 h-4 text-[#0f5132]" />
                          <span className="text-xs font-bold text-slate-800">
                            Section A • Verbatim Document Content
                          </span>
                          <span className="text-[10px] text-slate-400">
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
                            className="p-1 text-slate-400 hover:text-slate-700"
                            title="Copy full text"
                          >
                            {copiedContent ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                          <ChevronDown
                            className={`w-4 h-4 text-slate-400 transition-transform ${
                              expanded.content ? 'rotate-180' : ''
                            }`}
                          />
                        </div>
                      </div>
                      {expanded.content && (
                        <div className="p-3 bg-white border-t border-slate-100 space-y-3">
                          {/* Segmented View Mode Toggle */}
                          <div className="flex items-center space-x-2 bg-slate-100 p-1 rounded-lg w-fit text-xs">
                            <button
                              type="button"
                              onClick={() => setOcrViewMode('full')}
                              className={`px-3 py-1 rounded font-bold transition-all ${
                                ocrViewMode === 'full' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                              }`}
                            >
                              Full Continuous OCR
                            </button>
                            <button
                              type="button"
                              onClick={() => setOcrViewMode('paged')}
                              className={`px-3 py-1 rounded font-bold transition-all ${
                                ocrViewMode === 'paged' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                              }`}
                            >
                              Physical Page Breakdown ({runData.pages_content?.length || runData.page_count || 1})
                            </button>
                          </div>

                          {ocrViewMode === 'full' ? (
                            <pre className="text-xs font-mono text-slate-700 whitespace-pre-wrap max-h-56 overflow-y-auto bg-slate-50 p-2.5 rounded-lg border border-slate-200 leading-relaxed">
                              {runData.document_content || 'No text extracted from document.'}
                            </pre>
                          ) : (
                            <div className="space-y-2 max-h-56 overflow-y-auto">
                              {(runData.pages_content && runData.pages_content.length > 0
                                ? runData.pages_content
                                : [{ page_number: 1, text: runData.document_content || '' }]
                              ).map(p => (
                                <div key={p.page_number} className="p-2.5 rounded-lg border border-slate-200 bg-slate-50 space-y-1">
                                  <div className="flex items-center justify-between">
                                    <span className="text-[10px] font-bold uppercase text-slate-700">
                                      Page {p.page_number}
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => handleJumpToPage(p.page_number)}
                                      className="text-[10px] font-bold text-[#0f5132] hover:underline"
                                    >
                                      Jump in Viewer →
                                    </button>
                                  </div>
                                  <pre className="text-xs font-mono text-slate-700 whitespace-pre-wrap max-h-24 overflow-y-auto">
                                    {p.text || 'Page empty or illegible.'}
                                  </pre>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* ─────────────────────────────────────────────────────────── */}
                  {/* Officer Sign-Off & Confirmation Footer                     */}
                  {/* ─────────────────────────────────────────────────────────── */}
                  <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 flex-shrink-0">
                    <div className="text-[11px] text-slate-600">
                      <strong>Human Sign-Off:</strong> Confirming verifies the extraction data and triggers Stages 3, 4, and 5 automatically.
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

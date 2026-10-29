import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  BookOpen,
  Save,
  CheckCircle2,
  FileDown,
  History,
  AlertCircle,
  Globe,
  RefreshCw,
  FileText,
  AlertTriangle
} from 'lucide-react';

export const CaseDiaryGenerator: React.FC = () => {
  const { t } = useLanguage();
  const [searchParams] = useSearchParams();
  const urlCaseId = searchParams.get('caseId');

  const [cases, setCases] = useState<any[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(urlCaseId || '');
  const [docLanguage, setDocLanguage] = useState<'en' | 'te' | 'hi'>('en');
  const [activeDoc, setActiveDoc] = useState<any>(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchCases = async () => {
    try {
      setLoadError(null);
      const res = await api.get('/cases/');
      setCases(res.data);
      if (!selectedCaseId && res.data.length > 0) {
        setSelectedCaseId(res.data[0].id);
      }
    } catch (e) {
      console.error('Failed to load cases:', e);
      setLoadError('The case list could not be loaded.');
    }
  };

  useEffect(() => {
    fetchCases();
  }, []);

  const loadOrCreateDraft = async (caseId: string, lang: 'en' | 'te' | 'hi' = docLanguage, forceRegen = false) => {
    if (!caseId) return;
    try {
      setLoading(true);
      setLoadError(null);
      if (!forceRegen) {
        // Check existing generated docs for matching type and language
        const res = await api.get(`/generation/case/${caseId}/documents`);
        const diaryDoc = res.data.find(
          (d: any) =>
            d.doc_type === 'CASE_DIARY' &&
            (d.language === lang || (!d.language && lang === 'en'))
        );
        // A draft from an older template is regenerated as a new version (the old one is kept)
        if (diaryDoc && !diaryDoc.is_outdated) {
          setActiveDoc(diaryDoc);
          setContent(diaryDoc.content);
          setLoading(false);
          return;
        }
      }

      // Generate new draft in requested language
      const genRes = await api.post('/generation/draft', {
        case_id: caseId,
        doc_type: 'CASE_DIARY',
        language: lang,
      });
      setActiveDoc(genRes.data);
      setContent(genRes.data.content);
    } catch (e: any) {
      console.error('Failed to load/generate case diary draft:', e);
      setLoadError(e?.response?.data?.detail || 'The case diary could not be loaded.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCaseId) {
      loadOrCreateDraft(selectedCaseId, docLanguage);
    }
  }, [selectedCaseId, docLanguage]);

  const handleLanguageSwitch = (lang: 'en' | 'te' | 'hi') => {
    if (lang === docLanguage) return;
    setDocLanguage(lang);
  };

  const handleRegenerate = async () => {
    if (!selectedCaseId) return;
    await loadOrCreateDraft(selectedCaseId, docLanguage, true);
    setSuccessMsg(
      `Re-generated draft template in ${
        docLanguage === 'te' ? 'Telugu (తెలుగు)' : docLanguage === 'hi' ? 'Hindi (हिन्दी)' : 'English'
      }.`
    );
    setTimeout(() => setSuccessMsg(null), 3500);
  };

  const handleSaveEdits = async () => {
    if (!activeDoc) return;
    try {
      setSaving(true);
      const res = await api.put(`/generation/${activeDoc.id}`, null, {
        params: { content }
      });
      setActiveDoc(res.data);
      setSuccessMsg(`Document saved as Version ${res.data.version}.`);
      setTimeout(() => setSuccessMsg(null), 3500);
    } catch (e) {
      console.error('Save edits error:', e);
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!activeDoc) return;
    try {
      setSaving(true);
      const res = await api.post(`/generation/${activeDoc.id}/approve`, {
        action: 'APPROVED',
        comments: 'Verified against departmental daily diary guidelines'
      });
      setActiveDoc(res.data);
      setSuccessMsg('Case diary approved! Ready for official export.');
      setTimeout(() => setSuccessMsg(null), 3500);
    } catch (e) {
      console.error('Approval error:', e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-blue-600" />
            <span>{t.nav.caseDiaryGenerator}</span>
          </h2>
          <p className="text-xs text-slate-500">
            Component 5: Investigation Case Diary Drafting (Section 172 CrPC / 192 BNSS)
          </p>
        </div>

        {/* Case & Language Selector */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Language Selector */}
          <div className="flex items-center bg-slate-200 p-0.5 rounded-lg text-xs font-semibold">
            <button
              onClick={() => handleLanguageSwitch('en')}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                docLanguage === 'en'
                  ? 'bg-white text-blue-700 shadow-2xs font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              English
            </button>
            <button
              onClick={() => handleLanguageSwitch('te')}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                docLanguage === 'te'
                  ? 'bg-white text-blue-700 shadow-2xs font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              తెలుగు
            </button>
            <button
              onClick={() => handleLanguageSwitch('hi')}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                docLanguage === 'hi'
                  ? 'bg-white text-blue-700 shadow-2xs font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              हिन्दी
            </button>
          </div>

          {/* Case Selector */}
          <div className="flex items-center space-x-2 text-xs">
            <span className="font-semibold text-slate-600">Case:</span>
            <select
              value={selectedCaseId}
              onChange={(e) => setSelectedCaseId(e.target.value)}
              className="border border-slate-300 rounded-lg px-3 py-1.5 bg-white text-slate-800 font-medium focus:ring-2 focus:ring-blue-500"
            >
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.fir_number} ({c.station})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {successMsg && (
        <div className="p-3 bg-emerald-50 text-emerald-800 rounded-lg border border-emerald-200 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {loadError && (
        <div className="p-3 bg-red-50 text-red-800 rounded-lg border border-red-200 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span className="flex-1">{loadError}</span>
          <button
            onClick={() => (selectedCaseId ? loadOrCreateDraft(selectedCaseId, docLanguage) : fetchCases())}
            className="px-2.5 py-1 bg-white border border-red-300 rounded-md font-semibold hover:bg-red-100"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && selectedCaseId && content.includes('/legal?caseId=') && (
        <div className="p-3 bg-amber-50 text-amber-800 rounded-lg border border-amber-200 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <span className="flex-1">Sections are pending officer acceptance.</span>
          <Link to={`/legal?caseId=${selectedCaseId}`} className="font-semibold underline">
            Open Legal Section Assistance
          </Link>
        </div>
      )}

      {/* Editor Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
              {activeDoc?.title || 'Case Diary Draft'}
            </span>
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                activeDoc?.status === 'APPROVED'
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-amber-50 text-amber-800 border-amber-200'
              }`}
            >
              {activeDoc?.status === 'APPROVED' ? 'STATUS: APPROVED' : 'STATUS: DRAFT — PENDING OFFICER REVIEW'}
            </span>
            <span className="text-[10px] text-slate-500 font-semibold bg-slate-100 px-2 py-0.5 rounded border border-slate-200 flex items-center gap-1">
              <Globe className="w-3 h-3 text-slate-400" />
              {(activeDoc?.language || docLanguage).toUpperCase()}
            </span>
            <span className="text-[10px] text-slate-400 font-mono">
              v{activeDoc?.version || 1}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleRegenerate}
              disabled={saving || loading}
              title="Regenerate template body for this case in selected language"
              className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1 border border-slate-300"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Regenerate</span>
            </button>

            <button
              onClick={handleSaveEdits}
              disabled={saving || loading}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-2xs"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? 'Saving...' : 'Save Draft'}</span>
            </button>

            {activeDoc?.status !== 'APPROVED' && (
              <button
                onClick={handleApprove}
                disabled={saving || loading}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-2xs"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Approve Document</span>
              </button>
            )}

            {activeDoc && (
              <>
                <a
                  href={`/api/v1/generation/${activeDoc.id}/export-pdf`}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-2xs"
                >
                  <FileDown className="w-3.5 h-3.5" />
                  <span>PDF</span>
                </a>

                <a
                  href={`/api/v1/generation/${activeDoc.id}/export-docx`}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-2xs"
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>DOCX</span>
                </a>
              </>
            )}
          </div>
        </div>

        {/* Textarea Editor */}
        {loading ? (
          <div className="p-12 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="text-xs text-slate-500 mt-2">
              Rendering {docLanguage === 'te' ? 'Telugu' : docLanguage === 'hi' ? 'Hindi' : 'English'} case diary template...
            </p>
          </div>
        ) : (
          <textarea
            rows={22}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full text-xs font-mono bg-slate-50 p-4 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 leading-relaxed text-slate-800"
          />
        )}
      </div>
    </div>
  );
};
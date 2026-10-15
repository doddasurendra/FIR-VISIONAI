import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  BookOpen,
  Save,
  CheckCircle2,
  FileDown,
  History,
  AlertCircle
} from 'lucide-react';

export const CaseDiaryGenerator: React.FC = () => {
  const { t } = useLanguage();
  const [searchParams] = useSearchParams();
  const urlCaseId = searchParams.get('caseId');

  const [cases, setCases] = useState<any[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(urlCaseId || '');
  const [activeDoc, setActiveDoc] = useState<any>(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    const fetchCases = async () => {
      try {
        const res = await api.get('/cases/');
        setCases(res.data);
        if (!selectedCaseId && res.data.length > 0) {
          setSelectedCaseId(res.data[0].id);
        }
      } catch (e) {
        console.error('Failed to load cases:', e);
      }
    };
    fetchCases();
  }, []);

  const loadOrCreateDraft = async (caseId: string) => {
    if (!caseId) return;
    try {
      setLoading(true);
      // Check existing generated docs
      const res = await api.get(`/generation/case/${caseId}/documents`);
      const diaryDoc = res.data.find((d: any) => d.doc_type === 'CASE_DIARY');
      if (diaryDoc) {
        setActiveDoc(diaryDoc);
        setContent(diaryDoc.content);
      } else {
        // Generate new draft
        const genRes = await api.post('/generation/draft', {
          case_id: caseId,
          doc_type: 'CASE_DIARY'
        });
        setActiveDoc(genRes.data);
        setContent(genRes.data.content);
      }
    } catch (e) {
      console.error('Failed to generate draft:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCaseId) {
      loadOrCreateDraft(selectedCaseId);
    }
  }, [selectedCaseId]);

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
      setSuccessMsg('Case diary approved! Ready for PDF download.');
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
            Component 5: Investigation Case Diary Drafting (Section 172 CrPC / BNSS)
          </p>
        </div>

        {/* Case Selector */}
        <div className="flex items-center space-x-2 text-xs">
          <span className="font-semibold text-slate-600">Select Case:</span>
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

      {successMsg && (
        <div className="p-3 bg-emerald-50 text-emerald-800 rounded-lg border border-emerald-200 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Editor Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
              {activeDoc?.title}
            </span>
            <span className="text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded">
              STATUS: {activeDoc?.status}
            </span>
            <span className="text-[10px] text-slate-400 font-mono">
              Version {activeDoc?.version}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleSaveEdits}
              disabled={saving || loading}
              className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-2xs"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? 'Saving...' : 'Save Draft Edits'}</span>
            </button>

            {activeDoc?.status !== 'APPROVED' ? (
              <button
                onClick={handleApprove}
                disabled={saving || loading}
                className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-2xs"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Approve Document</span>
              </button>
            ) : (
              <a
                href={`/api/v1/generation/${activeDoc.id}/export-pdf`}
                target="_blank"
                rel="noreferrer"
                className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-2xs"
              >
                <FileDown className="w-3.5 h-3.5" />
                <span>Export Official PDF</span>
              </a>
            )}
          </div>
        </div>

        {/* Textarea Editor */}
        {loading ? (
          <div className="p-12 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="text-xs text-slate-500 mt-2">Rendering Jinja2 case diary template...</p>
          </div>
        ) : (
          <textarea
            rows={20}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full text-xs font-mono bg-slate-50 p-4 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 leading-relaxed text-slate-800"
          />
        )}
      </div>
    </div>
  );
};

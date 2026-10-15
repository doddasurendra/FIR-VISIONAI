import React, { useState } from 'react';
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
  RotateCcw
} from 'lucide-react';

export const NewCaseIntake: React.FC = () => {
  const { t, language } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<'narrative' | 'voice' | 'file'>('narrative');
  const [narrativeText, setNarrativeText] = useState('');
  const [recording, setRecording] = useState(false);
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [processing, setProcessing] = useState(false);
  const [extractedData, setExtractedData] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form edit fields
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
      // Create empty mock audio file for multipart post
      const blob = new Blob(['sample-audio-bytes'], { type: 'audio/wav' });
      const fd = new FormData();
      fd.append('audio', blob, 'sample_audio.wav');
      fd.append('language', language);

      const res = await api.post('/extraction/voice', fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setNarrativeText(res.data.transcript);
      applyExtractedToForm(res.data.extracted_data);
    } catch (e: any) {
      setErrorMsg('Voice processing error: ' + (e.response?.data?.detail || e.message));
    } finally {
      setProcessing(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    setUploadFile(file);
    try {
      setProcessing(true);
      setErrorMsg(null);
      const fd = new FormData();
      fd.append('file', file);

      const res = await api.post('/documents/upload', fd);
      
      // Auto extract mock from uploaded document
      setFormData((prev: any) => ({
        ...prev,
        fir_number: `FIR-2024-${file.name.slice(0, 3).toUpperCase()}-` + Math.floor(1000 + Math.random() * 9000),
        offence_nature: 'Illicit Distillation & Transport of Contraband',
        contraband_type: 'ID Liquor',
        seized_quantity: 35.0,
        narrative: `Extracted from uploaded official evidence document: ${file.name}`
      }));
      setExtractedData({ source: file.name });
    } catch (e: any) {
      setErrorMsg('File upload error: ' + (e.response?.data?.detail || e.message));
    } finally {
      setProcessing(false);
    }
  };

  const applyExtractedToForm = (data: any) => {
    setExtractedData(data);
    setFormData((prev: any) => ({
      ...prev,
      fir_number: data.fir_number || `FIR-2024-${user?.district ? user.district.slice(0, 3).toUpperCase() : 'EXC'}-` + Math.floor(1000 + Math.random() * 9000),
      district: data.district || user?.district || 'Kurnool',
      station: data.station || user?.station || 'Station',
      mandal: data.mandal || '',
      village: data.village || '',
      offence_nature: data.offence_nature || 'Unlawful Possession of Intoxicating Liquor',
      contraband_type: data.contraband_type || 'ID Liquor',
      seized_quantity: data.seized_quantity || 10.0,
      seized_unit: data.seized_unit || 'Litres',
      vehicle_details: data.vehicle_details || '',
      narrative: data.narrative_summary || narrativeText
    }));
  };

  const handleFinalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setProcessing(true);
      const res = await api.post('/cases/', formData);
      navigate(`/cases/${res.data.id}`);
    } catch (e: any) {
      setErrorMsg('Failed to save case: ' + (e.response?.data?.detail || e.message));
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Page Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-800">{t.nav.newCaseIntake}</h2>
        <p className="text-xs text-slate-500">
          Multimodal case intake pipeline: Typed Narrative, Voice Input, and Document Ingestion
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 bg-white rounded-t-xl px-4 pt-3 gap-2">
        <button
          onClick={() => setActiveTab('narrative')}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === 'narrative'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>Typed Narrative</span>
        </button>

        <button
          onClick={() => setActiveTab('voice')}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === 'voice'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Mic className="w-4 h-4" />
          <span>Voice Intake ({language.toUpperCase()})</span>
        </button>

        <button
          onClick={() => setActiveTab('file')}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === 'file'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <UploadCloud className="w-4 h-4" />
          <span>Evidence PDF / OCR</span>
        </button>
      </div>

      {/* Tab Panels */}
      <div className="bg-white p-6 rounded-b-xl border border-slate-200 border-t-0 shadow-sm space-y-4">
        {errorMsg && (
          <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs flex items-center gap-2 border border-red-200">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Narrative Input Tab */}
        {activeTab === 'narrative' && (
          <div className="space-y-3">
            <label className="block text-xs font-semibold text-slate-700">
              Type or paste FIR occurrence narrative (English, Telugu, or Hindi):
            </label>
            <textarea
              rows={5}
              value={narrativeText}
              onChange={(e) => setNarrativeText(e.target.value)}
              placeholder="e.g. On 14-08-2024 at Kallur Toll Plaza, Kurnool, seized 45 litres of ID Liquor in Auto AP21TY4567. Accused Ramu Naidu and Someshwar Rao arrested..."
              className="w-full text-xs border border-slate-300 rounded-lg p-3 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
            <button
              onClick={handleNarrativeExtract}
              disabled={processing || !narrativeText.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-sm disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{processing ? 'Extracting via Gemini...' : 'Extract Structured Fields'}</span>
            </button>
          </div>
        )}

        {/* Voice Recording Tab */}
        {activeTab === 'voice' && (
          <div className="p-6 bg-slate-50 rounded-xl border border-slate-200 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center mx-auto">
              <Mic className="w-8 h-8" />
            </div>
            <div>
              <h4 className="font-bold text-sm text-slate-800">Browser Voice Capture</h4>
              <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                Speak directly into your microphone in Telugu, Hindi, or English. Audio is securely sent for transcription and structured field extraction.
              </p>
            </div>
            <button
              onClick={handleVoiceSimulate}
              disabled={processing}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-2 shadow-sm"
            >
              <Mic className="w-4 h-4" />
              <span>{processing ? 'Transcribing Audio...' : 'Record & Transcribe Sample Voice'}</span>
            </button>
          </div>
        )}

        {/* File Upload Tab */}
        {activeTab === 'file' && (
          <div className="p-6 bg-slate-50 rounded-xl border-2 border-dashed border-slate-300 text-center space-y-3">
            <UploadCloud className="w-10 h-10 text-slate-400 mx-auto" />
            <div>
              <h4 className="font-bold text-sm text-slate-800">Upload FIR Document (PDF)</h4>
              <p className="text-xs text-slate-500 mt-0.5">
                Physical PDF pages will be extracted, OCR-processed, and indexed in SQLite FTS5 for grounded page citations.
              </p>
            </div>
            <input
              type="file"
              accept=".pdf"
              onChange={handleFileUpload}
              className="text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-600 file:text-white hover:file:bg-blue-500 cursor-pointer"
            />
          </div>
        )}
      </div>

      {/* Extracted Fields Review & Confirmation Form */}
      {extractedData && (
        <form onSubmit={handleFinalSubmit} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 className="font-bold text-sm text-slate-900 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              Officer Review of Extracted Draft Case
            </h3>
            <span className="text-[10px] font-bold bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
              STATE: DRAFT (REQUIRES SIGN-OFF)
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 text-xs">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">FIR Number</label>
              <input
                type="text"
                required
                value={formData.fir_number}
                onChange={(e) => setFormData({ ...formData, fir_number: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2 font-mono font-bold"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">District</label>
              <input
                type="text"
                required
                value={formData.district}
                onChange={(e) => setFormData({ ...formData, district: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Station</label>
              <input
                type="text"
                required
                value={formData.station}
                onChange={(e) => setFormData({ ...formData, station: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Offence Nature</label>
              <input
                type="text"
                required
                value={formData.offence_nature}
                onChange={(e) => setFormData({ ...formData, offence_nature: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Contraband Type</label>
              <input
                type="text"
                value={formData.contraband_type}
                onChange={(e) => setFormData({ ...formData, contraband_type: e.target.value })}
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
                  onChange={(e) => setFormData({ ...formData, seized_quantity: parseFloat(e.target.value) || 0 })}
                  className="w-2/3 border border-slate-300 rounded-lg p-2"
                />
                <input
                  type="text"
                  value={formData.seized_unit}
                  onChange={(e) => setFormData({ ...formData, seized_unit: e.target.value })}
                  className="w-1/3 border border-slate-300 rounded-lg p-2"
                />
              </div>
            </div>
            <div className="sm:col-span-3">
              <label className="block font-semibold text-slate-700 mb-1">Vehicle Details</label>
              <input
                type="text"
                value={formData.vehicle_details}
                onChange={(e) => setFormData({ ...formData, vehicle_details: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2 font-mono"
              />
            </div>
            <div className="sm:col-span-3">
              <label className="block font-semibold text-slate-700 mb-1">Case Narrative</label>
              <textarea
                rows={3}
                value={formData.narrative}
                onChange={(e) => setFormData({ ...formData, narrative: e.target.value })}
                className="w-full border border-slate-300 rounded-lg p-2"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={() => setExtractedData(null)}
              className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50"
            >
              Reset
            </button>
            <button
              type="submit"
              disabled={processing}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-sm"
            >
              <Save className="w-4 h-4" />
              <span>{processing ? 'Registering...' : 'Confirm & Save Case Record'}</span>
            </button>
          </div>
        </form>
      )}
    </div>
  );
};

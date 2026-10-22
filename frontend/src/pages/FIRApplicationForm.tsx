import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  FileText, Save, Send, Download, ChevronLeft,
  AlertCircle, CheckCircle2, Globe, RefreshCw,
  FileJson, FileType2
} from 'lucide-react';

type Lang = 'en' | 'te' | 'hi';

const LABEL: Record<string, Record<Lang, string>> = {
  firNumber:        { en: 'FIR Number',             te: 'FIR నంబర్',              hi: 'FIR नंबर' },
  district:         { en: 'District',                te: 'జిల్లా',                hi: 'जिला' },
  station:          { en: 'Police Station / Office', te: 'స్టేషన్ / కార్యాలయం',  hi: 'స్టేషన్ / కార్యాలయం' },
  mandal:           { en: 'Mandal',                  te: 'మండలం',                 hi: 'मंडल' },
  village:          { en: 'Village',                 te: 'గ్రామం',                hi: 'गाँव' },
  locationDesc:     { en: 'Incident Location',       te: 'సంఘటన స్థానం',          hi: 'घटना स्थान' },
  offenceNature:    { en: 'Nature of Offence',       te: 'నేరం స్వభావం',          hi: 'अपराध की प्रकृति' },
  offenceCategory:  { en: 'Offence Category',        te: 'నేరం వర్గం',             hi: 'अपराध श्रेणी' },
  contrabandType:   { en: 'Contraband / Seized Item',te: 'స్వాధీనపరచిన వస్తువు',  hi: 'जब्त वस्तु' },
  seizedQty:        { en: 'Seized Quantity',         te: 'స్వాధీనపరచిన పరిమాణం', hi: 'जब्त मात्रा' },
  seizedUnit:       { en: 'Unit',                    te: 'యూనిట్',                hi: 'इकाई' },
  vehicleDetails:   { en: 'Vehicle Details',         te: 'వాహన వివరాలు',          hi: 'वाहन विवरण' },
  officerName:      { en: 'Seizing Officer Name',    te: 'అధికారి పేరు',          hi: 'अधिकारी का नाम' },
  officerRank:      { en: 'Officer Rank',            te: 'అధికారి హోదా',          hi: 'अधिकारी का पद' },
  witnesses:        { en: 'Witnesses',               te: 'సాక్షులు',              hi: 'गवाह' },
  narrative:        { en: 'Case Narrative',          te: 'కేసు వివరణ',            hi: 'मामले का विवरण' },
  incidentDate:     { en: 'Incident Date',           te: 'సంఘటన తేదీ',            hi: 'घटना तिथि' },
  applicationDate:  { en: 'Application Date',        te: 'దరఖాస్తు తేదీ',          hi: 'आवेदन तिथि' },
};

const BTN: Record<string, Record<Lang, string>> = {
  saveDraft:   { en: 'Save Draft',        te: 'ముసాయిదా సేవ్ చేయండి', hi: 'मसौदा सहेजें' },
  submit:      { en: 'Submit Application',te: 'దరఖాస్తు సమర్పించండి', hi: 'आवेदन जमा करें' },
  downloadPdf: { en: 'Download PDF',      te: 'PDF డౌన్‌లోడ్',          hi: 'PDF डाउनलोड' },
  downloadDoc: { en: 'Download Word',     te: 'Word డౌన్‌లోడ్',         hi: 'Word डाउनलोड' },
  downloadJson:{ en: 'Download JSON',     te: 'JSON డౌన్‌లోడ్',         hi: 'JSON डाउनलोड' },
};

interface FormValues {
  fir_number: string;
  district: string;
  station: string;
  mandal: string;
  village: string;
  location_description: string;
  offence_nature: string;
  offence_category: string;
  contraband_type: string;
  seized_quantity: string;
  seized_unit: string;
  vehicle_details: string;
  seizing_officer_name: string;
  seizing_officer_rank: string;
  witnesses_summary: string;
  narrative: string;
  incident_date: string;
  application_date: string;
}

const EMPTY_FORM: FormValues = {
  fir_number: '', district: '', station: '', mandal: '', village: '',
  location_description: '', offence_nature: '', offence_category: '',
  contraband_type: '', seized_quantity: '', seized_unit: 'Litres',
  vehicle_details: '', seizing_officer_name: '', seizing_officer_rank: '',
  witnesses_summary: '', narrative: '', incident_date: '', application_date: '',
};

export const FIRApplicationForm: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();

  const templateId = searchParams.get('template') || 'FIR_FORM_AP_EXCISE_v1';
  const caseId = searchParams.get('case_id') || '';
  const initialLang = (searchParams.get('lang') as Lang) || 'en';

  const [lang, setLang] = useState<Lang>(initialLang);
  const [form, setForm] = useState<FormValues>({
    ...EMPTY_FORM,
    district: user?.district || '',
    station: user?.station || '',
    application_date: new Date().toISOString().split('T')[0],
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedCaseId, setSavedCaseId] = useState<string>(caseId);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [downloading, setDownloading] = useState<string | null>(null);

  const l = (key: string) => (LABEL[key]?.[lang] || key);
  const b = (key: string) => (BTN[key]?.[lang] || key);

  const fontStyle = lang !== 'en' ? { fontFamily: '"Noto Sans Telugu", "Noto Sans Devanagari", sans-serif' } : {};

  useEffect(() => {
    if (caseId) {
      setLoading(true);
      api.get(`/fir-applications/${caseId}`).then(res => {
        const d = res.data;
        setForm({
          fir_number: d.fir_number || '',
          district: d.district || '',
          station: d.station || '',
          mandal: d.mandal || '',
          village: d.village || '',
          location_description: d.location_description || '',
          offence_nature: d.offence_nature || '',
          offence_category: d.offence_category || '',
          contraband_type: d.contraband_type || '',
          seized_quantity: d.seized_quantity?.toString() || '',
          seized_unit: d.seized_unit || 'Litres',
          vehicle_details: d.vehicle_details || '',
          seizing_officer_name: d.seizing_officer_name || '',
          seizing_officer_rank: d.seizing_officer_rank || '',
          witnesses_summary: d.witnesses_summary || '',
          narrative: d.narrative || '',
          incident_date: d.incident_date ? d.incident_date.split('T')[0] : '',
          application_date: d.application_date ? d.application_date.split('T')[0] : new Date().toISOString().split('T')[0],
        });
        if (d.form_language) setLang(d.form_language as Lang);
      }).catch(() => {}).finally(() => setLoading(false));
    }
  }, [caseId]);

  const buildPayload = (appStatus: string) => ({
    fir_number: form.fir_number || undefined,
    district: form.district,
    station: form.station,
    mandal: form.mandal || undefined,
    village: form.village || undefined,
    location_description: form.location_description || undefined,
    offence_nature: form.offence_nature || 'FIR Application',
    offence_category: form.offence_category || undefined,
    contraband_type: form.contraband_type || undefined,
    seized_quantity: form.seized_quantity ? parseFloat(form.seized_quantity) : undefined,
    seized_unit: form.seized_unit || undefined,
    vehicle_details: form.vehicle_details || undefined,
    seizing_officer_name: form.seizing_officer_name || undefined,
    seizing_officer_rank: form.seizing_officer_rank || undefined,
    witnesses_summary: form.witnesses_summary || undefined,
    narrative: form.narrative || undefined,
    incident_date: form.incident_date || undefined,
    application_date: form.application_date || undefined,
    form_template: templateId,
    form_language: lang,
    form_values_json: JSON.stringify(form),
    application_status: appStatus,
  });

  const handleSave = async (appStatus: 'DRAFT' | 'SUBMITTED') => {
    if (!form.district) { setErrorMsg('District is required.'); return; }
    if (!form.station) { setErrorMsg('Station is required.'); return; }
    setSaving(true);
    setErrorMsg('');
    setSuccessMsg('');
    try {
      let res;
      if (savedCaseId) {
        res = await api.put(`/fir-applications/${savedCaseId}`, {
          application_status: appStatus,
          form_values_json: JSON.stringify(form),
          incident_date: form.incident_date || undefined,
          form_language: lang
        });
      } else {
        res = await api.post('/fir-applications/', buildPayload(appStatus));
        setSavedCaseId(res.data.id);
      }
      setSuccessMsg(appStatus === 'DRAFT' ? 'Draft saved successfully.' : 'Application submitted successfully.');
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = async (fmt: 'pdf' | 'docx' | 'json') => {
    if (!savedCaseId) { setErrorMsg('Please save the draft first before downloading.'); return; }
    setDownloading(fmt);
    try {
      const res = await api.get(`/fir-applications/${savedCaseId}/download`, {
        params: { fmt, lang },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      const cd = res.headers['content-disposition'] || '';
      const fnMatch = cd.match(/filename="(.+)"/);
      a.href = url;
      a.download = fnMatch?.[1] || `FIR_Application.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setErrorMsg(`Download failed: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setDownloading(null);
    }
  };

  const field = (key: keyof FormValues, labelText: string, required = false, type: 'text'|'date'|'textarea'|'select' = 'text', options?: string[]) => (
    <div>
      <label className="block text-xs font-semibold text-slate-600 mb-1" style={fontStyle}>
        {labelText}{required && <span className="text-red-500 ml-1">*</span>}
      </label>
      {type === 'textarea' ? (
        <textarea
          value={form[key]}
          onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
          rows={3}
          className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132] resize-none"
          style={fontStyle}
        />
      ) : type === 'select' && options ? (
        <select
          value={form[key]}
          onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
          className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
        >
          {options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input
          type={type}
          value={form[key]}
          onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
          className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
          style={fontStyle}
        />
      )}
    </div>
  );

  if (loading) return (
    <div className="flex justify-center items-center py-24">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#0f5132]" />
    </div>
  );

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="flex items-center space-x-2 text-sm text-slate-500 hover:text-slate-800">
          <ChevronLeft className="w-4 h-4" /> <span>Back</span>
        </button>
        {/* Language switcher */}
        <div className="flex items-center space-x-1 bg-white border border-slate-200 rounded-lg p-1">
          <Globe className="w-4 h-4 text-slate-400 ml-1" />
          {(['en', 'te', 'hi'] as Lang[]).map(lCode => (
            <button
              key={lCode}
              onClick={() => setLang(lCode)}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${lang === lCode ? 'bg-[#0f5132] text-white' : 'text-slate-600 hover:bg-slate-100'}`}
              style={{ fontFamily: lCode !== 'en' ? '"Noto Sans Telugu", "Noto Sans Devanagari", sans-serif' : undefined }}
            >
              {lCode === 'en' ? 'English' : lCode === 'te' ? 'తెలుగు' : 'हिंदी'}
            </button>
          ))}
        </div>
      </div>

      {/* Form card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
        {/* Form header */}
        <div className="bg-[#0f5132] text-white rounded-t-xl px-6 py-4">
          <div className="flex items-center space-x-3">
            <FileText className="w-6 h-6" />
            <div>
              <h1 className="text-lg font-bold" style={fontStyle}>
                {lang === 'te' ? 'FIR దరఖాస్తు ఫారం' : lang === 'hi' ? 'FIR आवेदन प्रपत्र' : 'FIR Application Form'}
              </h1>
              <p className="text-xs text-green-200">AP Prohibition & Excise Department — {templateId}</p>
            </div>
          </div>
          {savedCaseId && (
            <div className="mt-2 text-xs text-green-200 font-mono">Case ID: {savedCaseId}</div>
          )}
        </div>

        <div className="p-6 space-y-6">
          {/* Status messages */}
          {successMsg && (
            <div className="flex items-center space-x-2 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}
          {errorMsg && (
            <div className="flex items-center space-x-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{errorMsg}</span>
              <button onClick={() => setErrorMsg('')} className="ml-auto text-red-500 hover:text-red-700 text-xs underline">Dismiss</button>
            </div>
          )}

          {/* Section 1: Identifiers & Jurisdiction */}
          <section>
            <h3 className="text-sm font-bold text-slate-700 mb-3 pb-1.5 border-b border-slate-200" style={fontStyle}>
              {lang === 'te' ? 'గుర్తింపు & అధికార పరిధి' : lang === 'hi' ? 'पहचान और अधिकार क्षेत्र' : 'Identification & Jurisdiction'}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {field('fir_number', l('firNumber'))}
              {field('application_date', l('applicationDate'), false, 'date')}
              {field('district', l('district'), true)}
              {field('station', l('station'), true)}
              {field('mandal', l('mandal'))}
              {field('village', l('village'))}
            </div>
          </section>

          {/* Section 2: Incident Details */}
          <section>
            <h3 className="text-sm font-bold text-slate-700 mb-3 pb-1.5 border-b border-slate-200" style={fontStyle}>
              {lang === 'te' ? 'సంఘటన వివరాలు' : lang === 'hi' ? 'घटना विवरण' : 'Incident Details'}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {field('incident_date', l('incidentDate'), false, 'date')}
              {field('offence_nature', l('offenceNature'), true)}
              {field('offence_category', l('offenceCategory'))}
              {field('location_description', l('locationDesc'), false, 'textarea')}
            </div>
          </section>

          {/* Section 3: Seized Items */}
          <section>
            <h3 className="text-sm font-bold text-slate-700 mb-3 pb-1.5 border-b border-slate-200" style={fontStyle}>
              {lang === 'te' ? 'స్వాధీన వివరాలు' : lang === 'hi' ? 'जब्त विवरण' : 'Seizure Details'}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {field('contraband_type', l('contrabandType'))}
              {field('seized_quantity', l('seizedQty'), false, 'text')}
              {field('seized_unit', l('seizedUnit'), false, 'select', ['Litres', 'Kgs', 'Bottles', 'Packets', 'Grams', 'Numbers', 'Other'])}
              {field('vehicle_details', l('vehicleDetails'))}
            </div>
          </section>

          {/* Section 4: Officer & Witnesses */}
          <section>
            <h3 className="text-sm font-bold text-slate-700 mb-3 pb-1.5 border-b border-slate-200" style={fontStyle}>
              {lang === 'te' ? 'అధికారి & సాక్షులు' : lang === 'hi' ? 'अधिकारी और गवाह' : 'Officer & Witnesses'}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {field('seizing_officer_name', l('officerName'))}
              {field('seizing_officer_rank', l('officerRank'))}
              {field('witnesses_summary', l('witnesses'), false, 'textarea')}
            </div>
          </section>

          {/* Section 5: Narrative */}
          <section>
            <h3 className="text-sm font-bold text-slate-700 mb-3 pb-1.5 border-b border-slate-200" style={fontStyle}>
              {lang === 'te' ? 'కేసు వివరణ' : lang === 'hi' ? 'मामले का विवरण' : 'Case Narrative'}
            </h3>
            {field('narrative', l('narrative'), false, 'textarea')}
          </section>
        </div>

        {/* Action bar */}
        <div className="border-t border-slate-200 px-6 py-4 bg-slate-50 rounded-b-xl flex flex-col sm:flex-row gap-3 justify-between">
          <div className="flex gap-2">
            {savedCaseId && (
              <>
                <button
                  type="button"
                  onClick={() => handleDownload('pdf')}
                  disabled={!!downloading}
                  className="flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 disabled:opacity-50"
                >
                  {downloading === 'pdf' ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                  <span>PDF</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleDownload('docx')}
                  disabled={!!downloading}
                  className="flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 disabled:opacity-50"
                >
                  {downloading === 'docx' ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <FileType2 className="w-3.5 h-3.5" />}
                  <span>Word</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleDownload('json')}
                  disabled={!!downloading}
                  className="flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 disabled:opacity-50"
                >
                  {downloading === 'json' ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <FileJson className="w-3.5 h-3.5" />}
                  <span>JSON</span>
                </button>
              </>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => handleSave('DRAFT')}
              disabled={saving}
              className="flex items-center space-x-2 px-4 py-2 text-sm font-semibold bg-white border-2 border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 disabled:opacity-50"
              style={fontStyle}
            >
              {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              <span>{b('saveDraft')}</span>
            </button>
            <button
              type="button"
              onClick={() => handleSave('SUBMITTED')}
              disabled={saving}
              className="flex items-center space-x-2 px-4 py-2 text-sm font-semibold bg-[#0f5132] text-white rounded-lg hover:bg-[#0a3d26] disabled:opacity-50"
              style={fontStyle}
            >
              {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              <span>{b('submit')}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="text-xs text-slate-400 text-center pb-4" style={fontStyle}>
        {lang === 'te' ? 'ఈ ఫారంలో నమోదు చేయబడిన సమాచారం అధికారిక రికార్డు ప్రయోజనాల కోసం మాత్రమే.' :
         lang === 'hi' ? 'इस फॉर्म में दर्ज जानकारी केवल आधिकारिक रिकॉर्ड उद्देश्यों के लिए है।' :
         'Information entered in this form is for official record purposes only. Submit only after verification.'}
      </div>
    </div>
  );
};

import React, { useState } from 'react';
import {
  X, Globe, FileText, Upload, PenLine,
  FileSearch, BookOpen, Scan
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface FIRFormSelectionModalProps {
  onClose: () => void;
}

type Language = 'en' | 'te' | 'hi';

interface Template {
  id: string;
  name: { en: string; te: string; hi: string };
  description: { en: string; te: string; hi: string };
  purpose: { en: string; te: string; hi: string };
  icon: React.ReactNode;
}

const FORM_TEMPLATES: Template[] = [
  {
    id: 'FIR_FORM_AP_EXCISE_v1',
    name: {
      en: 'AP Excise FIR Form (Standard)',
      te: 'AP ఎక్సైజ్ FIR ఫారం (ప్రామాణిక)',
      hi: 'AP आबकारी FIR प्रपत्र (मानक)',
    },
    description: {
      en: 'Standard First Information Report for AP Prohibition & Excise Department cases.',
      te: 'AP నిషేధం & ఎక్సైజ్ విభాగం కేసుల కోసం ప్రామాణిక ప్రథమ సమాచార నివేదిక.',
      hi: 'AP प्रतिषेध एवं आबकारी विभाग के मामलों के लिए मानक प्रथम सूचना रिपोर्ट।',
    },
    purpose: {
      en: 'Illicit distillation, seizures, NDPS, unlawful possession',
      te: 'అక్రమ స్వేదనం, స్వాధీనాలు, NDPS, అనధికార స్వాధీనం',
      hi: 'अवैध आसवन, जब्ती, NDPS, अनधिकृत कब्जा',
    },
    icon: <FileText className="w-5 h-5" />,
  },
  {
    id: 'NDPS_REPORT_v1',
    name: {
      en: 'NDPS / Drug Seizure Report',
      te: 'NDPS / మాదక ద్రవ్యాల స్వాధీన నివేదిక',
      hi: 'NDPS / नशीली दवाएं जब्ती रिपोर्ट',
    },
    description: {
      en: 'Report for cases under the Narcotic Drugs and Psychotropic Substances Act.',
      te: 'మత్తు మందులు మరియు సైకోట్రోపిక్ పదార్థాల చట్టం కింద కేసుల కోసం నివేదిక.',
      hi: 'स्वापक औषधि और मन:प्रभावी पदार्थ अधिनियम के अंतर्गत मामलों के लिए रिपोर्ट।',
    },
    purpose: {
      en: 'Ganja, heroin, NDPS transport, drug seizures',
      te: 'గంజాయి, హెరాయిన్, NDPS రవాణా, మాదక ద్రవ్య స్వాధీనాలు',
      hi: 'गांजा, हेरोइन, NDPS परिवहन, नशीली दवाएं जब्ती',
    },
    icon: <BookOpen className="w-5 h-5" />,
  },
  {
    id: 'HANDWRITTEN_DIGITIZE_v1',
    name: {
      en: 'Handwritten FIR Digitization',
      te: 'చేత్తో రాసిన FIR డిజిటైజేషన్',
      hi: 'हस्तलिखित FIR डिजिटीकरण',
    },
    description: {
      en: 'Upload and digitize an existing handwritten or printed FIR document.',
      te: 'ఇప్పటికే ఉన్న చేత్తో రాసిన లేదా ముద్రిత FIR పత్రాన్ని అప్‌లోడ్ చేసి డిజిటైజ్ చేయండి.',
      hi: 'मौजूदा हस्तलिखित या मुद्रित FIR दस्तावेज़ को अपलोड करें और डिजिटाइज़ करें।',
    },
    purpose: {
      en: 'Upload PDF, JPEG, PNG, WEBP — extract & verify fields via OCR',
      te: 'PDF, JPEG, PNG, WEBP అప్‌లోడ్ — OCR ద్వారా ఫీల్డ్‌లు సేకరించండి & ధృవీకరించండి',
      hi: 'PDF, JPEG, PNG, WEBP अपलोड करें — OCR के माध्यम से फ़ील्ड निकालें और सत्यापित करें',
    },
    icon: <Scan className="w-5 h-5" />,
  },
];

const LANG_OPTIONS: { code: Language; label: string; native: string }[] = [
  { code: 'en', label: 'English', native: 'English' },
  { code: 'te', label: 'Telugu', native: 'తెలుగు' },
  { code: 'hi', label: 'Hindi', native: 'हिंदी' },
];

export const FIRFormSelectionModal: React.FC<FIRFormSelectionModalProps> = ({ onClose }) => {
  const navigate = useNavigate();
  const [selectedLang, setSelectedLang] = useState<Language>('en');
  const [selectedTemplate, setSelectedTemplate] = useState<string>('FIR_FORM_AP_EXCISE_v1');

  const handleUpload = () => {
    navigate(`/intake?template=${selectedTemplate}&lang=${selectedLang}&mode=upload`);
    onClose();
  };

  const handleManual = () => {
    navigate(`/fir-application?template=${selectedTemplate}&lang=${selectedLang}&mode=manual`);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-200 bg-[#0f5132] rounded-t-2xl">
          <div className="flex items-center space-x-3">
            <FileSearch className="w-6 h-6 text-white" />
            <div>
              <h2 className="text-lg font-bold text-white">
                {selectedLang === 'te' ? 'FIR దరఖాస్తు ఫారం ఎంచుకోండి' :
                 selectedLang === 'hi' ? 'FIR आवेदन प्रपत्र चुनें' :
                 'Select FIR Application Form'}
              </h2>
              <p className="text-xs text-green-200">AP Prohibition & Excise Department</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-white/80 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Language Selection */}
          <div>
            <label className="flex items-center space-x-2 text-sm font-semibold text-slate-700 mb-2">
              <Globe className="w-4 h-4" />
              <span>
                {selectedLang === 'te' ? 'భాష ఎంచుకోండి' :
                 selectedLang === 'hi' ? 'भाषा चुनें' :
                 'Select Language'}
              </span>
            </label>
            <div className="flex gap-2">
              {LANG_OPTIONS.map(l => (
                <button
                  key={l.code}
                  onClick={() => setSelectedLang(l.code)}
                  className={`flex-1 py-2 px-3 rounded-lg border-2 text-sm font-semibold transition-all ${
                    selectedLang === l.code
                      ? 'border-[#0f5132] bg-[#0f5132]/10 text-[#0f5132]'
                      : 'border-slate-200 text-slate-600 hover:border-slate-300'
                  }`}
                  style={{ fontFamily: l.code !== 'en' ? '"Noto Sans Telugu", "Noto Sans Devanagari", sans-serif' : undefined }}
                >
                  <div>{l.native}</div>
                  <div className="text-xs font-normal opacity-70">{l.label}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Form Template Selection */}
          <div>
            <label className="flex items-center space-x-2 text-sm font-semibold text-slate-700 mb-2">
              <FileText className="w-4 h-4" />
              <span>
                {selectedLang === 'te' ? 'ఫారం టెంప్లేట్' :
                 selectedLang === 'hi' ? 'फॉर्म टेम्पलेट' :
                 'Form Template'}
              </span>
            </label>
            <div className="space-y-2">
              {FORM_TEMPLATES.map(t => (
                <button
                  key={t.id}
                  onClick={() => setSelectedTemplate(t.id)}
                  className={`w-full text-left p-3 rounded-lg border-2 transition-all ${
                    selectedTemplate === t.id
                      ? 'border-[#0f5132] bg-[#0f5132]/5'
                      : 'border-slate-200 hover:border-slate-300 bg-white'
                  }`}
                >
                  <div className="flex items-start space-x-3">
                    <div className={`mt-0.5 p-1.5 rounded-md ${selectedTemplate === t.id ? 'bg-[#0f5132] text-white' : 'bg-slate-100 text-slate-500'}`}>
                      {t.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div
                        className="font-semibold text-sm text-slate-800"
                        style={{ fontFamily: selectedLang !== 'en' ? '"Noto Sans Telugu", "Noto Sans Devanagari", sans-serif' : undefined }}
                      >
                        {t.name[selectedLang]}
                      </div>
                      <div
                        className="text-xs text-slate-500 mt-0.5 leading-relaxed"
                        style={{ fontFamily: selectedLang !== 'en' ? '"Noto Sans Telugu", "Noto Sans Devanagari", sans-serif' : undefined }}
                      >
                        {t.description[selectedLang]}
                      </div>
                      <div className="mt-1 inline-flex items-center px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full">
                        {t.purpose[selectedLang]}
                      </div>
                    </div>
                    {selectedTemplate === t.id && (
                      <div className="mt-1 w-4 h-4 rounded-full bg-[#0f5132] flex items-center justify-center flex-shrink-0">
                        <div className="w-2 h-2 rounded-full bg-white" />
                      </div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="border-t border-slate-200 pt-4 space-y-3">
            <p className="text-xs text-slate-500 text-center">
              {selectedLang === 'te' ? 'ఎంపిక చేసిన ఫారం తెరవడానికి ఒక మార్గం ఎంచుకోండి:' :
               selectedLang === 'hi' ? 'चयनित फॉर्म खोलने का तरीका चुनें:' :
               'Choose how to open the selected form:'}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={handleUpload}
                className="flex flex-col items-center p-4 bg-blue-50 border-2 border-blue-200 rounded-xl hover:bg-blue-100 hover:border-blue-300 transition-all group"
              >
                <Upload className="w-7 h-7 text-blue-600 mb-2 group-hover:scale-110 transition-transform" />
                <span
                  className="text-sm font-semibold text-blue-800 text-center leading-tight"
                  style={{ fontFamily: selectedLang !== 'en' ? '"Noto Sans Telugu", "Noto Sans Devanagari", sans-serif' : undefined }}
                >
                  {selectedLang === 'te' ? 'చేత్తో రాసిన / ముద్రిత FIR అప్‌లోడ్' :
                   selectedLang === 'hi' ? 'हस्तलिखित / मुद्रित FIR अपलोड' :
                   'Upload Handwritten / Printed FIR'}
                </span>
                <span className="text-xs text-blue-500 mt-1">PDF, JPEG, PNG, WEBP</span>
              </button>

              <button
                onClick={handleManual}
                className="flex flex-col items-center p-4 bg-[#0f5132]/5 border-2 border-[#0f5132]/30 rounded-xl hover:bg-[#0f5132]/10 hover:border-[#0f5132]/50 transition-all group"
              >
                <PenLine className="w-7 h-7 text-[#0f5132] mb-2 group-hover:scale-110 transition-transform" />
                <span
                  className="text-sm font-semibold text-[#0f5132] text-center leading-tight"
                  style={{ fontFamily: selectedLang !== 'en' ? '"Noto Sans Telugu", "Noto Sans Devanagari", sans-serif' : undefined }}
                >
                  {selectedLang === 'te' ? 'ఫారం మాన్యువల్‌గా పూరించండి' :
                   selectedLang === 'hi' ? 'फॉर्म मैन्युअल रूप से भरें' :
                   'Fill Form Manually'}
                </span>
                <span className="text-xs text-[#0f5132]/70 mt-1">
                  {selectedLang === 'te' ? 'డిజిటల్ ఫారం' :
                   selectedLang === 'hi' ? 'डिजिटल फॉर्म' :
                   'Digital form'}
                </span>
              </button>
            </div>

            <button
              onClick={onClose}
              className="w-full py-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
            >
              {selectedLang === 'te' ? 'రద్దు' : selectedLang === 'hi' ? 'रद्द करें' : 'Cancel'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

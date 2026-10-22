import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  Calendar, Search, X, Download, ExternalLink,
  ChevronLeft, ChevronRight, AlertCircle, RefreshCw,
  FileText
} from 'lucide-react';

type DateType = 'application' | 'registration' | 'incident';
type ExportFmt = 'xlsx' | 'csv' | 'json';

interface CaseItem {
  id: string;
  fir_number: string;
  district: string;
  station: string;
  offence_nature: string;
  status: string;
  application_status?: string;
  application_date?: string;
  registration_date?: string;
  incident_date?: string;
  seizing_officer_name?: string;
  form_template?: string;
}

interface SearchResult {
  total: number;
  page: number;
  limit: number;
  cases: CaseItem[];
}

interface DailySummary {
  date: string;
  date_type: string;
  total_applications: number;
  registered: number;
  drafts: number;
  under_investigation: number;
}

const STATUS_BADGE: Record<string, string> = {
  DRAFT: 'bg-yellow-100 text-yellow-800',
  SUBMITTED: 'bg-blue-100 text-blue-800',
  UNDER_REVIEW: 'bg-orange-100 text-orange-800',
  REGISTERED: 'bg-green-100 text-green-800',
  UNDER_INVESTIGATION: 'bg-purple-100 text-purple-800',
  CLOSED: 'bg-slate-100 text-slate-600',
  IN_REVIEW: 'bg-orange-100 text-orange-800',
  APPROVED: 'bg-green-100 text-green-800',
  ARCHIVED: 'bg-slate-100 text-slate-400',
};

export const DateWiseFIRSearch: React.FC = () => {
  const navigate = useNavigate();
  const { language } = useLanguage();

  const [dateMode, setDateMode] = useState<'single' | 'range'>('single');
  const [date, setDate] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [dateType, setDateType] = useState<DateType>('application');
  const [firNumber, setFirNumber] = useState('');
  const [caseId, setCaseId] = useState('');
  const [person, setPerson] = useState('');
  const [location, setLocation] = useState('');
  const [status, setStatus] = useState('');

  const [results, setResults] = useState<SearchResult | null>(null);
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState<ExportFmt | null>(null);

  const fontStyle = language !== 'en' ? { fontFamily: '"Noto Sans Telugu", "Noto Sans Devanagari", sans-serif' } : {};

  const T = {
    title: language === 'te' ? 'తేదీ వారీ FIR శోధన' : language === 'hi' ? 'तिथिवार FIR खोज' : 'Date-Wise FIR Search',
    singleDate: language === 'te' ? 'ఒక తేదీ' : language === 'hi' ? 'एक तिथि' : 'Single Date',
    dateRange: language === 'te' ? 'తేదీ పరిధి' : language === 'hi' ? 'तिथि सीमा' : 'Date Range',
    dateType: language === 'te' ? 'తేదీ రకం' : language === 'hi' ? 'तिथि प्रकार' : 'Date Type',
    applicationDate: language === 'te' ? 'దరఖాస్తు తేదీ' : language === 'hi' ? 'आवेदन तिथि' : 'Application Date',
    registrationDate: language === 'te' ? 'నమోదు తేదీ' : language === 'hi' ? 'पंजीकरण तिथि' : 'Registration Date',
    incidentDate: language === 'te' ? 'సంఘటన తేదీ' : language === 'hi' ? 'घटना तिथि' : 'Incident Date',
    search: language === 'te' ? 'శోధన' : language === 'hi' ? 'खोजें' : 'Search',
    clear: language === 'te' ? 'క్లియర్' : language === 'hi' ? 'साफ़ करें' : 'Clear Filters',
    exportResults: language === 'te' ? 'ఫలితాలు ఎగుమతి' : language === 'hi' ? 'परिणाम निर्यात' : 'Export Results',
    noRecords: language === 'te' ? 'ఎంచుకున్న తేదీ లేదా ఫిల్టర్‌లకు FIR రికార్డులు కనుగొనబడలేదు.' : language === 'hi' ? 'चुनी हुई तिथि या फ़िल्टर के लिए कोई FIR रिकॉर्ड नहीं मिला।' : 'No FIR records found for the selected date or filters.',
    totalApp: language === 'te' ? 'మొత్తం దరఖాస్తులు' : language === 'hi' ? 'कुल आवेदन' : 'Total Applications',
    registered: language === 'te' ? 'నమోదైనవి' : language === 'hi' ? 'पंजीकृत' : 'Registered',
    drafts: language === 'te' ? 'ముసాయిదాలు' : language === 'hi' ? 'मसौदे' : 'Drafts',
    underInv: language === 'te' ? 'దర్యాప్తులో' : language === 'hi' ? 'जांच में' : 'Under Investigation',
  };

  const buildParams = (p = page) => {
    const params: Record<string, string | number> = { date_type: dateType, page: p, limit: 30 };
    if (dateMode === 'single' && date) params.date = date;
    else {
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
    }
    if (firNumber) params.fir_number = firNumber;
    if (caseId) params.case_id = caseId;
    if (person) params.person = person;
    if (location) params.location = location;
    if (status) params.status = status;
    return params;
  };

  const doSearch = useCallback(async (p = 1) => {
    setLoading(true);
    setError('');
    setPage(p);
    try {
      const params = buildParams(p);
      const [resSearch, resSummary] = await Promise.all([
        api.get<SearchResult>('/fir-applications/', { params }),
        date ? api.get<DailySummary>('/fir-applications/summary', { params: { date, date_type: dateType } }) : Promise.resolve(null),
      ]);
      setResults(resSearch.data);
      setSummary(resSummary ? resSummary.data : null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Search failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [date, fromDate, toDate, dateType, firNumber, caseId, person, location, status, dateMode]);

  const handleClear = () => {
    setDate(''); setFromDate(''); setToDate('');
    setFirNumber(''); setCaseId(''); setPerson('');
    setLocation(''); setStatus('');
    setResults(null); setSummary(null); setError('');
  };

  const handleExport = async (fmt: ExportFmt) => {
    setExporting(fmt);
    try {
      const params: Record<string, string> = { fmt, date_type: dateType };
      if (dateMode === 'single' && date) params.date = date;
      else {
        if (fromDate) params.from_date = fromDate;
        if (toDate) params.to_date = toDate;
      }
      if (firNumber) params.fir_number = firNumber;
      if (status) params.status = status;
      const res = await api.get('/fir-applications/export/results', { params, responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      const cd = (res.headers['content-disposition'] as string) || '';
      const fn = cd.match(/filename="(.+)"/)?.[1] || `FIR_Results.${fmt}`;
      a.href = url;
      a.download = fn;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(`Export failed: ${err?.response?.data?.detail || 'Unknown error'}`);
    } finally {
      setExporting(null);
    }
  };

  const formatDate = (d?: string) => {
    if (!d) return '—';
    try {
      return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch {
      return d;
    }
  };

  const totalPages = results ? Math.ceil(results.total / 30) : 0;

  return (
    <div className="space-y-5 mt-6 border-t border-slate-200 pt-6">
      {/* Section header */}
      <div className="flex items-center space-x-3">
        <div className="p-2 bg-[#0f5132]/10 rounded-lg">
          <Calendar className="w-5 h-5 text-[#0f5132]" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-800" style={fontStyle}>{T.title}</h3>
          <p className="text-xs text-slate-500">Search and filter FIR records by date, status, person or location</p>
        </div>
      </div>

      {/* Filter panel */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-4 shadow-sm">
        {/* Date mode toggle */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setDateMode('single')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${dateMode === 'single' ? 'bg-[#0f5132] text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            style={fontStyle}
          >
            {T.singleDate}
          </button>
          <button
            type="button"
            onClick={() => setDateMode('range')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${dateMode === 'range' ? 'bg-[#0f5132] text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            style={fontStyle}
          >
            {T.dateRange}
          </button>
          <select
            value={dateType}
            onChange={e => setDateType(e.target.value as DateType)}
            className="ml-auto text-xs border border-slate-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
          >
            <option value="application">{T.applicationDate}</option>
            <option value="registration">{T.registrationDate}</option>
            <option value="incident">{T.incidentDate}</option>
          </select>
        </div>

        {/* Date inputs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {dateMode === 'single' ? (
            <div className="sm:col-span-1">
              <label className="text-xs font-medium text-slate-500 block mb-1" style={fontStyle}>
                {language === 'te' ? 'తేదీ ఎంచుకోండి' : language === 'hi' ? 'तिथि चुनें' : 'Select Date'}
              </label>
              <input
                type="date"
                value={date}
                onChange={e => setDate(e.target.value)}
                className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
              />
            </div>
          ) : (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 block mb-1" style={fontStyle}>
                  {language === 'te' ? 'ప్రారంభ తేదీ' : language === 'hi' ? 'प्रारंभ तिथि' : 'From Date'}
                </label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={e => setFromDate(e.target.value)}
                  className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 block mb-1" style={fontStyle}>
                  {language === 'te' ? 'ముగింపు తేదీ' : language === 'hi' ? 'अंत तिथि' : 'To Date'}
                </label>
                <input
                  type="date"
                  value={toDate}
                  onChange={e => setToDate(e.target.value)}
                  className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
                />
              </div>
            </>
          )}
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1">FIR Number</label>
            <input
              type="text"
              value={firNumber}
              onChange={e => setFirNumber(e.target.value)}
              placeholder="e.g. FIR-2024-KNL-001"
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1">Case ID</label>
            <input
              type="text"
              value={caseId}
              onChange={e => setCaseId(e.target.value)}
              placeholder="Internal case ID"
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1" style={fontStyle}>
              {language === 'te' ? 'వ్యక్తి శోధన' : language === 'hi' ? 'व्यक्ति खोजें' : 'Search Person'}
            </label>
            <input
              type="text"
              value={person}
              onChange={e => setPerson(e.target.value)}
              placeholder="Officer / witness name"
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1" style={fontStyle}>
              {language === 'te' ? 'స్థానం శోధన' : language === 'hi' ? 'स्थान खोजें' : 'Search Location'}
            </label>
            <input
              type="text"
              value={location}
              onChange={e => setLocation(e.target.value)}
              placeholder="Mandal / village / location"
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1" style={fontStyle}>
              {language === 'te' ? 'స్థితి ద్వారా ఫిల్టర్' : language === 'hi' ? 'स्थिति से फ़िल्टर' : 'Filter by Status'}
            </label>
            <select
              value={status}
              onChange={e => setStatus(e.target.value)}
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
            >
              <option value="">All Statuses</option>
              <option value="DRAFT">Draft</option>
              <option value="SUBMITTED">Submitted</option>
              <option value="IN_REVIEW">Under Review</option>
              <option value="APPROVED">Registered / Approved</option>
              <option value="ARCHIVED">Archived</option>
            </select>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={() => doSearch(1)}
            disabled={loading}
            className="flex items-center space-x-2 px-4 py-2 bg-[#0f5132] text-white text-sm font-semibold rounded-lg hover:bg-[#0a3d26] disabled:opacity-50"
            style={fontStyle}
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            <span>{T.search}</span>
          </button>
          <button
            type="button"
            onClick={handleClear}
            className="flex items-center space-x-2 px-4 py-2 bg-white border border-slate-300 text-slate-600 text-sm font-semibold rounded-lg hover:bg-slate-50"
            style={fontStyle}
          >
            <X className="w-4 h-4" /><span>{T.clear}</span>
          </button>
          {results && results.total > 0 && (
            <div className="ml-auto flex gap-2">
              {(['xlsx', 'csv', 'json'] as ExportFmt[]).map(fmt => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() => handleExport(fmt)}
                  disabled={!!exporting}
                  className="flex items-center space-x-1 px-3 py-2 bg-white border border-slate-300 text-slate-600 text-xs font-semibold rounded-lg hover:bg-slate-50 disabled:opacity-50"
                >
                  {exporting === fmt ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                  <span>.{fmt}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center space-x-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Summary counts */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: T.totalApp, value: summary.total_applications, color: 'bg-blue-50 border-blue-200 text-blue-800' },
            { label: T.registered, value: summary.registered, color: 'bg-green-50 border-green-200 text-green-800' },
            { label: T.drafts, value: summary.drafts, color: 'bg-yellow-50 border-yellow-200 text-yellow-800' },
            { label: T.underInv, value: summary.under_investigation, color: 'bg-purple-50 border-purple-200 text-purple-800' },
          ].map(({ label, value, color }) => (
            <div key={label} className={`rounded-lg border p-3 ${color}`}>
              <div className="text-2xl font-bold">{value}</div>
              <div className="text-xs font-semibold mt-0.5 leading-tight" style={fontStyle}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Results table */}
      {results && (
        <>
          {results.cases.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-xl border border-slate-200">
              <FileText className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <p className="text-sm font-semibold text-slate-500" style={fontStyle}>{T.noRecords}</p>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-700">
                  {results.total} {language === 'te' ? 'రికార్డులు' : language === 'hi' ? 'रिकॉर्ड' : 'records found'}
                </span>
                <span className="text-xs text-slate-400">Page {page} of {totalPages}</span>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      {['FIR Number', 'Offence', 'District / Station', 'Application Date', 'Registration Date', 'Incident Date', 'Status', 'Actions'].map(h => (
                        <th key={h} className="px-3 py-2.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {results.cases.map(c => (
                      <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-3 py-2.5 font-mono text-xs font-semibold text-[#0f5132]">{c.fir_number}</td>
                        <td className="px-3 py-2.5 text-slate-700 max-w-[160px] truncate text-xs" title={c.offence_nature}>{c.offence_nature}</td>
                        <td className="px-3 py-2.5 text-xs">
                          <div className="text-slate-700">{c.district}</div>
                          <div className="text-slate-400">{c.station}</div>
                        </td>
                        <td className="px-3 py-2.5 text-xs text-slate-600 whitespace-nowrap">{formatDate(c.application_date)}</td>
                        <td className="px-3 py-2.5 text-xs text-slate-600 whitespace-nowrap">{formatDate(c.registration_date)}</td>
                        <td className="px-3 py-2.5 text-xs text-slate-600 whitespace-nowrap">{formatDate(c.incident_date)}</td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-semibold ${STATUS_BADGE[c.application_status || c.status] || 'bg-slate-100 text-slate-600'}`}>
                            {c.application_status || c.status}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <button
                            type="button"
                            onClick={() => navigate(`/cases/${c.id}`)}
                            className="flex items-center space-x-1 text-xs text-[#0f5132] hover:underline font-medium"
                          >
                            <ExternalLink className="w-3 h-3" />
                            <span>Open</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* Pagination */}
              {totalPages > 1 && (
                <div className="px-4 py-3 border-t border-slate-200 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => doSearch(page - 1)}
                    disabled={page <= 1 || loading}
                    className="flex items-center space-x-1 text-sm text-slate-600 hover:text-slate-900 disabled:opacity-40"
                  >
                    <ChevronLeft className="w-4 h-4" /><span>Previous</span>
                  </button>
                  <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
                  <button
                    type="button"
                    onClick={() => doSearch(page + 1)}
                    disabled={page >= totalPages || loading}
                    className="flex items-center space-x-1 text-sm text-slate-600 hover:text-slate-900 disabled:opacity-40"
                  >
                    <span>Next</span><ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

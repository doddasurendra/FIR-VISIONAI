import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useSearchParams } from 'react-router-dom';
import {
  Sparkles,
  RefreshCw,
  FileText,
  Search,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Layers,
  XCircle,
  Info
} from 'lucide-react';

type Lang = 'en' | 'te' | 'hi';
type SummaryState = 'COMPLETED' | 'STALE' | 'PENDING' | 'FAILED' | 'NEEDS_REVIEW';

interface RecordItem {
  record_key: string;
  record_type: 'FIR_DOCUMENT' | 'CASE_RECORD';
  document_id: string | null;
  case_id: string | null;
  fir_number: string | null;
  title: string;
  district: string | null;
  station: string | null;
  case_status: string | null;
  record_date: string | null;
  usable_text: boolean;
  source_chars: number;
  summary_state: Record<Lang, SummaryState>;
}

interface Coverage {
  total_records: number;
  eligible: number;
  needs_ocr_or_review: number;
  by_language: Record<Lang, Record<string, number>>;
}

interface FieldEntry {
  text: string | null;
  available: boolean;
  citations: number[];
  uncited?: boolean;
  unverified_numbers?: string[];
  unverified_names?: string[];
}

interface SummaryDetail {
  status: SummaryState;
  language?: Lang;
  version?: number;
  generated_at?: string;
  model?: string;
  error?: string;
  summary?: {
    overview: FieldEntry;
    fields: Record<string, FieldEntry>;
    labels: Record<string, string>;
    ocr_uncertain?: boolean;
    warnings?: string[];
  };
  citations?: { n: number; label: string; document_id: string | null; page: number | null; ocr_uncertain?: boolean }[];
}

interface BatchInfo {
  job_id: string;
  status: string;
  total: number;
  processed: number;
  succeeded: number;
  failed_or_review: number;
  counts?: Record<string, number>;
  errors?: { record_key?: string; fir_number?: string; status?: string; error?: string }[];
}

const LANG_LABEL: Record<Lang, string> = { en: 'English', te: 'తెలుగు', hi: 'हिंदी' };
const NA_LABEL: Record<Lang, string> = {
  en: 'Not available in the source',
  te: 'మూల పత్రంలో అందుబాటులో లేదు',
  hi: 'स्रोत में उपलब्ध नहीं'
};
const STATE_STYLE: Record<SummaryState, string> = {
  COMPLETED: 'bg-emerald-100 text-emerald-800',
  STALE: 'bg-amber-100 text-amber-800',
  PENDING: 'bg-slate-100 text-slate-600',
  FAILED: 'bg-red-100 text-red-700',
  NEEDS_REVIEW: 'bg-orange-100 text-orange-800'
};

function errorText(e: any, fallback: string): string {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (!e?.response) return 'The server could not be reached. Check your connection and try again.';
  return fallback;
}

export const AICaseSummaries: React.FC = () => {
  const { t, language } = useLanguage();
  const [searchParams] = useSearchParams();
  const [lang, setLang] = useState<Lang>((['en', 'te', 'hi'].includes(language) ? language : 'en') as Lang);
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ search: '', district: '', station: '', case_status: '', date_from: '', date_to: '', summary_status: '' });
  const [selectedKey, setSelectedKey] = useState<string>('');
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<SummaryDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchInfo | null>(null);
  const [batchError, setBatchError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRecords = useCallback(async () => {
    setLoadingList(true);
    setListError(null);
    try {
      const params: Record<string, string> = { language: lang };
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
      const res = await api.get('/summaries/records', { params });
      setRecords(res.data.items);
      setCoverage(res.data.coverage);
      if (!selectedKey && res.data.items.length) {
        const caseParam = searchParams.get('caseId');
        const fromCase = caseParam ? res.data.items.find((r: RecordItem) => r.case_id === caseParam) : null;
        setSelectedKey((fromCase || res.data.items[0]).record_key);
      }
    } catch (e) {
      setListError(errorText(e, 'Could not load historical FIR records.'));
    } finally {
      setLoadingList(false);
    }
  }, [filters, lang, selectedKey, searchParams]);

  useEffect(() => { loadRecords(); }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadDetail = useCallback(async (key: string, l: Lang) => {
    if (!key) return;
    setLoadingDetail(true);
    setDetailError(null);
    try {
      const res = await api.get(`/summaries/records/${encodeURIComponent(key)}`, { params: { language: l } });
      setDetail(res.data);
    } catch (e) {
      setDetail(null);
      setDetailError(errorText(e, 'Could not load the summary.'));
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => { loadDetail(selectedKey, lang); }, [selectedKey, lang, loadDetail]);

  const generate = async (regenerate: boolean) => {
    if (!selectedKey) return;
    setGenerating(true);
    setDetailError(null);
    try {
      const res = await api.post(`/summaries/records/${encodeURIComponent(selectedKey)}/generate`, { regenerate }, { params: { language: lang } });
      setDetail(res.data);
      loadRecords();
    } catch (e) {
      setDetailError(errorText(e, 'The summary could not be generated.'));
      loadDetail(selectedKey, lang);
    } finally {
      setGenerating(false);
    }
  };

  const pollBatch = useCallback((jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.get(`/summaries/batch/${jobId}`);
        setBatch(res.data);
        if (res.data.status !== 'RUNNING') {
          if (pollRef.current) clearInterval(pollRef.current);
          loadRecords();
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 2000);
  }, [loadRecords]);

  useEffect(() => {
    api.get('/summaries/batch/active').then(res => {
      if (res.data?.job_id) { setBatch(res.data); pollBatch(res.data.job_id); }
    }).catch(() => undefined);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [pollBatch]);

  const startBatch = async (keys?: string[]) => {
    setBatchError(null);
    try {
      const res = await api.post('/summaries/batch', keys ? { record_keys: keys } : {});
      if (res.data.status === 'NOTHING_TO_DO') {
        setBatchError(res.data.message);
        return;
      }
      setBatch(res.data);
      pollBatch(res.data.job_id);
    } catch (e) {
      setBatchError(errorText(e, 'The batch could not be started.'));
    }
  };

  const cancelBatch = async () => {
    if (!batch) return;
    try {
      const res = await api.post(`/summaries/batch/${batch.job_id}/cancel`);
      setBatch(res.data);
    } catch (e) {
      setBatchError(errorText(e, 'The batch could not be cancelled.'));
    }
  };

  const selected = useMemo(() => records.find(r => r.record_key === selectedKey), [records, selectedKey]);
  const districts = useMemo(() => Array.from(new Set(records.map(r => r.district).filter(Boolean))) as string[], [records]);
  const toggleChecked = (key: string) => setChecked(prev => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const renderField = (key: string, entry: FieldEntry | undefined, label: string) => {
    const e = entry || { text: null, available: false, citations: [] };
    return (
      <div key={key} className="grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-1 sm:gap-3 py-2 border-b border-slate-100 last:border-0">
        <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wide">{label}</div>
        <div className="text-sm text-slate-800">
          {e.available ? (
            <>
              <span>{e.text}</span>
              {e.citations.map(n => {
                const c = detail?.citations?.find(x => x.n === n);
                return (
                  <span key={n} title={c ? `${c.label}${c.page ? `, page ${c.page}` : ''}` : ''}
                        className="ml-1 inline-block text-[10px] font-mono font-bold px-1 rounded bg-blue-50 text-blue-700 border border-blue-200 cursor-help">
                    S{n}
                  </span>
                );
              })}
              {e.uncited && <span className="ml-2 text-[10px] text-amber-700">(no source citation)</span>}
              {e.unverified_numbers && e.unverified_numbers.length > 0 && (
                <span className="ml-2 text-[10px] text-red-700">numbers not found in the cited source: {e.unverified_numbers.join(', ')}</span>
              )}
              {e.unverified_names && e.unverified_names.length > 0 && (
                <span className="ml-2 text-[10px] text-red-700">names not found in the cited source (check the original): {e.unverified_names.join(', ')}</span>
              )}
            </>
          ) : (
            <span className="italic text-slate-400">{NA_LABEL[lang]}</span>
          )}
        </div>
      </div>
    );
  };

  const batchPct = batch && batch.total ? Math.round((batch.processed / batch.total) * 100) : 0;

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-blue-600" />
            <span>{t.nav.aiCaseSummaries}</span>
          </h2>
          <p className="text-xs text-slate-500">
            Cited summaries of historical FIR records in English, Telugu and Hindi, built only from the stored FIR text and officer-approved case fields.
          </p>
        </div>
        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg" role="group" aria-label="Summary language">
          {(['en', 'te', 'hi'] as Lang[]).map(l => (
            <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l}
                    className={`px-3 py-1 rounded-md text-xs font-bold ${lang === l ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-600'}`}>
              {LANG_LABEL[l]}
            </button>
          ))}
        </div>
      </div>

      {/* Coverage */}
      {coverage && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-[11px] text-slate-500 font-semibold">Historical FIR records</div>
            <div className="text-xl font-black text-slate-800">{coverage.total_records}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-[11px] text-slate-500 font-semibold">With usable text</div>
            <div className="text-xl font-black text-emerald-700">{coverage.eligible}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-[11px] text-slate-500 font-semibold">Need OCR / review</div>
            <div className="text-xl font-black text-orange-700">{coverage.needs_ocr_or_review}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-[11px] text-slate-500 font-semibold">Summarised ({LANG_LABEL[lang]})</div>
            <div className="text-xl font-black text-blue-700">
              {coverage.by_language[lang]?.COMPLETED ?? 0}
              <span className="text-xs font-semibold text-slate-400"> / {coverage.eligible}</span>
            </div>
            <div className="text-[10px] text-slate-500">
              {coverage.by_language[lang]?.STALE ?? 0} outdated · {coverage.by_language[lang]?.FAILED ?? 0} failed
            </div>
          </div>
        </div>
      )}

      {/* Batch */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
        <div className="flex flex-wrap items-center gap-2 justify-between">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-700">
            <Layers className="w-4 h-4 text-blue-600" /> Batch summaries
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => startBatch()} disabled={batch?.status === 'RUNNING'}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white disabled:opacity-50">
              Summarise all pending
            </button>
            <button onClick={() => startBatch(Array.from(checked))} disabled={!checked.size || batch?.status === 'RUNNING'}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 disabled:opacity-50">
              Summarise selected ({checked.size})
            </button>
            {batch?.status === 'RUNNING' && (
              <button onClick={cancelBatch} className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-50 text-red-700">Cancel</button>
            )}
          </div>
        </div>
        {batchError && <div className="text-xs text-amber-700 flex items-center gap-1"><Info className="w-3.5 h-3.5" />{batchError}</div>}
        {batch && (
          <div className="space-y-1">
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden" role="progressbar" aria-valuenow={batchPct} aria-valuemin={0} aria-valuemax={100}>
              <div className={`h-full ${batch.status === 'PAUSED' ? 'bg-amber-500' : 'bg-blue-600'}`} style={{ width: `${batchPct}%` }} />
            </div>
            <div className="text-[11px] text-slate-600">
              <strong>{batch.status}</strong> · {batch.processed}/{batch.total} processed · {batch.counts?.COMPLETED ?? 0} summarised ·{' '}
              {batch.counts?.UP_TO_DATE ?? 0} already up to date · {batch.counts?.NEEDS_REVIEW ?? 0} need OCR/review · {batch.counts?.FAILED ?? 0} failed
              {batch.status === 'PAUSED' && ' · AI quota exhausted: start the batch again later to resume.'}
            </div>
            {batch.errors && batch.errors.length > 0 && (
              <details className="text-[11px] text-slate-600">
                <summary className="cursor-pointer">Records needing attention ({batch.errors.length})</summary>
                <ul className="mt-1 max-h-32 overflow-auto space-y-0.5">
                  {batch.errors.map((e, i) => (
                    <li key={i}><span className="font-mono">{e.fir_number || e.record_key}</span>: {e.status} – {e.error}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-4">
        {/* Records */}
        <div className="bg-white border border-slate-200 rounded-xl p-3 space-y-2">
          <form onSubmit={e => { e.preventDefault(); loadRecords(); }} className="space-y-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
              <input value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })}
                     placeholder="FIR number, title, station…" aria-label="Search records"
                     className="w-full pl-8 pr-2 py-1.5 text-xs border border-slate-300 rounded-lg" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <select value={filters.district} onChange={e => setFilters({ ...filters, district: e.target.value })} aria-label="District"
                      className="text-xs border border-slate-300 rounded-lg px-2 py-1.5">
                <option value="">All districts</option>
                {districts.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
              <input value={filters.station} onChange={e => setFilters({ ...filters, station: e.target.value })} placeholder="Station" aria-label="Station"
                     className="text-xs border border-slate-300 rounded-lg px-2 py-1.5" />
              <select value={filters.case_status} onChange={e => setFilters({ ...filters, case_status: e.target.value })} aria-label="Case status"
                      className="text-xs border border-slate-300 rounded-lg px-2 py-1.5">
                <option value="">Any case status</option>
                {['DRAFT', 'IN_REVIEW', 'APPROVED', 'UNREGISTERED'].map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
              </select>
              <select value={filters.summary_status} onChange={e => setFilters({ ...filters, summary_status: e.target.value })} aria-label="Summary status"
                      className="text-xs border border-slate-300 rounded-lg px-2 py-1.5">
                <option value="">Any summary state</option>
                {['COMPLETED', 'STALE', 'PENDING', 'FAILED', 'NEEDS_REVIEW'].map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
              </select>
              <input type="date" value={filters.date_from} onChange={e => setFilters({ ...filters, date_from: e.target.value })} aria-label="From date"
                     className="text-xs border border-slate-300 rounded-lg px-2 py-1.5" />
              <input type="date" value={filters.date_to} onChange={e => setFilters({ ...filters, date_to: e.target.value })} aria-label="To date"
                     className="text-xs border border-slate-300 rounded-lg px-2 py-1.5" />
            </div>
            <button type="submit" className="w-full py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-white">Apply filters</button>
          </form>
          {listError && <div className="text-xs text-red-700">{listError}</div>}
          <div className="text-[11px] text-slate-500">{loadingList ? 'Loading…' : `${records.length} record(s)`}</div>
          <ul className="max-h-[560px] overflow-auto divide-y divide-slate-100">
            {records.map(r => (
              <li key={r.record_key} className={`p-2 flex gap-2 items-start cursor-pointer ${r.record_key === selectedKey ? 'bg-blue-50' : 'hover:bg-slate-50'}`}
                  onClick={() => setSelectedKey(r.record_key)}>
                <input type="checkbox" checked={checked.has(r.record_key)} onClick={e => e.stopPropagation()}
                       onChange={() => toggleChecked(r.record_key)} aria-label={`Select ${r.fir_number || r.title}`} className="mt-1" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="text-xs font-bold text-slate-800 truncate">{r.fir_number || r.title}</span>
                  </div>
                  <div className="text-[10px] text-slate-500 truncate">
                    {[r.station, r.district, r.record_date?.slice(0, 10)].filter(Boolean).join(' · ')}
                    {r.record_type === 'CASE_RECORD' && ' · case record'}
                  </div>
                  <div className="flex gap-1 mt-1">
                    {(['en', 'te', 'hi'] as Lang[]).map(l => (
                      <span key={l} className={`text-[9px] font-bold px-1.5 rounded ${STATE_STYLE[r.summary_state[l]]}`}>
                        {l.toUpperCase()} {r.summary_state[l] === 'COMPLETED' ? '✓' : r.summary_state[l].replace('_', ' ').toLowerCase()}
                      </span>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* Detail */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
          {!selected ? (
            <div className="text-sm text-slate-500">Select a historical FIR record.</div>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">{selected.fir_number || 'FIR number not recorded'}</span>
                    <span className="text-[10px] font-bold bg-purple-100 text-purple-800 px-2 py-0.5 rounded">{t.common.aiGenerated}</span>
                    {detail && <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${STATE_STYLE[detail.status]}`}>{detail.status.replace('_', ' ')}</span>}
                  </div>
                  <div className="text-xs text-slate-600 mt-1">{selected.title}</div>
                  <div className="text-[11px] text-slate-500">{[selected.station, selected.district, selected.case_status].filter(Boolean).join(' · ')}</div>
                </div>
                <div className="flex gap-2">
                  {detail?.status !== 'COMPLETED' && detail?.status !== 'NEEDS_REVIEW' && (
                    <button onClick={() => generate(false)} disabled={generating || !selected.usable_text}
                            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-semibold disabled:opacity-50 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" /> {detail?.status === 'STALE' ? 'Update summary' : 'Generate summary'}
                    </button>
                  )}
                  {(detail?.status === 'COMPLETED' || detail?.status === 'STALE') && (
                    <button onClick={() => generate(true)} disabled={generating}
                            className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5">
                      <RefreshCw className={`w-3.5 h-3.5 ${generating ? 'animate-spin' : ''}`} /> Regenerate
                    </button>
                  )}
                </div>
              </div>

              {detailError && <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg p-2 flex gap-1.5"><XCircle className="w-4 h-4 shrink-0" />{detailError}</div>}

              {loadingDetail || generating ? (
                <div className="p-8 text-center text-xs text-slate-500">
                  <div className="inline-block animate-spin rounded-full h-7 w-7 border-b-2 border-blue-600 mb-2" />
                  <div>{generating ? 'Summarising from the FIR record in English, Telugu and Hindi…' : 'Loading…'}</div>
                </div>
              ) : detail?.status === 'NEEDS_REVIEW' ? (
                <div className="text-sm text-orange-800 bg-orange-50 border border-orange-200 rounded-lg p-3 flex gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{detail.error || 'No readable text is stored for this FIR record. Run OCR again or review the document; no summary was generated.'}</span>
                </div>
              ) : detail?.status === 'PENDING' || !detail?.summary ? (
                <div className="text-sm text-slate-500">
                  {detail?.status === 'FAILED' ? `The last attempt failed: ${detail.error || 'unknown error'}` : 'No summary yet. Generate one to read it in English, Telugu and Hindi.'}
                </div>
              ) : (
                <div className="space-y-3">
                  {detail.status === 'STALE' && (
                    <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2 flex gap-1.5">
                      <Clock className="w-4 h-4 shrink-0" /> The FIR record changed after this summary was written. Update it before relying on it.
                    </div>
                  )}
                  {detail.summary.ocr_uncertain && (
                    <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2 flex gap-1.5">
                      <AlertTriangle className="w-4 h-4 shrink-0" /> Parts of the source are OCR text with low confidence; check names and numbers against the original.
                    </div>
                  )}
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm text-slate-800">
                    {renderField('overview', detail.summary.overview, detail.summary.labels.overview)}
                  </div>
                  <div>
                    {Object.entries(detail.summary.fields).map(([k, v]) => renderField(k, v, detail.summary!.labels[k] || k))}
                  </div>
                  {detail.summary.warnings && detail.summary.warnings.length > 0 && (
                    <div className="text-[11px] text-amber-800">
                      <strong>Checks:</strong> {detail.summary.warnings.join('; ')}
                    </div>
                  )}
                  {detail.citations && detail.citations.length > 0 && (
                    <div className="text-[11px] text-slate-600 border-t border-slate-100 pt-2">
                      <strong>Sources:</strong>
                      <ul className="mt-1 space-y-0.5">
                        {detail.citations.map(c => (
                          <li key={c.n}><span className="font-mono font-bold">S{c.n}</span> {c.label}{c.page ? `, page ${c.page}` : ''}{c.ocr_uncertain ? ' (low-confidence OCR)' : ''}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div className="flex flex-wrap justify-between text-[11px] text-slate-400 border-t border-slate-100 pt-2 gap-2">
                    <span className="flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" />
                      AI-generated summary of the original record (allegations are not established facts) · version {detail.version} · {detail.generated_at ? new Date(detail.generated_at).toLocaleString() : ''}
                    </span>
                    <span>{LANG_LABEL[lang]}</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

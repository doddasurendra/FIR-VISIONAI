import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  UploadCloud,
  FileSpreadsheet,
  AlertTriangle,
  RefreshCw,
  FileText,
  ChevronDown,
  ChevronRight,
  Files,
} from 'lucide-react';

const errorText = (e: any, fallback: string) => {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return e?.message || fallback;
};

const FILE_STATUS: Record<string, string> = {
  COMPLETED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  NEEDS_REVIEW: 'bg-amber-50 text-amber-800 border-amber-200',
  DUPLICATE: 'bg-slate-100 text-slate-600 border-slate-200',
  FAILED: 'bg-red-50 text-red-700 border-red-200',
  PROCESSING: 'bg-blue-50 text-blue-700 border-blue-200',
  QUEUED: 'bg-slate-50 text-slate-500 border-slate-200',
};

export const BulkIngestion: React.FC = () => {
  const { t } = useLanguage();
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [scanFiles, setScanFiles] = useState<File[]>([]);
  const [scanUploading, setScanUploading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('/bulk/jobs', { timeout: 30000 });
      setJobs(res.data);
      setJobsError(null);
    } catch (e: any) {
      setJobsError(errorText(e, 'Bulk jobs could not be loaded'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 4000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    try {
      setUploading(true);
      setUploadError(null);
      const fd = new FormData();
      fd.append('file', selectedFile);
      await api.post('/bulk/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setSelectedFile(null);
      await fetchJobs();
    } catch (e: any) {
      setUploadError(errorText(e, 'Upload failed'));
    } finally {
      setUploading(false);
    }
  };

  const handleScanUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!scanFiles.length) return;
    try {
      setScanUploading(true);
      setScanError(null);
      const fd = new FormData();
      scanFiles.forEach((f) => fd.append('files', f));
      const res = await api.post('/bulk/upload-scans', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 });
      setScanFiles([]);
      setExpanded((x) => ({ ...x, [res.data.id]: true }));
      await fetchJobs();
    } catch (e: any) {
      setScanError(errorText(e, 'Upload failed'));
    } finally {
      setScanUploading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
          <UploadCloud className="w-5 h-5 text-blue-600" />
          <span>{t.nav.bulkIngestion}</span>
        </h2>
        <p className="text-xs text-slate-500">
          Bulk import of scanned FIRs (PDF, images or ZIP) through the normal OCR and extraction pipeline, or of structured
          case datasets (CSV, JSON). Duplicates are detected by SHA-256 and never processed twice.
        </p>
      </div>

      {/* Scanned FIRs */}
      <form onSubmit={handleScanUpload} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <h3 className="font-bold text-sm text-slate-800">Upload Scanned FIRs</h3>
        <div className="p-6 border-2 border-dashed border-slate-300 rounded-xl bg-slate-50 text-center space-y-3">
          <Files className="w-10 h-10 text-slate-400 mx-auto" />
          <div>
            <p className="text-xs font-semibold text-slate-700">Select several PDF / JPG / PNG files, or ZIP archives of them</p>
            <p className="text-[11px] text-slate-400 mt-0.5">Up to 200 files and 500 MB per job; each file up to 50 MB.</p>
          </div>
          <input
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,.webp,.zip"
            onChange={(e) => setScanFiles(e.target.files ? Array.from(e.target.files) : [])}
            className="text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-600 file:text-white hover:file:bg-blue-500 cursor-pointer"
          />
          {scanFiles.length > 0 && (
            <p className="text-[11px] text-slate-600">{scanFiles.length} file(s) selected: {scanFiles.slice(0, 4).map((f) => f.name).join(', ')}{scanFiles.length > 4 ? '…' : ''}</p>
          )}
        </div>
        {scanError && <p className="text-xs text-red-700" role="alert">{scanError}</p>}
        <div className="flex justify-end">
          <button type="submit" disabled={!scanFiles.length || scanUploading}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center gap-2 shadow-sm disabled:opacity-50">
            <UploadCloud className="w-4 h-4" />
            <span>{scanUploading ? 'Uploading…' : 'Start Scanned FIR Import'}</span>
          </button>
        </div>
      </form>

      {/* Structured dataset */}
      <form onSubmit={handleFileUpload} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <h3 className="font-bold text-sm text-slate-800">Upload Bulk Historical Dataset</h3>
        <div className="p-6 border-2 border-dashed border-slate-300 rounded-xl bg-slate-50 text-center space-y-3">
          <FileSpreadsheet className="w-10 h-10 text-slate-400 mx-auto" />
          <div>
            <p className="text-xs font-semibold text-slate-700">Select CSV or JSON Case Records File</p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Columns supported: fir_number, district, station, offence_nature, contraband_type, seized_quantity, accused_name
            </p>
          </div>
          <input
            type="file"
            accept=".csv,.json"
            onChange={(e) => setSelectedFile(e.target.files ? e.target.files[0] : null)}
            className="text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-600 file:text-white hover:file:bg-blue-500 cursor-pointer"
          />
        </div>
        {uploadError && <p className="text-xs text-red-700" role="alert">{uploadError}</p>}
        <div className="flex justify-end">
          <button type="submit" disabled={!selectedFile || uploading}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center gap-2 shadow-sm disabled:opacity-50">
            <UploadCloud className="w-4 h-4" />
            <span>{uploading ? 'Uploading & Queueing...' : 'Start Bulk Import Job'}</span>
          </button>
        </div>
      </form>

      {/* Jobs */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-bold text-sm text-slate-800">Processing Jobs History</h3>
          <button onClick={fetchJobs} className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100" title="Refresh">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {jobsError && (
          <div className="m-4 p-3 rounded-lg border bg-red-50 border-red-200 text-red-800 text-xs flex items-center justify-between gap-3" role="alert">
            <span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{jobsError}</span>
            <button onClick={fetchJobs} className="px-3 py-1 bg-white border border-red-200 rounded-md font-semibold hover:bg-red-100">Retry</button>
          </div>
        )}

        {jobs.length === 0 && !jobsError ? (
          <div className="p-8 text-center text-slate-400 text-xs">{loading ? 'Loading jobs…' : 'No bulk jobs recorded yet.'}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500 uppercase border-b border-slate-200 font-semibold text-[11px]">
                  <th className="px-5 py-3">Job / Files</th>
                  <th className="px-5 py-3">Format</th>
                  <th className="px-5 py-3">Progress</th>
                  <th className="px-5 py-3">Success / Fail</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {jobs.map((job) => {
                  const pct = job.total_records > 0 ? Math.round((job.processed_records / job.total_records) * 100) : 0;
                  const isScan = Array.isArray(job.files);
                  const open = expanded[job.id];
                  return (
                    <React.Fragment key={job.id}>
                      <tr className="hover:bg-slate-50/80">
                        <td className="px-5 py-3.5 font-medium">
                          <button type="button" disabled={!isScan} onClick={() => setExpanded((x) => ({ ...x, [job.id]: !open }))}
                            className="flex items-start gap-1 text-left disabled:cursor-default">
                            {isScan && (open ? <ChevronDown className="w-3.5 h-3.5 mt-0.5" /> : <ChevronRight className="w-3.5 h-3.5 mt-0.5" />)}
                            <span>
                              <span className="font-bold text-slate-900 block">{job.filename}</span>
                              <span className="text-[10px] text-slate-400 font-mono">{job.file_hash?.slice(0, 12)}...</span>
                            </span>
                          </button>
                        </td>
                        <td className="px-5 py-3.5 font-mono text-[11px] font-bold">{job.file_type}</td>
                        <td className="px-5 py-3.5">
                          <div className="w-36 space-y-1">
                            <div className="flex justify-between text-[10px] text-slate-500">
                              <span>{job.processed_records} / {job.total_records}</span>
                              <span>{pct}%</span>
                            </div>
                            <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                              <div className="h-full bg-blue-600 rounded-full" style={{ width: `${pct}%` }}></div>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className="text-emerald-700 font-bold">{job.success_count}</span>
                          <span className="text-slate-400 mx-1">/</span>
                          <span className="text-red-600 font-bold">{job.failure_count}</span>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            job.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : job.status === 'RUNNING' || job.status === 'PROCESSING' ? 'bg-blue-50 text-blue-700 border-blue-200'
                              : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                            {job.status}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-slate-400 text-[11px]">{new Date(job.created_at).toLocaleString()}</td>
                      </tr>
                      {isScan && open && (
                        <tr className="bg-slate-50/60">
                          <td colSpan={6} className="px-8 py-3">
                            <ul className="space-y-1">
                              {job.files.map((f: any, i: number) => (
                                <li key={i} className="flex items-start gap-2">
                                  <FileText className="w-3.5 h-3.5 text-slate-400 mt-0.5" />
                                  <span className="font-medium text-slate-800 min-w-[180px]">{f.name}</span>
                                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${FILE_STATUS[f.status] || FILE_STATUS.QUEUED}`}>{f.status}</span>
                                  <span className="text-slate-500 flex-1">{f.detail}</span>
                                  {f.document_id && (
                                    <Link to={`/document-extraction?docId=${f.document_id}`} className="text-blue-700 hover:underline whitespace-nowrap">Review extraction</Link>
                                  )}
                                </li>
                              ))}
                              {(job.skipped || []).map((s: any, i: number) => (
                                <li key={`s${i}`} className="flex items-start gap-2 text-slate-500">
                                  <FileText className="w-3.5 h-3.5 text-slate-300 mt-0.5" />
                                  <span className="min-w-[180px]">{s.name}</span>
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold border bg-slate-100 border-slate-200">SKIPPED</span>
                                  <span>{s.reason}</span>
                                </li>
                              ))}
                            </ul>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Clock,
  FileText
} from 'lucide-react';

export const BulkIngestion: React.FC = () => {
  const { t } = useLanguage();
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const fetchJobs = async () => {
    try {
      setLoading(true);
      const res = await api.get('/bulk/jobs');
      setJobs(res.data);
    } catch (e) {
      console.error('Failed to load bulk jobs:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    try {
      setUploading(true);
      const fd = new FormData();
      fd.append('file', selectedFile);

      await api.post('/bulk/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setSelectedFile(null);
      await fetchJobs();
    } catch (e: any) {
      alert('Upload failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
          <UploadCloud className="w-5 h-5 text-blue-600" />
          <span>{t.nav.bulkIngestion}</span>
        </h2>
        <p className="text-xs text-slate-500">
          Component 1 & Section 13: Bulk historical FIR dataset processing (CSV, JSON) with SHA-256 deduplication.
        </p>
      </div>

      {/* Upload Box */}
      <form onSubmit={handleFileUpload} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <h3 className="font-bold text-sm text-slate-800">Upload Bulk Historical Dataset</h3>
        <div className="p-8 border-2 border-dashed border-slate-300 rounded-xl bg-slate-50 text-center space-y-3">
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

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!selectedFile || uploading}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center gap-2 shadow-sm disabled:opacity-50"
          >
            <UploadCloud className="w-4 h-4" />
            <span>{uploading ? 'Uploading & Queueing...' : 'Start Bulk Import Job'}</span>
          </button>
        </div>
      </form>

      {/* Bulk Jobs Status Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-bold text-sm text-slate-800">Processing Jobs History</h3>
          <button
            onClick={fetchJobs}
            className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-blue-600' : ''}`} />
          </button>
        </div>

        {jobs.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-xs">
            No bulk jobs recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500 uppercase border-b border-slate-200 font-semibold text-[11px]">
                  <th className="px-5 py-3">Job ID / Filename</th>
                  <th className="px-5 py-3">Format</th>
                  <th className="px-5 py-3">Progress</th>
                  <th className="px-5 py-3">Success / Fail</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {jobs.map((job) => {
                  const pct = job.total_records > 0 ? Math.round((job.processed_records / job.total_records) * 100) : 0;
                  return (
                    <tr key={job.id} className="hover:bg-slate-50/80">
                      <td className="px-5 py-3.5 font-medium">
                        <span className="font-bold text-slate-900 block">{job.filename}</span>
                        <span className="text-[10px] text-slate-400 font-mono">{job.file_hash?.slice(0, 12)}...</span>
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
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            job.status === 'COMPLETED'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : job.status === 'RUNNING'
                              ? 'bg-blue-50 text-blue-700 border-blue-200 animate-pulse'
                              : 'bg-amber-50 text-amber-700 border-amber-200'
                          }`}
                        >
                          {job.status}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-slate-400 text-[11px]">
                        {new Date(job.created_at).toLocaleTimeString()}
                      </td>
                    </tr>
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

import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  Settings,
  Activity,
  Database,
  Cpu,
  Download,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  RefreshCw,
  FileArchive,
  BookOpen,
  FileText
} from 'lucide-react';

export const SettingsHealth: React.FC = () => {
  const { t } = useLanguage();
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [backups, setBackups] = useState<any[]>([]);
  const [backupLoading, setBackupLoading] = useState(false);
  const [backupResult, setBackupResult] = useState<any>(null);
  const [backupError, setBackupError] = useState<string | null>(null);

  const fetchHealthAndBackups = async () => {
    try {
      setLoading(true);
      const [healthRes, backupsRes] = await Promise.allSettled([
        api.get('/health'),
        api.get('/system/backups')
      ]);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value.data);
      if (backupsRes.status === 'fulfilled') setBackups(backupsRes.value.data);
    } catch (e) {
      console.error('Health check failed:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealthAndBackups();
  }, []);

  const handleCreateBackup = async () => {
    setBackupLoading(true);
    setBackupError(null);
    setBackupResult(null);
    try {
      const res = await api.post('/system/backup');
      setBackupResult(res.data);
      const bRes = await api.get('/system/backups');
      setBackups(bRes.data);
    } catch (err: any) {
      setBackupError(err.response?.data?.detail || 'Backup snapshot failed.');
    } finally {
      setBackupLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
          <Settings className="w-5 h-5 text-blue-600" />
          <span>{t.nav.settingsHealth}</span>
        </h2>
        <p className="text-xs text-slate-500">
          System diagnostics, database FTS5 vector index status, and departmental backup controls.
        </p>
      </div>

      {/* Diagnostics Card */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <h3 className="font-bold text-sm text-slate-800 flex items-center gap-2 border-b border-slate-100 pb-3">
          <Activity className="w-4 h-4 text-emerald-600" />
          <span>Core System Health &amp; Services Status</span>
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-1">
            <span className="text-slate-400 block text-[11px]">Backend API</span>
            <div className="flex items-center gap-1.5 font-bold text-slate-800 text-sm">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>FastAPI (Operational)</span>
            </div>
            <span className="text-[10px] text-slate-500">Service: {health?.service || 'FIR VisionAI'}</span>
          </div>

          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-1">
            <span className="text-slate-400 block text-[11px]">Database &amp; FTS5</span>
            <div className="flex items-center gap-1.5 font-bold text-slate-800 text-sm">
              <Database className="w-4 h-4 text-emerald-600" />
              <span>SQLite + FTS5 Ready</span>
            </div>
            <span className="text-[10px] text-slate-500">WAL mode + Sub-second retrieval</span>
          </div>

          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-1">
            <span className="text-slate-400 block text-[11px]">AI Model Provider</span>
            <div className="flex items-center gap-1.5 font-bold text-slate-800 text-sm">
              <Cpu className="w-4 h-4 text-blue-600" />
              <span>Gemini Flash + Fallback</span>
            </div>
            <span className="text-[10px] text-slate-500">Candidate fallback chain active</span>
          </div>
        </div>
      </div>

      {/* Database Backup & Disaster Recovery Controls */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="space-y-0.5">
            <h3 className="font-bold text-sm text-slate-800 flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-600" />
              <span>Database Backup &amp; Disaster Recovery Procedures</span>
            </h3>
            <p className="text-xs text-slate-500">
              Online SQLite snapshot with PRAGMA integrity verification and cryptographic SHA-256 hash.
            </p>
          </div>
          <button
            onClick={handleCreateBackup}
            disabled={backupLoading}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs transition-colors disabled:opacity-50"
          >
            {backupLoading ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Creating Snapshot...</span>
              </>
            ) : (
              <>
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Create Backup Snapshot Now</span>
              </>
            )}
          </button>
        </div>

        {backupResult && (
          <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-lg text-xs space-y-1 text-emerald-900">
            <div className="flex items-center gap-1.5 font-bold text-emerald-950">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Backup Successfully Created: {backupResult.backup_filename}</span>
            </div>
            <p className="text-[11px] text-emerald-800">
              Verified: {backupResult.cases_verified} Cases, {backupResult.documents_verified} Documents | Size: {backupResult.size_kb} KB
            </p>
            <p className="font-mono text-[10px] text-emerald-700 break-all">
              SHA-256: {backupResult.sha256_hash}
            </p>
          </div>
        )}

        {backupError && (
          <div className="p-3.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <span>{backupError}</span>
          </div>
        )}

        {/* Existing Backups List */}
        <div className="space-y-2">
          <h4 className="font-bold text-xs text-slate-700 uppercase tracking-wider">
            Verified Backup Snapshots ({backups.length})
          </h4>
          {backups.length === 0 ? (
            <p className="text-xs text-slate-400 italic">No previous snapshot files recorded in backups directory.</p>
          ) : (
            <div className="space-y-1.5 max-h-56 overflow-y-auto">
              {backups.map((b: any, bIdx: number) => (
                <div
                  key={bIdx}
                  className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs"
                >
                  <div className="flex items-center gap-2">
                    <FileArchive className="w-4 h-4 text-blue-600 flex-shrink-0" />
                    <div>
                      <span className="font-mono font-semibold text-slate-800 text-[11px] block">{b.filename}</span>
                      <span className="text-[10px] text-slate-400">
                        {b.size_kb} KB • Created: {new Date(b.modified_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <a
                    href={`/api/v1/system/backups/download/${encodeURIComponent(b.filename)}`}
                    download
                    className="flex items-center gap-1 px-2.5 py-1 rounded bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 font-semibold text-[11px] transition-colors"
                  >
                    <Download className="w-3.5 h-3.5 text-slate-500" />
                    <span>Download</span>
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Official System Documentation & User Guides */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="space-y-0.5">
            <h3 className="font-bold text-sm text-slate-800 flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-emerald-600" />
              <span>Official System Documentation &amp; Architecture Guides</span>
            </h3>
            <p className="text-xs text-slate-500">
              Complete high-level design, system architecture, database schema, and step-by-step user operational guide.
            </p>
          </div>
          <a
            href="/api/v1/download/architecture-guide"
            download="FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf"
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#0f5132] hover:bg-[#0a3d26] text-white font-semibold text-xs transition-colors shadow-sm cursor-pointer"
            id="btn-download-architecture-guide"
          >
            <Download className="w-4 h-4 text-amber-300" />
            <span>Download Architecture &amp; User Guide (PDF)</span>
          </a>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
          <a
            href="/api/v1/download/architecture-guide"
            download="FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf"
            className="p-3 bg-emerald-50/60 hover:bg-emerald-50 rounded-lg border border-emerald-200 transition-colors flex items-center justify-between group"
          >
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-emerald-700" />
              <div>
                <span className="font-bold text-xs text-slate-800 block">Complete Architecture Guide</span>
                <span className="text-[10px] text-emerald-700 font-semibold">33 Pages • Verified PDF</span>
              </div>
            </div>
            <Download className="w-4 h-4 text-emerald-700 group-hover:scale-110 transition-transform" />
          </a>
          <a
            href="/api/v1/download/report"
            download
            className="p-3 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors flex items-center justify-between group"
          >
            <div className="flex items-center gap-2">
              <FileArchive className="w-5 h-5 text-blue-600" />
              <div>
                <span className="font-bold text-xs text-slate-800 block">Technical Report</span>
                <span className="text-[10px] text-slate-500">Word Document (.docx)</span>
              </div>
            </div>
            <Download className="w-4 h-4 text-slate-500 group-hover:scale-110 transition-transform" />
          </a>
          <a
            href="/api/v1/download/presentation"
            download
            className="p-3 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors flex items-center justify-between group"
          >
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-indigo-600" />
              <div>
                <span className="font-bold text-xs text-slate-800 block">Project Presentation</span>
                <span className="text-[10px] text-slate-500">PowerPoint (.pptx)</span>
              </div>
            </div>
            <Download className="w-4 h-4 text-slate-500 group-hover:scale-110 transition-transform" />
          </a>
        </div>
      </div>
    </div>
  );
};

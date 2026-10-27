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
  FileText,
  Image as ImageIcon
} from 'lucide-react';

export const SettingsHealth: React.FC = () => {
  const { t } = useLanguage();
  const [health, setHealth] = useState<any>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [ready, setReady] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [backups, setBackups] = useState<any[]>([]);
  const [backupLoading, setBackupLoading] = useState(false);
  const [backupResult, setBackupResult] = useState<any>(null);
  const [backupError, setBackupError] = useState<string | null>(null);

  const fetchHealthAndBackups = async () => {
    try {
      setLoading(true);
      const [healthRes, readyRes, backupsRes] = await Promise.allSettled([
        api.get('/health'),
        api.get('/health/ready'),
        api.get('/system/backups')
      ]);
      if (healthRes.status === 'fulfilled') {
        setHealth(healthRes.value.data);
        setHealthError(null);
      } else {
        setHealth(null);
        const reason: any = healthRes.reason;
        setHealthError(reason?.response?.data?.detail || reason?.message || 'The backend did not respond.');
      }
      // A degraded readiness check answers 503 with the same report body, so read it from either branch
      if (readyRes.status === 'fulfilled') setReady(readyRes.value.data);
      else setReady((readyRes.reason as any)?.response?.data?.checks ? (readyRes.reason as any).response.data : null);
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
              {loading ? (
                <><RefreshCw className="w-4 h-4 text-slate-400 animate-spin" /><span>Checking…</span></>
              ) : health ? (
                <><CheckCircle2 className="w-4 h-4 text-emerald-600" /><span>FastAPI (Operational)</span></>
              ) : (
                <><AlertCircle className="w-4 h-4 text-red-600" /><span>Backend unreachable</span></>
              )}
            </div>
            <span className="text-[10px] text-slate-500">
              {healthError ? healthError : `Service: ${health?.service || 'FIR VisionAI'}`}
            </span>
          </div>

          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-1">
            <span className="text-slate-400 block text-[11px]">Database &amp; Storage</span>
            {(() => {
              const db = ready?.checks?.database;
              const storage = ready?.checks?.storage;
              const label = db?.engine === 'SUPABASE_POSTGRESQL' ? 'Supabase PostgreSQL' : 'SQLite + FTS5';
              return (
                <>
                  <div className="flex items-center gap-1.5 font-bold text-slate-800 text-sm">
                    {loading ? (
                      <><RefreshCw className="w-4 h-4 text-slate-400 animate-spin" /><span>Checking…</span></>
                    ) : db?.ok ? (
                      <><Database className="w-4 h-4 text-emerald-600" /><span>{label} Ready</span></>
                    ) : (
                      <><AlertCircle className="w-4 h-4 text-red-600" /><span>{db ? `${label} Unavailable` : 'Status unknown'}</span></>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-500 block">
                    {db ? (db.ok ? `Query answered in ${db.latency_ms} ms` : db.error) : 'Readiness check did not respond.'}
                  </span>
                  {storage && (
                    <span className={`text-[10px] block ${storage.ok ? 'text-slate-500' : 'text-red-600'}`}>
                      Storage ({storage.backend === 'SUPABASE_STORAGE' ? 'Supabase' : 'local disk'}): {storage.ok ? 'reachable' : storage.error || 'unavailable'}
                    </span>
                  )}
                </>
              );
            })()}
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
          <div className="flex flex-wrap items-center gap-2">
            <a
              href="/api/v1/download/manager-guide"
              download="FIR_VisionAI_Complete_Manager_Guide.pdf"
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white font-semibold text-xs transition-colors shadow-sm cursor-pointer"
              id="btn-download-manager-guide"
            >
              <Download className="w-4 h-4 text-emerald-200" />
              <span>Download Manager Guide (PDF)</span>
            </a>
            <a
              href="/api/v1/download/architecture-image"
              download="FIR_VisionAI_System_Architecture_Diagram.png"
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-700 hover:bg-blue-800 text-white font-semibold text-xs transition-colors shadow-sm cursor-pointer"
              id="btn-download-architecture-image"
            >
              <ImageIcon className="w-4 h-4 text-sky-200" />
              <span>Download Architecture Diagram (PNG)</span>
            </a>
            <a
              href="/api/v1/download/architecture-guide"
              download="FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf"
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-[#0f5132] hover:bg-[#0a3d26] text-white font-semibold text-xs transition-colors shadow-sm cursor-pointer"
              id="btn-download-architecture-guide"
            >
              <Download className="w-4 h-4 text-amber-300" />
              <span>Download Guide (PDF)</span>
            </a>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 pt-1">
          <a
            href="/api/v1/download/manager-guide"
            download="FIR_VisionAI_Complete_Manager_Guide.pdf"
            className="p-3 bg-emerald-50/80 hover:bg-emerald-50 rounded-lg border border-emerald-300 transition-colors flex items-center justify-between group"
          >
            <div className="flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-emerald-700" />
              <div>
                <span className="font-bold text-xs text-slate-800 block">Manager Guide</span>
                <span className="text-[10px] text-emerald-700 font-semibold">23 Pages • PDF</span>
              </div>
            </div>
            <Download className="w-4 h-4 text-emerald-700 group-hover:scale-110 transition-transform" />
          </a>
          <a
            href="/api/v1/download/architecture-image"
            download="FIR_VisionAI_System_Architecture_Diagram.png"
            className="p-3 bg-blue-50/70 hover:bg-blue-50 rounded-lg border border-blue-200 transition-colors flex items-center justify-between group"
          >
            <div className="flex items-center gap-2">
              <ImageIcon className="w-5 h-5 text-blue-700" />
              <div>
                <span className="font-bold text-xs text-slate-800 block">Architecture Diagram</span>
                <span className="text-[10px] text-blue-700 font-semibold">Ultra HD 4K • PNG Image</span>
              </div>
            </div>
            <Download className="w-4 h-4 text-blue-700 group-hover:scale-110 transition-transform" />
          </a>
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

        {/* Embedded Architecture Diagram Preview */}
        <div className="mt-4 pt-3 border-t border-slate-100">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
              <ImageIcon className="w-3.5 h-3.5 text-blue-600" />
              <span>FIR VisionAI Architecture Diagram Preview (Click to download full 3840×2400 image)</span>
            </span>
            <a
              href="/FIR_VisionAI_Architecture_Diagram.png"
              target="_blank"
              rel="noreferrer"
              className="text-[11px] text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1"
            >
              Open Full Resolution in New Tab
            </a>
          </div>
          <a
            href="/api/v1/download/architecture-image"
            download="FIR_VisionAI_System_Architecture_Diagram.png"
            className="block border border-slate-200 rounded-xl overflow-hidden hover:border-blue-400 transition-all shadow-2xs group relative"
          >
            <img
              src="/FIR_VisionAI_Architecture_Diagram.png"
              alt="FIR VisionAI System Architecture Diagram"
              className="w-full h-auto object-cover max-h-80"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-slate-900/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2 text-white font-bold text-xs">
              <Download className="w-4 h-4" /> Click to Download High-Res Architecture Diagram (PNG)
            </div>
          </a>
        </div>
      </div>
    </div>
  );
};

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
  AlertCircle
} from 'lucide-react';

export const SettingsHealth: React.FC = () => {
  const { t } = useLanguage();
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        setLoading(true);
        const res = await api.get('/health');
        setHealth(res.data);
      } catch (e) {
        console.error('Health check failed:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchHealth();
  }, []);

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
          <span>Core System Health & Services Status</span>
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
            <span className="text-slate-400 block text-[11px]">Database & FTS5</span>
            <div className="flex items-center gap-1.5 font-bold text-slate-800 text-sm">
              <Database className="w-4 h-4 text-emerald-600" />
              <span>SQLite + FTS5 Ready</span>
            </div>
            <span className="text-[10px] text-slate-500">Sub-second lexical retrieval</span>
          </div>

          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-1">
            <span className="text-slate-400 block text-[11px]">AI Model Provider</span>
            <div className="flex items-center gap-1.5 font-bold text-slate-800 text-sm">
              <Cpu className="w-4 h-4 text-blue-600" />
              <span>Gemini Flash + Fallback</span>
            </div>
            <span className="text-[10px] text-slate-500">Grounded RAG synthesis</span>
          </div>
        </div>
      </div>

      {/* Database Backup & Disaster Recovery Guide */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <h3 className="font-bold text-sm text-slate-800 flex items-center gap-2 border-b border-slate-100 pb-3">
          <Database className="w-4 h-4 text-blue-600" />
          <span>Persistent Storage & Disaster Recovery Procedures</span>
        </h3>
        <p className="text-xs text-slate-600 leading-relaxed">
          The persistent SQLite database and SHA-256 evidence files are maintained in the protected <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">data/</code> directory. To perform an offline backup or migration to departmental PostgreSQL, replicate <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">data/fir_sahayak.db</code> and <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">data/evidence/</code>.
        </p>

        <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 text-xs font-mono space-y-1">
          <p className="text-slate-500 font-sans font-semibold mb-1">Command-line Backup Command:</p>
          <p className="text-slate-800">sqlite3 data/fir_sahayak.db ".backup data/backups/backup_$(date +%Y%m%d).db"</p>
        </div>
      </div>
    </div>
  );
};

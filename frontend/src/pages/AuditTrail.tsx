import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import {
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Hash,
  Lock,
  User,
  Clock
} from 'lucide-react';

export const AuditTrail: React.FC = () => {
  const { t } = useLanguage();
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState<any>(null);

  const fetchLogs = async () => {
    try {
      setLoading(true);
      const res = await api.get('/audit/');
      setLogs(res.data);
    } catch (e) {
      console.error('Failed to load audit logs:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const handleVerifyChain = async () => {
    try {
      setVerifying(true);
      const res = await api.get('/audit/verify-integrity');
      setVerificationResult(res.data);
    } catch (e) {
      console.error('Integrity check error:', e);
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-blue-600" />
            <span>{t.nav.auditTrail}</span>
          </h2>
          <p className="text-xs text-slate-500">
            Section 15: Tamper-Evident SHA-256 Recursive Hash Chain for Chain-of-Custody & Evidence Integrity
          </p>
        </div>

        <button
          onClick={handleVerifyChain}
          disabled={verifying}
          className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors border border-slate-700"
        >
          <Lock className="w-4 h-4 text-emerald-400" />
          <span>{verifying ? 'Verifying Recalculated Hashes...' : 'Verify Cryptographic Hash Chain'}</span>
        </button>
      </div>

      {/* Verification Result Banner */}
      {verificationResult && (
        <div
          className={`p-4 rounded-xl border flex items-start gap-3 text-xs ${
            verificationResult.is_chain_intact
              ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
              : 'bg-red-50 border-red-200 text-red-900'
          }`}
        >
          {verificationResult.is_chain_intact ? (
            <ShieldCheck className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          )}
          <div className="space-y-1">
            <h4 className="font-bold text-sm">
              {verificationResult.is_chain_intact
                ? 'Cryptographic Hash Chain Verified: 100% Intact & Untampered'
                : 'Integrity Violation Detected!'}
            </h4>
            <p className="leading-relaxed">
              Verified {verificationResult.verified_entries_count} consecutive event nodes using{' '}
              <strong className="font-mono">{verificationResult.algorithm}</strong>. Every entry hash strictly validates against its preceding block digest from genesis.
            </p>
            <span className="text-[10px] text-slate-500 font-mono block">
              Auditor: @{verificationResult.verified_by_actor}
            </span>
          </div>
        </div>
      )}

      {/* Audit Log Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500 uppercase border-b border-slate-200 font-semibold text-[11px]">
                  <th className="px-5 py-3">Block ID & Timestamp</th>
                  <th className="px-5 py-3">Actor</th>
                  <th className="px-5 py-3">Action Event</th>
                  <th className="px-5 py-3">Target Object</th>
                  <th className="px-5 py-3 font-mono">SHA-256 Entry Hash Link</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {logs.map((entry) => (
                  <tr key={entry.id} className="hover:bg-slate-50/80">
                    <td className="px-5 py-3.5">
                      <div className="font-bold text-slate-900 font-mono">#{entry.id}</div>
                      <div className="text-[11px] text-slate-400">
                        {new Date(entry.timestamp).toLocaleString()}
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="font-semibold text-slate-800">@{entry.actor_username}</div>
                      <div className="text-[10px] text-slate-400 font-mono">{entry.actor_id.slice(0, 8)}...</div>
                    </td>
                    <td className="px-5 py-3.5 font-semibold">
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-100 text-slate-800 border border-slate-200">
                        {entry.action_type}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="font-medium text-slate-800">{entry.object_type}</div>
                      <div className="text-[10px] text-slate-400 font-mono">{entry.object_id.slice(0, 12)}...</div>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-[11px]">
                      <div className="text-blue-700 font-bold truncate max-w-xs" title={entry.entry_hash}>
                        {entry.entry_hash}
                      </div>
                      <div className="text-slate-400 text-[10px] truncate max-w-xs">
                        prev: {entry.previous_entry_hash}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

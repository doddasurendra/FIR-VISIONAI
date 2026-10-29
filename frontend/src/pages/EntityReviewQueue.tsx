import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { LoadError, errorMessage } from '../components/common/LoadError';
import { useLanguage } from '../context/LanguageContext';
import {
  UsersRound,
  CheckCircle2,
  XCircle,
  GitMerge,
  ArrowRight,
  ShieldCheck,
  AlertCircle
} from 'lucide-react';

export const EntityReviewQueue: React.FC = () => {
  const { t } = useLanguage();
  const [candidates, setCandidates] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchCandidates = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const res = await api.get('/entities/review-queue');
      setCandidates(res.data);
    } catch (e) {
      console.error('Failed to load review queue:', e);
      setLoadError(errorMessage(e, 'The review queue could not be loaded.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, []);

  const handleMerge = async (primaryId: string, secondaryId: string) => {
    try {
      setActionError(null);
      await api.post('/entities/merge', {
        primary_entity_id: primaryId,
        secondary_entity_id: secondaryId
      });
      setActionSuccess('Entities merged successfully into canonical profile. Associated case edges updated.');
      setTimeout(() => setActionSuccess(null), 4000);
      await fetchCandidates();
    } catch (e) {
      console.error('Merge error:', e);
      setActionError(errorMessage(e, 'The merge could not be completed.'));
    }
  };

  // Saved and audited, so the pair is not suggested again
  const handleKeepSeparate = async (pair: any) => {
    try {
      setActionError(null);
      await api.post('/entities/keep-separate', {
        entity_1_id: pair.entity_1.id,
        entity_2_id: pair.entity_2.id,
      });
      setCandidates((prev) => prev.filter((p) => p.pair_id !== pair.pair_id));
      setActionSuccess('Recorded: these are different entities and will not be suggested as duplicates again.');
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (e) {
      console.error('Keep separate error:', e);
      setActionError(errorMessage(e, 'The decision could not be saved.'));
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
          <UsersRound className="w-5 h-5 text-blue-600" />
          <span>{t.nav.entityReviewQueue}</span>
        </h2>
        <p className="text-xs text-slate-500">
          Component 4: RapidFuzz & attribute similarity review. Resolve candidate duplicate suspect and vehicle records.
        </p>
      </div>

      {actionSuccess && (
        <div className="p-3.5 bg-emerald-50 text-emerald-800 rounded-xl border border-emerald-200 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {actionError && <LoadError message={actionError} onRetry={fetchCandidates} />}

      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="text-xs text-slate-500 mt-2">Scanning entity mentions for candidate matches...</p>
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={fetchCandidates} />
      ) : candidates.length === 0 ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200 text-slate-500 text-xs">
          <ShieldCheck className="w-10 h-10 text-emerald-500 mx-auto mb-2" />
          <p className="font-semibold text-slate-700">All entity profiles are verified and deduplicated</p>
          <p className="text-slate-400 mt-0.5">No unresolved candidate duplicate entities found in queue.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {candidates.map((pair) => (
            <div
              key={pair.pair_id}
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4"
            >
              <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                <span className="text-xs font-semibold text-slate-600">
                  Candidate Match Type: <strong className="text-slate-900">{pair.entity_1.type}</strong>
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-blue-700 font-mono bg-blue-50 px-2.5 py-1 rounded border border-blue-200">
                    Similarity: {Math.round(pair.similarity_score * 100)}%
                  </span>
                </div>
              </div>

              {/* Side-by-Side Candidates Comparison */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                {/* Candidate A (Primary) */}
                <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] font-bold text-blue-700 uppercase">Primary Record</span>
                    <span className="font-mono text-[10px] text-slate-400">ID: {pair.entity_1.id.slice(0, 8)}</span>
                  </div>
                  <h4 className="font-bold text-sm text-slate-900">{pair.entity_1.name}</h4>
                  <div className="space-y-1 text-slate-600 text-[11px]">
                    <div>Address / Village: <span className="font-medium text-slate-800">{pair.entity_1.attributes?.village || pair.entity_1.attributes?.address || '—'}</span></div>
                    <div>District: <span className="font-medium text-slate-800">{pair.entity_1.attributes?.district || '—'}</span></div>
                    <div>Phone / Details: <span className="font-medium text-slate-800">{pair.entity_1.attributes?.phone || '—'}</span></div>
                  </div>
                </div>

                {/* Candidate B (Duplicate) */}
                <div className="p-4 bg-amber-50/50 rounded-lg border border-amber-200 space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] font-bold text-amber-800 uppercase">Candidate Duplicate</span>
                    <span className="font-mono text-[10px] text-slate-400">ID: {pair.entity_2.id.slice(0, 8)}</span>
                  </div>
                  <h4 className="font-bold text-sm text-slate-900">{pair.entity_2.name}</h4>
                  <div className="space-y-1 text-slate-600 text-[11px]">
                    <div>Address / Village: <span className="font-medium text-slate-800">{pair.entity_2.attributes?.village || pair.entity_2.attributes?.address || '—'}</span></div>
                    <div>District: <span className="font-medium text-slate-800">{pair.entity_2.attributes?.district || '—'}</span></div>
                    <div>Phone / Details: <span className="font-medium text-slate-800">{pair.entity_2.attributes?.phone || '—'}</span></div>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex justify-end gap-3 pt-2">
                <button
                  onClick={() => handleKeepSeparate(pair)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 hover:bg-slate-50 rounded-lg text-xs font-semibold transition-colors"
                >
                  Keep Entities Separate
                </button>

                <button
                  onClick={() => handleMerge(pair.entity_1.id, pair.entity_2.id)}
                  className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors"
                >
                  <GitMerge className="w-4 h-4" />
                  <span>Confirm Merge into Canonical Profile</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

import React, { useState, useEffect, useCallback } from 'react';
import {
  Share2,
  Users,
  Car,
  MapPin,
  Building,
  Phone,
  Package,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Edit3,
  RefreshCw,
  ExternalLink,
  Filter,
  Layers,
  FileText,
  X,
  Info,
  Check
} from 'lucide-react';
import api from '../../api/client';
import { NetworkGraph } from '../network/NetworkGraph';

interface Stage6ModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseId: string | null;
  firNumber?: string | null;
  onRefreshWorkflow?: () => void;
}

export const Stage6NetworkIntelligenceModal: React.FC<Stage6ModalProps> = ({
  isOpen,
  onClose,
  caseId,
  firNumber,
  onRefreshWorkflow
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'matches' | 'entities' | 'graph'>('matches');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [entityFilter, setEntityFilter] = useState<string>('ALL');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [actionProcessing, setActionProcessing] = useState<string | null>(null);
  const [correctionTarget, setCorrectionTarget] = useState<any | null>(null);
  const [correctedNameInput, setCorrectedNameInput] = useState<string>('');

  const fetchIntelligence = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = caseId
        ? `/entities/case/${caseId}/stage6-intelligence`
        : '/entities/stage6-intelligence';
      const res = await api.get(url);
      setData(res.data);
    } catch (err: any) {
      console.error('Stage 6 fetch error:', err);
      setError(err?.response?.data?.detail || 'Failed to load Stage 6 criminal network intelligence.');
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    if (isOpen) {
      fetchIntelligence();
    }
  }, [isOpen, fetchIntelligence]);

  const handleDecision = async (entityId: string, decision: 'CONFIRM' | 'REJECT' | 'CORRECT', correctedName?: string) => {
    if (!caseId && !data?.case_id) return;
    const targetCaseId = caseId || data?.case_id;
    setActionProcessing(entityId);
    try {
      await api.post('/entities/matches/decision', {
        case_id: targetCaseId,
        entity_id: entityId,
        decision,
        corrected_name: correctedName || undefined,
        notes: `Officer action '${decision}' via Stage 6 Intake Pipeline`
      });
      // Refresh local intelligence
      await fetchIntelligence();
      if (onRefreshWorkflow) onRefreshWorkflow();
    } catch (err: any) {
      alert('Error updating decision: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setActionProcessing(null);
      setCorrectionTarget(null);
    }
  };

  if (!isOpen) return null;

  const stats = data?.stats || { total_entities: 0, repeat_appearances_count: 0, connected_cases_count: 0 };
  const repeatAppearances = data?.repeat_appearances || [];
  const identifiedEntities = data?.identified_entities || {};
  const graphNodes = data?.graph_data?.nodes || [];
  const graphEdges = data?.graph_data?.edges || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-900/70 backdrop-blur-xs overflow-y-auto animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-6xl max-h-[92vh] flex flex-col overflow-hidden">
        
        {/* ── MODAL HEADER ── */}
        <div className="bg-[#112d4e] text-white px-6 py-4 flex items-center justify-between border-b border-slate-700">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-purple-600/30 border border-purple-400/40 flex items-center justify-center text-purple-300 shadow-inner">
              <Share2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-400/30">
                  Stage 6 Intelligence
                </span>
                <span className="text-[10px] font-mono text-slate-300">
                  {data?.fir_number ? `Case: ${data.fir_number}` : (firNumber ? `Case: ${firNumber}` : 'Case Intake')}
                </span>
                {data?.district && (
                  <span className="text-[10px] text-slate-400">
                    • {data.district} {data.station ? `(${data.station})` : ''}
                  </span>
                )}
              </div>
              <h1 className="text-base font-bold text-white leading-tight mt-0.5">
                Repeat Offender & Criminal Network Intelligence
              </h1>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={fetchIntelligence}
              disabled={loading}
              className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-slate-200 transition-colors"
              title="Refresh Analysis"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-slate-200 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* ── HUMAN-IN-THE-LOOP ADVISORY SAFEGUARD NOTICE ── */}
        <div className="bg-amber-50/90 border-b border-amber-200 px-6 py-2.5 flex items-start space-x-2.5 text-xs text-amber-900">
          <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <div className="leading-snug">
            <strong>Human-in-the-Loop Safeguard:</strong> Proposed repeat appearances, matching attributes, and network connections are advisory intelligence derived from authorized police records. Similarity scores do not establish guilt or criminality. Independent officer verification and sign-off are required.
          </div>
        </div>

        {/* ── TOP KPI BAR ── */}
        <div className="bg-slate-50 border-b border-slate-200 px-6 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-6 text-xs">
            <div className="flex items-center space-x-2">
              <span className="text-slate-500">Case Entities:</span>
              <span className="font-bold text-slate-900 bg-white px-2 py-0.5 rounded border border-slate-200 font-mono">
                {stats.total_entities}
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-slate-500">Potential Repeat Appearances:</span>
              <span className={`font-bold px-2 py-0.5 rounded border font-mono ${
                stats.repeat_appearances_count > 0 ? 'bg-amber-100 text-amber-800 border-amber-300' : 'bg-white text-slate-700 border-slate-200'
              }`}>
                {stats.repeat_appearances_count}
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-slate-500">Connected Prior Cases:</span>
              <span className="font-bold text-slate-900 bg-white px-2 py-0.5 rounded border border-slate-200 font-mono">
                {stats.connected_cases_count}
              </span>
            </div>
          </div>

          {/* Subtabs Navigation */}
          <div className="flex items-center space-x-1 bg-slate-200/80 p-0.5 rounded-lg text-xs font-semibold">
            <button
              onClick={() => setActiveSubTab('matches')}
              className={`px-3 py-1.5 rounded-md transition-all ${
                activeSubTab === 'matches'
                  ? 'bg-white text-purple-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Repeat Matches ({repeatAppearances.length})
            </button>
            <button
              onClick={() => setActiveSubTab('entities')}
              className={`px-3 py-1.5 rounded-md transition-all ${
                activeSubTab === 'entities'
                  ? 'bg-white text-purple-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Identified Entities ({stats.total_entities})
            </button>
            <button
              onClick={() => setActiveSubTab('graph')}
              className={`px-3 py-1.5 rounded-md transition-all ${
                activeSubTab === 'graph'
                  ? 'bg-white text-purple-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Network Graph ({graphNodes.length})
            </button>
          </div>
        </div>

        {/* ── MODAL BODY ── */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center space-y-3">
              <RefreshCw className="w-8 h-8 text-purple-600 animate-spin" />
              <p className="text-sm font-semibold text-slate-600">
                Scanning authorized police records for repeat offender matches & cross-case linkages...
              </p>
            </div>
          ) : error ? (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                <span>{error}</span>
              </div>
              <button
                onClick={fetchIntelligence}
                className="px-3 py-1 bg-red-600 text-white rounded text-xs font-bold hover:bg-red-700"
              >
                Retry
              </button>
            </div>
          ) : data?.insufficient_data ? (
            /* ── INSUFFICIENT DATA DISPLAY ── */
            <div className="p-10 text-center bg-slate-50 rounded-2xl border border-slate-200 space-y-3 my-6">
              <div className="w-12 h-12 rounded-full bg-slate-200 text-slate-500 flex items-center justify-center mx-auto">
                <Info className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-800">
                Insufficient authorized case data to identify relationships
              </h3>
              <p className="text-xs text-slate-500 max-w-lg mx-auto">
                Repeat appearance and criminal network intelligence requires at least two registered cases or extracted case entities within your authorized jurisdiction. All analyses are strictly grounded in verified database records.
              </p>
            </div>
          ) : (
            <>
              {/* ── TAB 1: REPEAT MATCHES & LINK ANALYSIS ── */}
              {activeSubTab === 'matches' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                        Cross-Case Repeat Offender & Entity Matches
                      </h3>
                      <p className="text-[11px] text-slate-500">
                        {data?.message || 'Extracted entities cross-referenced against historical authorized FIRs'}
                      </p>
                    </div>
                    <span className="text-[11px] font-semibold text-slate-500">
                      Showing {repeatAppearances.length} candidate linkage(s)
                    </span>
                  </div>

                  {repeatAppearances.length === 0 ? (
                    <div className="p-8 text-center bg-emerald-50/50 rounded-xl border border-emerald-200 space-y-2">
                      <ShieldCheck className="w-8 h-8 text-emerald-600 mx-auto" />
                      <h4 className="text-xs font-bold text-emerald-900">No Repeat Offender Matches Found</h4>
                      <p className="text-[11px] text-emerald-700 max-w-md mx-auto">
                        None of the entities in this FIR match prior criminal records or co-accused networks in your authorized jurisdiction.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {repeatAppearances.map((match: any) => {
                        const isConfirmed = match.verification_status === 'CONFIRMED';
                        const isRejected = match.verification_status === 'REJECTED';
                        const isPending = !isConfirmed && !isRejected;

                        const badgeColor = isConfirmed
                          ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                          : isRejected
                          ? 'bg-red-100 text-red-800 border-red-300'
                          : match.match_type === 'POSSIBLE_ENTITY_MATCH'
                          ? 'bg-blue-100 text-blue-800 border-blue-300'
                          : 'bg-amber-100 text-amber-800 border-amber-300';

                        return (
                          <div
                            key={match.entity_id}
                            className={`p-4 rounded-xl border transition-all ${
                              isConfirmed
                                ? 'bg-emerald-50/30 border-emerald-300'
                                : isRejected
                                ? 'bg-slate-50 border-slate-300 opacity-60'
                                : 'bg-white border-amber-300 ring-1 ring-amber-100 shadow-xs'
                            }`}
                          >
                            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-100 pb-3">
                              <div className="flex items-start space-x-3">
                                <div className={`p-2 rounded-lg mt-0.5 ${
                                  match.entity_type === 'PERSON' ? 'bg-blue-100 text-blue-700' :
                                  match.entity_type === 'VEHICLE' ? 'bg-amber-100 text-amber-700' :
                                  'bg-purple-100 text-purple-700'
                                }`}>
                                  {match.entity_type === 'PERSON' && <Users className="w-4 h-4" />}
                                  {match.entity_type === 'VEHICLE' && <Car className="w-4 h-4" />}
                                  {match.entity_type !== 'PERSON' && match.entity_type !== 'VEHICLE' && <Share2 className="w-4 h-4" />}
                                </div>
                                <div>
                                  <div className="flex items-center space-x-2">
                                    <h4 className="font-bold text-sm text-slate-900">
                                      {match.canonical_name}
                                    </h4>
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${badgeColor}`}>
                                      {isRejected ? 'REJECTED LINK' : match.match_label}
                                    </span>
                                    <span className="text-[10px] font-mono text-slate-500">
                                      Type: {match.entity_type}
                                    </span>
                                  </div>
                                  <div className="text-[11px] text-slate-500 flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                                    <span>Recorded in {match.appearance_count} independent case(s)</span>
                                    <span>•</span>
                                    <span>Confidence: {Math.round(match.confidence_score * 100)}%</span>
                                    {match.source_evidence && (
                                      <>
                                        <span>•</span>
                                        <span className="text-slate-600 font-medium">
                                          Evidence: {match.source_evidence.doc_name} (Pg {match.source_evidence.page_number})
                                        </span>
                                      </>
                                    )}
                                  </div>
                                </div>
                              </div>

                              {/* Officer Action Buttons */}
                              <div className="flex items-center space-x-1.5 self-end md:self-auto">
                                <button
                                  type="button"
                                  disabled={actionProcessing === match.entity_id}
                                  onClick={() => handleDecision(match.entity_id, 'CONFIRM')}
                                  className={`px-2.5 py-1 text-xs font-bold rounded-lg border inline-flex items-center space-x-1 transition-colors ${
                                    isConfirmed
                                      ? 'bg-emerald-600 text-white border-emerald-600'
                                      : 'bg-white hover:bg-emerald-50 text-emerald-700 border-emerald-300'
                                  }`}
                                  title="Confirm this repeat offender / entity match"
                                >
                                  <CheckCircle2 className="w-3.5 h-3.5" />
                                  <span>{isConfirmed ? 'Verified' : 'Confirm Match'}</span>
                                </button>

                                <button
                                  type="button"
                                  disabled={actionProcessing === match.entity_id}
                                  onClick={() => handleDecision(match.entity_id, 'REJECT')}
                                  className={`px-2.5 py-1 text-xs font-semibold rounded-lg border inline-flex items-center space-x-1 transition-colors ${
                                    isRejected
                                      ? 'bg-red-600 text-white border-red-600'
                                      : 'bg-white hover:bg-red-50 text-red-600 border-red-300'
                                  }`}
                                  title="Reject false identity match (protect against incorrect merge)"
                                >
                                  <XCircle className="w-3.5 h-3.5" />
                                  <span>Reject Link</span>
                                </button>

                                <button
                                  type="button"
                                  onClick={() => {
                                    setCorrectionTarget(match);
                                    setCorrectedNameInput(match.canonical_name);
                                  }}
                                  className="px-2 py-1 text-xs font-semibold rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 inline-flex items-center space-x-1"
                                  title="Correct identity spelling or attributes"
                                >
                                  <Edit3 className="w-3.5 h-3.5" />
                                  <span>Correct</span>
                                </button>
                              </div>
                            </div>

                            {/* Matching Attributes & Linked Cases Table */}
                            <div className="mt-3 pt-2 text-xs space-y-2">
                              {/* Attribute pills */}
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-[10px] uppercase font-bold text-slate-400">Match Evidence:</span>
                                {Object.entries(match.matching_attributes || {}).map(([k, v]) => (
                                  <span key={k} className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                                    {k.replace('_', ' ')}: <strong>{String(v)}</strong>
                                  </span>
                                ))}
                              </div>

                              {/* Prior Cases Table */}
                              <div className="border border-slate-200 rounded-lg overflow-hidden bg-slate-50/50">
                                <table className="w-full text-left text-[11px]">
                                  <thead className="bg-slate-100/80 text-slate-600 font-bold border-b border-slate-200">
                                    <tr>
                                      <th className="px-3 py-1.5">Prior Case FIR</th>
                                      <th className="px-3 py-1.5">Station / Jurisdiction</th>
                                      <th className="px-3 py-1.5">Recorded Role</th>
                                      <th className="px-3 py-1.5">Incident Date</th>
                                      <th className="px-3 py-1.5">Source Evidence Citation</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-100 text-slate-700">
                                    {(match.related_cases || []).map((rc: any, idx: number) => (
                                      <tr key={idx} className="hover:bg-white transition-colors">
                                        <td className="px-3 py-1.5 font-mono font-bold text-purple-900">
                                          {rc.fir_number}
                                        </td>
                                        <td className="px-3 py-1.5">
                                          {rc.district} • {rc.station}
                                        </td>
                                        <td className="px-3 py-1.5">
                                          <span className="px-1.5 py-0.5 rounded bg-purple-100 text-purple-800 font-semibold text-[10px]">
                                            {rc.role_in_case}
                                          </span>
                                        </td>
                                        <td className="px-3 py-1.5 text-slate-500 font-mono">
                                          {rc.date ? new Date(rc.date).toLocaleDateString('en-IN') : 'Recorded'}
                                        </td>
                                        <td className="px-3 py-1.5 text-slate-600">
                                          <span className="inline-flex items-center space-x-1">
                                            <FileText className="w-3 h-3 text-slate-400" />
                                            <span>{rc.citation}</span>
                                          </span>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ── TAB 2: IDENTIFIED ENTITIES IN CURRENT CASE ── */}
              {activeSubTab === 'entities' && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                        Structured Entities Identified in Case Evidence
                      </h3>
                      <p className="text-[11px] text-slate-500">
                        Extracted people, conveyances, crime spots, contact identifiers, and seized items
                      </p>
                    </div>

                    {/* Filter by Entity Type */}
                    <div className="flex items-center space-x-1 bg-slate-100 p-0.5 rounded-lg text-xs">
                      {['ALL', 'PERSON', 'VEHICLE', 'LOCATION', 'PHONE', 'ORGANIZATION', 'PROPERTY'].map(t => (
                        <button
                          key={t}
                          onClick={() => setEntityFilter(t)}
                          className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-all ${
                            entityFilter === t ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                          }`}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Entity Cards Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {Object.entries(identifiedEntities).flatMap(([type, list]: [string, any]) => {
                      if (entityFilter !== 'ALL' && entityFilter !== type) return [];
                      return list.map((ent: any) => (
                        <div key={ent.entity_id} className="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs space-y-2">
                          <div className="flex items-start justify-between">
                            <div className="flex items-center space-x-2">
                              <span className={`p-1.5 rounded-md ${
                                ent.entity_type === 'PERSON' ? 'bg-blue-100 text-blue-700' :
                                ent.entity_type === 'VEHICLE' ? 'bg-amber-100 text-amber-700' :
                                ent.entity_type === 'LOCATION' ? 'bg-emerald-100 text-emerald-700' :
                                ent.entity_type === 'PHONE' ? 'bg-cyan-100 text-cyan-700' :
                                'bg-purple-100 text-purple-700'
                              }`}>
                                {ent.entity_type === 'PERSON' && <Users className="w-3.5 h-3.5" />}
                                {ent.entity_type === 'VEHICLE' && <Car className="w-3.5 h-3.5" />}
                                {ent.entity_type === 'LOCATION' && <MapPin className="w-3.5 h-3.5" />}
                                {ent.entity_type === 'PHONE' && <Phone className="w-3.5 h-3.5" />}
                                {ent.entity_type === 'PROPERTY' && <Package className="w-3.5 h-3.5" />}
                                {ent.entity_type === 'ORGANIZATION' && <Building className="w-3.5 h-3.5" />}
                              </span>
                              <div>
                                <h5 className="font-bold text-xs text-slate-900 leading-tight">
                                  {ent.canonical_name}
                                </h5>
                                <span className="text-[10px] font-mono text-slate-500">
                                  Role: {ent.role_in_case}
                                </span>
                              </div>
                            </div>
                            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                              {ent.entity_type}
                            </span>
                          </div>

                          {/* Source citation */}
                          <div className="text-[10px] text-slate-500 bg-slate-50 p-1.5 rounded border border-slate-100 flex items-center justify-between">
                            <span>Evidence Citation:</span>
                            <span className="font-semibold text-slate-700">{ent.citation}</span>
                          </div>
                        </div>
                      ));
                    })}
                  </div>
                </div>
              )}

              {/* ── TAB 3: INTERACTIVE NETWORK GRAPH ── */}
              {activeSubTab === 'graph' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                        Interactive Criminal Relationship Graph
                      </h3>
                      <p className="text-[11px] text-slate-500">
                        Nodes represent accused individuals, vehicles, crime spots, and prior cases; red edges highlight repeat offender appearances
                      </p>
                    </div>
                  </div>

                  <div className="h-[420px] bg-slate-50 rounded-xl border border-slate-200 overflow-hidden relative">
                    <NetworkGraph
                      nodes={graphNodes}
                      edges={graphEdges}
                      onSelectNode={(nodeId) => setSelectedNodeId(nodeId)}
                      selectedFilter="ALL"
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* ── CORRECTION MODAL / PROMPT (IF TRIGGERED) ── */}
        {correctionTarget && (
          <div className="absolute inset-0 z-60 bg-black/50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-2xl max-w-md w-full space-y-3 animate-in fade-in zoom-in-95 duration-100">
              <h4 className="font-bold text-sm text-slate-900 flex items-center space-x-2">
                <Edit3 className="w-4 h-4 text-purple-600" />
                <span>Correct Entity Identity</span>
              </h4>
              <p className="text-xs text-slate-500">
                Correct the canonical spelling or identity of <strong>{correctionTarget.canonical_name}</strong>. This correction will be permanently logged in the audit trail.
              </p>
              <input
                type="text"
                value={correctedNameInput}
                onChange={(e) => setCorrectedNameInput(e.target.value)}
                placeholder="Corrected Name"
                className="w-full text-xs px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-600 font-semibold"
              />
              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setCorrectionTarget(null)}
                  className="px-3 py-1.5 text-xs text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => handleDecision(correctionTarget.entity_id, 'CORRECT', correctedNameInput)}
                  className="px-3.5 py-1.5 text-xs font-bold text-white bg-purple-700 hover:bg-purple-800 rounded-lg"
                >
                  Save Correction & Sign Off
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── FOOTER ── */}
        <div className="bg-slate-50 border-t border-slate-200 px-6 py-3 flex items-center justify-between text-xs">
          <div className="text-slate-500 text-[11px] flex items-center space-x-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>Audit trail active • Decisions recorded with officer ID & timestamp</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-900 text-white font-bold rounded-lg transition-colors"
          >
            Close Intelligence
          </button>
        </div>

      </div>
    </div>
  );
};

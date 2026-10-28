import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { NetworkGraph } from '../components/network/NetworkGraph';
import {
  Share2,
  Users,
  Car,
  MapPin,
  Building,
  Phone,
  Info,
  ShieldAlert,
  Search,
  ExternalLink,
  Layers,
  Filter,
  CheckCircle2,
  ShieldCheck
} from 'lucide-react';

export const EntityNetwork: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [graphData, setGraphData] = useState<any>({
    nodes: [],
    edges: [],
    communities: [],
    available_cases: [],
    selected_case: null
  });
  const [loading, setLoading] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string>('ALL');
  const [selectedFilter, setSelectedFilter] = useState('ALL');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEntityProfile, setSelectedEntityProfile] = useState<any>(null);

  const fetchGraph = useCallback(async (caseIdFilter: string) => {
    try {
      setLoading(true);
      const url = caseIdFilter !== 'ALL'
        ? `/entities/network-graph?case_id=${encodeURIComponent(caseIdFilter)}`
        : '/entities/network-graph';
      const res = await api.get(url);
      setGraphData(res.data);
      // Reset selected entity if it is not present in new dataset
      setSelectedNodeId(null);
      setSelectedEntityProfile(null);
    } catch (e) {
      console.error('Failed to load network graph:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGraph(selectedCaseId);
  }, [selectedCaseId, fetchGraph]);

  const handleNodeClick = async (nodeId: string) => {
    setSelectedNodeId(nodeId);
    if (nodeId.startsWith('vehicle:')) {
      // A vehicle linked only through the registration recorded on cases has no entity record of its own
      const node = graphData.nodes?.find((n: any) => n.id === nodeId);
      setSelectedEntityProfile({ entity: { canonical_name: node?.label, entity_type: 'VEHICLE', risk_score: 0,
        verification_status: 'LINKED BY REGISTRATION' }, linked_cases: [] });
      return;
    }
    try {
      const res = await api.get(`/entities/${nodeId}`);
      setSelectedEntityProfile(res.data);
    } catch (e) {
      console.error('Failed to fetch entity profile:', e);
    }
  };

  const selectedNode = graphData.nodes?.find((n: any) => n.id === selectedNodeId);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Share2 className="w-5 h-5 text-blue-600" />
            <span>{t.nav.entityNetwork}</span>
            {selectedCaseId !== 'ALL' ? (
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 font-mono font-bold">
                Single FIR Mode
              </span>
            ) : (
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-semibold">
                Cross-Case Intelligence
              </span>
            )}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Evidence-based entity graph connecting Accused, Conveyances, Crime Locations, Organisations, and Contact Numbers.
          </p>
        </div>

        {/* Top Controls: FIR Case Selector & Entity Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Case Scope Dropdown */}
          <div className="flex items-center space-x-1.5 bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-slate-600 font-semibold">Case Scope:</span>
            <select
              value={selectedCaseId}
              onChange={(e) => setSelectedCaseId(e.target.value)}
              className="bg-transparent font-medium text-slate-800 focus:outline-none cursor-pointer"
            >
              <option value="ALL">All Permitted Cases (Cross-Case)</option>
              {graphData.available_cases?.map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.fir_number} ({c.station || c.district})
                </option>
              ))}
            </select>
          </div>

          {/* Filter Pills with Phone beside Organisation */}
          <div className="flex flex-wrap items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs">
            {[
              { id: 'ALL', label: 'ALL' },
              { id: 'PERSON', label: 'Persons' },
              { id: 'VEHICLE', label: 'Vehicles' },
              { id: 'LOCATION', label: 'Locations' },
              { id: 'ORGANIZATION', label: 'Organisations' },
              { id: 'PHONE', label: 'Phone Numbers' }
            ].map((ft) => (
              <button
                key={ft.id}
                onClick={() => setSelectedFilter(ft.id)}
                className={`px-2.5 py-1 rounded font-semibold transition-colors ${
                  selectedFilter === ft.id
                    ? 'bg-blue-600 text-white shadow-2xs'
                    : 'text-slate-600 hover:bg-slate-200/70'
                }`}
              >
                {ft.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Graph & Inspector Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 h-[650px]">
        {/* Left: Interactive Vis-Network Canvas */}
        <div className="lg:col-span-3 bg-white rounded-xl border border-slate-200 shadow-sm relative overflow-hidden flex flex-col">
          {loading ? (
            <div className="flex-1 flex flex-col items-center justify-center space-y-2">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <span className="text-xs text-slate-500 font-medium">Resolving entity network graph...</span>
            </div>
          ) : (
            <div className="flex-1 w-full h-full relative">
              <NetworkGraph
                nodes={graphData.nodes || []}
                edges={graphData.edges || []}
                onSelectNode={handleNodeClick}
                selectedFilter={selectedFilter}
              />

              {/* Legend Overlay */}
              <div className="absolute bottom-4 left-4 bg-white/95 backdrop-blur-sm p-3 rounded-lg border border-slate-200 shadow-md text-[11px] space-y-1.5 pointer-events-none z-10">
                <span className="font-bold text-slate-700 block mb-1">Entity Color Coding:</span>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block"></span>
                  <span>Person (Accused / Witness)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block"></span>
                  <span>Vehicle / Conveyance</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block"></span>
                  <span>Location (Scene of Crime)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block"></span>
                  <span>Organisation / Syndicate</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-cyan-500 inline-block"></span>
                  <span>Phone Number</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Selected Node / Community Lead Inspector */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 overflow-y-auto flex flex-col text-xs space-y-4">
          <h3 className="font-bold text-sm text-slate-800 border-b border-slate-100 pb-2 flex items-center justify-between">
            <span>Entity Lead Inspector</span>
            {selectedEntityProfile && (
              <span className="text-[10px] bg-blue-100 text-blue-800 font-mono px-2 py-0.5 rounded font-bold">
                {selectedEntityProfile.entity?.entity_type}
              </span>
            )}
          </h3>

          {selectedEntityProfile ? (
            <div className="space-y-4">
              <div>
                <span className="text-slate-400 block text-[11px]">Canonical Identity</span>
                <h4 className="font-bold text-base text-slate-900 break-words">
                  {selectedNode?.label || selectedEntityProfile.entity?.canonical_name}
                </h4>
                {selectedEntityProfile.entity?.entity_type === 'PHONE' && (
                  <p className="text-[10px] text-slate-500 mt-0.5 flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-cyan-600" />
                    <span>Evidence-extracted contact number</span>
                  </p>
                )}
              </div>

              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-500">Risk Assessment:</span>
                  <span className="font-bold text-blue-700">{selectedEntityProfile.entity?.risk_score}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Verification Status:</span>
                  <span className="font-semibold text-emerald-700">{selectedEntityProfile.entity?.verification_status}</span>
                </div>
                {selectedNode?.case_count != null && (
                  <div className="flex justify-between">
                    <span className="text-slate-500">Observed Cases:</span>
                    <span className="font-bold text-slate-800">{selectedNode.case_count} FIR(s)</span>
                  </div>
                )}
              </div>

              {/* Source Cases & Mentions */}
              <div>
                <h5 className="font-bold text-xs text-slate-800 mb-2">
                  Linked Case Provenance ({selectedNode?.source_cases?.length ?? selectedEntityProfile.linked_cases?.length ?? 0}):
                </h5>
                <div className="space-y-2">
                  {/* The graph node lists every authorised case, including drafts linked by vehicle registration */}
                  {selectedNode?.source_cases?.length ? selectedNode.source_cases.map((sc: any, idx: number) => (
                    <div key={`sc-${idx}`} className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-blue-700 font-bold">
                          {sc.fir_number}
                          {sc.is_draft && <span className="ml-1.5 text-[9px] font-sans font-bold px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">DRAFT</span>}
                        </span>
                        <button type="button" onClick={() => navigate(`/cases/${sc.case_id}`)}
                          className="inline-flex items-center space-x-1 text-[11px] text-[#0f5132] font-semibold hover:underline">
                          <span>Open FIR</span>
                          <ExternalLink className="w-3 h-3" />
                        </button>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-200/60">
                        <span>Role: {sc.role_in_case}{sc.linked_by === 'VEHICLE_REGISTRATION' ? ' (same registration)' : ''}</span>
                        <span>{sc.station} ({sc.district})</span>
                      </div>
                    </div>
                  )) : selectedEntityProfile.linked_cases?.map((lc: any, idx: number) => (
                    <div key={idx} className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-blue-700 font-bold">{lc.case?.fir_number}</span>
                        <button
                          type="button"
                          onClick={() => navigate(`/cases/${lc.case?.id}`)}
                          className="inline-flex items-center space-x-1 text-[11px] text-[#0f5132] font-semibold hover:underline"
                        >
                          <span>Open FIR</span>
                          <ExternalLink className="w-3 h-3" />
                        </button>
                      </div>
                      <p className="text-[11px] text-slate-600 line-clamp-2">{lc.case?.offence_nature}</p>
                      <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-200/60">
                        <span>Role: {lc.mention?.role_in_case}</span>
                        <span>{lc.case?.station} ({lc.case?.district})</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center text-slate-400 p-4">
              <Info className="w-8 h-8 text-slate-300 mb-2" />
              <p className="font-medium text-slate-600">Click any node on the graph</p>
              <p className="text-[11px] text-slate-400 mt-1">
                Inspect cross-case connections, suspect conveyance ownership, scene locations, and phone numbers.
              </p>
            </div>
          )}

          {/* Communities List */}
          <div className="pt-3 border-t border-slate-100">
            <h4 className="font-bold text-xs text-slate-700 mb-2">Detected Louvain Communities:</h4>
            <div className="space-y-1.5">
              {graphData.communities?.map((comm: any, idx: number) => (
                <div key={idx} className="p-2 bg-slate-50 rounded flex items-center justify-between text-[11px]">
                  <span className="font-medium text-slate-700">{comm.label}</span>
                  <span className="font-mono bg-blue-100 text-blue-800 px-1.5 py-0.2 rounded font-bold">
                    {comm.size} Nodes
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
